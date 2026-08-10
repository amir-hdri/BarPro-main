"""
Queue routing contract tests
============================

``get_routed_queue()`` suffixes a base queue with a healthy IP index
(``scheduled_tasks`` → ``scheduled_tasks_2``). That only works if a Celery
worker actually consumes the suffixed queue. If the ``-Q`` list in
``compose/backend.yml`` and the routing logic drift apart, tasks are accepted
by the broker and then sit in a queue nobody listens on — they never run and
nothing errors. Commit 872e940 introduced exactly that regression by dropping
``scheduled_tasks_1/2/3`` from the worker ``-Q`` lists while the dispatcher
kept routing to them.

These tests pin the contract in BOTH directions:

* **Dispatch → consume**: every queue the code can dispatch to must appear in
  some worker's ``-Q`` list (tasks must never land in an unlistened queue).
* **Fleet ↔ configuration**: every ``WORKER_IP_INDEX`` declared by a worker
  service in the Docker Compose files must exist in the real
  ``get_available_ip_indices()`` output (no worker may consume queues the
  dispatcher never sends to — the P0-1 "idle Worker 3" bug).

The routing index set is read at runtime from ``get_available_ip_indices()``
instead of a hardcoded tuple, so a drift between ``AVAILABLE_IP_INDICES`` and
the compose-declared fleet fails CI instead of passing vacuously.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

from app.core.circuit_breaker import get_available_ip_indices, get_routed_queue

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_DIR = PROJECT_ROOT / "compose"
COMPOSE_BACKEND = COMPOSE_DIR / "backend.yml"
COMPOSE_WORKER_NODE = COMPOSE_DIR / "worker-node.yml"
LOCAL_START_SYSTEM = PROJECT_ROOT / "scripts" / "start_system.sh"
LOCAL_STOP_SYSTEM = PROJECT_ROOT / "scripts" / "stop_system.sh"

# Every compose file that can declare a concrete ``WORKER_IP_INDEX: <n>``.
# ``compose/worker-node.yml`` only uses the ``${WORKER_IP_INDEX}`` placeholder,
# so it contributes no concrete index itself — its template contract is pinned
# separately by ``test_worker_node_template_consumes_its_own_partitions``.
COMPOSE_FILES = sorted(
    [
        *COMPOSE_DIR.glob("*.yml"),
        PROJECT_ROOT / "docker-compose.yml",
    ]
)

# Base queues that go through get_routed_queue() somewhere in the codebase.
# rpa_scheduler is intentionally excluded — it is in EXEMPT_QUEUES and is never
# suffixed.
ROUTED_BASE_QUEUES = [
    "waybill_tasks",
    "reconciliation_tasks",
    "rpa_auth",
    "rpa_submit",
    "scheduled_tasks",
]

# Queues dispatched DIRECTLY (no suffix) — e.g. barpro.fuel.inquiry in
# dispatch_fuel_inquiry_task and the raw base queues. Every one must have a
# consumer in compose AND in the local all-in-one stack, or tasks are dropped
# silently (NEW-4 / X7).
DIRECT_DISPATCH_QUEUES = {
    "barpro.fuel.inquiry",
    "waybill_tasks",
    "reconciliation_tasks",
    "scheduled_tasks",
}


def _queues_by_worker() -> dict[str, set[str]]:
    """Parse the ``-Q`` queues for each named Celery worker in backend compose."""
    queues_by_worker: dict[str, set[str]] = {}
    current_worker: str | None = None
    lines = COMPOSE_BACKEND.read_text(encoding="utf-8").splitlines()

    for index, line in enumerate(lines):
        service_match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if service_match:
            service_name = service_match.group(1)
            is_celery_service = bool(
                re.fullmatch(r"celery_worker_\d+", service_name) or service_name == "celery_scheduler"
            )
            current_worker = service_name if is_celery_service else None
            if current_worker is not None:
                queues_by_worker[current_worker] = set()
            continue

        if current_worker is None or line.strip() != "- -Q":
            continue

        # The queue CSV is the next non-empty list item after ``- -Q``.
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                continue
            queue_csv = stripped.removeprefix("- ").strip()
            queues_by_worker[current_worker].update(q.strip() for q in queue_csv.split(",") if q.strip())
            break

    return queues_by_worker


def _consumed_queues() -> set[str]:
    """Return the union of queues consumed by all backend Celery workers."""
    return set().union(*_queues_by_worker().values())


def _services_with_profiles() -> set[str]:
    """Return the set of backend compose services that declare a ``profiles:`` key.

    A service behind a profile is NOT started by a plain
    ``docker compose up`` — so anything critical (e.g. the control-queue
    consumer) must live on a profile-less service or it silently vanishes on a
    central/dual-node deployment (NEW-1).
    """
    text = COMPOSE_BACKEND.read_text(encoding="utf-8")
    lines = text.splitlines()
    profiled: set[str] = set()
    current: str | None = None
    for line in lines:
        service_match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if service_match:
            current = service_match.group(1)
            continue
        if current is not None and re.match(r"^\s+profiles:\s*\[", line):
            profiled.add(current)
    return profiled


def _routed_ip_indices() -> list[int]:
    """Return the live routing pool and reject an empty configuration."""
    indices = get_available_ip_indices()
    assert indices, (
        "AVAILABLE_IP_INDICES resolved to an empty index pool — the dispatcher "
        "cannot route to any worker queue. Check the AVAILABLE_IP_INDICES "
        "environment variable (e.g. AVAILABLE_IP_INDICES='1,2,3')."
    )
    return indices


def _worker_ip_indices_by_file() -> dict[int, list[str]]:
    """Map concrete ``WORKER_IP_INDEX: <n>`` declarations to their compose files."""
    declared: dict[int, list[str]] = {}
    pattern = re.compile(
        r"^\s*WORKER_IP_INDEX\s*:\s*[\"']?(\d+)[\"']?\s*(?:#.*)?$",
        re.MULTILINE,
    )
    for yml in COMPOSE_FILES:
        text = yml.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            declared.setdefault(int(match.group(1)), []).append(yml.name)
    return declared


def _worker_node_queues(worker_ip_index: int, tmp_path: Path) -> set[str]:
    """Execute the worker-node command with a fake Celery binary and read ``-Q``.

    Compose converts ``$$`` in command blocks to a literal ``$``. Rendering
    that escape here validates the same Worker 2/3 branching the container
    executes, rather than merely matching a source snippet.
    """
    text = COMPOSE_WORKER_NODE.read_text(encoding="utf-8")
    match = re.search(
        r"^    command:\n      - /bin/sh\n      - -ec\n      - \|\n(?P<script>(?:^        .*\n?)*)",
        text,
        flags=re.MULTILINE,
    )
    assert match, "worker-node.yml must use an explicit shell command to build its queue list"

    command = textwrap.dedent(match.group("script")).replace("$$", "$")
    fake_celery = tmp_path / "celery"
    captured_args = tmp_path / f"celery-args-{worker_ip_index}.txt"
    fake_celery.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE_FILE"\n', encoding="utf-8")
    fake_celery.chmod(0o755)

    env = {
        **os.environ,
        "WORKER_IP_INDEX": str(worker_ip_index),
        "PATH": f"{tmp_path}:{os.environ.get('PATH', '')}",
        "CAPTURE_FILE": str(captured_args),
    }
    subprocess.run(["/bin/sh", "-ec", command], check=True, env=env, capture_output=True, text=True)

    args = captured_args.read_text(encoding="utf-8").splitlines()
    queue_arg_index = args.index("-Q")
    return {queue.strip() for queue in args[queue_arg_index + 1].split(",") if queue.strip()}


def _shell_variable(text: str, name: str) -> str:
    """Read a simple double-quoted shell variable assignment from a script."""
    match = re.search(rf'^{re.escape(name)}="(?P<value>[^"]*)"$', text, flags=re.MULTILINE)
    assert match, f"{name} is not defined as a double-quoted shell variable"
    return match.group("value")


def _shell_function_body(text: str, name: str) -> str:
    """Return a Bash function body for static launch-contract assertions."""
    match = re.search(rf"^{re.escape(name)}\(\) \{{\n(?P<body>.*?)^\}}", text, flags=re.MULTILINE | re.DOTALL)
    assert match, f"{name} function is missing"
    return match.group("body")


def _local_celery_launcher_source() -> str:
    """Extract the Python launcher embedded in ``start_system.sh``."""
    text = LOCAL_START_SYSTEM.read_text(encoding="utf-8")
    match = re.search(
        r'LOCAL_CELERY_QUEUE_LIST="\$queues".*?<<\'PY\'\n(?P<script>.*?)\nPY\n    \)',
        text,
        flags=re.DOTALL,
    )
    assert match, "embedded local Celery launcher is missing"
    return match.group("script")


def _launch_local_celery_for_test(
    queue_list: str,
    node_name: str,
    include_beat: bool,
    worker_id: str,
    worker_ip_index: str,
    tmp_path: Path,
    monkeypatch,
) -> tuple[list[str], dict[str, object]]:
    """Run the embedded launcher with a fake Popen and capture its child env."""
    captured: dict[str, object] = {}

    class FakePopen:
        def __init__(self, command: list[str], **kwargs: object) -> None:
            captured["command"] = command
            captured["kwargs"] = kwargs
            self.pid = 42

    monkeypatch.setenv("LOCAL_CELERY_QUEUE_LIST", queue_list)
    monkeypatch.setenv("LOCAL_CELERY_NODE_NAME", node_name)
    monkeypatch.setenv("LOCAL_CELERY_INCLUDE_BEAT", str(include_beat).lower())
    monkeypatch.setenv("LOCAL_CELERY_LOG_FILE", str(tmp_path / f"{worker_id}.log"))
    monkeypatch.setenv("LOCAL_CELERY_WORKER_ID", worker_id)
    monkeypatch.setenv("LOCAL_CELERY_WORKER_IP_INDEX", worker_ip_index)
    # Simulate a remote-node .env leaking into the parent process. The launcher
    # must replace it for Worker 3 and remove it for the generic local worker.
    monkeypatch.setenv("WORKER_ID", "2")
    monkeypatch.setenv("WORKER_IP_INDEX", "2")

    with patch("subprocess.Popen", FakePopen):
        exec(_local_celery_launcher_source(), {"__name__": "__launcher_test__"})

    assert "command" in captured and "kwargs" in captured
    return captured["command"], captured["kwargs"]


def _routed_targets(base_queue: str) -> set[str]:
    """All queue names get_routed_queue() can produce for the live routing pool."""
    targets: set[str] = set()
    for idx in _routed_ip_indices():
        with patch("app.core.circuit_breaker.get_next_ip_index_sync", return_value=idx):
            targets.add(get_routed_queue(base_queue))
    return targets


def test_compose_defines_worker_queues():
    """Sanity check that the compose parsing found something at all."""
    consumed = _consumed_queues()
    assert consumed, "no -Q queues parsed from compose/backend.yml"
    assert "waybill_tasks" in consumed


def test_available_ip_indices_resolve_to_non_empty_pool():
    """A broken fleet setting must not let routing tests pass vacuously."""
    assert get_available_ip_indices(), "get_available_ip_indices() returned an empty pool"


def test_every_routed_queue_has_a_consumer():
    """No dispatch target may be a queue that zero workers consume."""
    consumed = _consumed_queues()

    unroutable: dict[str, set[str]] = {}
    for base in ROUTED_BASE_QUEUES:
        missing = _routed_targets(base) - consumed
        if missing:
            unroutable[base] = missing

    assert not unroutable, (
        "These queues are dispatched to but consumed by no worker, so tasks "
        f"sent there are silently dropped: {unroutable}. Add them to a worker's "
        "-Q list in compose/backend.yml."
    )


def test_scheduled_tasks_partitions_are_consumed():
    """Every partition in the active routing pool must have a consumer."""
    consumed = _consumed_queues()
    for idx in _routed_ip_indices():
        queue = f"scheduled_tasks_{idx}"
        assert queue in consumed, (
            f"{queue} has no consumer — scheduled waybill jobs routed there "
            "would never execute (regression from commit 872e940)."
        )


def test_exempt_queue_is_not_suffixed():
    """rpa_scheduler must stay unsuffixed, and must have a consumer."""
    with patch("app.core.circuit_breaker.get_next_ip_index_sync", return_value=2):
        assert get_routed_queue("rpa_scheduler") == "rpa_scheduler"
    assert "rpa_scheduler" in _consumed_queues()


def test_direct_dispatch_queues_have_consumers_everywhere():
    """Every directly-dispatched queue needs a consumer in compose AND the local stack."""
    consumed = _consumed_queues()
    start_script = LOCAL_START_SYSTEM.read_text(encoding="utf-8")
    local_queues = set(_shell_variable(start_script, "LOCAL_WORKER_QUEUES").split(","))

    missing_compose = DIRECT_DISPATCH_QUEUES - consumed
    missing_local = DIRECT_DISPATCH_QUEUES - local_queues
    assert not missing_compose, f"Directly-dispatched queues with no compose consumer: {sorted(missing_compose)}"
    assert (
        not missing_local
    ), f"Directly-dispatched queues missing from start_system.sh LOCAL_WORKER_QUEUES: {sorted(missing_local)}"


def test_env_templates_use_reachable_proxy():
    """Deploy-generated proxy templates must not reference unresolvable squid_N hostnames (X2).

    Squid runs with network_mode: host, so it has no DNS name inside the worker
    container; a proxy URL like http://squid_1:3128 fails closed on every job.
    Templates must use the Docker bridge gateway (172.20.0.1) or a real public IP.
    """
    offenders = []
    for f in [
        PROJECT_ROOT / "scripts" / "deploy_single_vm.py",
        PROJECT_ROOT / "scripts" / "deploy_remote.sh",
        PROJECT_ROOT / "scripts" / "deploy_remote.py",
    ]:
        text = f.read_text(encoding="utf-8")
        if re.search(r"WORKER_\d_PROXY\s*=\s*\"?http://squid_[123]:", text):
            offenders.append(f.name)
    assert not offenders, f"deploy templates still emit unresolvable squid_N proxy URLs (X2): {offenders}"


def test_every_worker_ip_index_is_available():
    """Every concrete Compose worker must be part of the dispatcher routing pool."""
    available = set(get_available_ip_indices())
    declared = _worker_ip_indices_by_file()

    assert declared, "no concrete WORKER_IP_INDEX values parsed from compose files"
    orphaned = {idx: files for idx, files in declared.items() if idx not in available}
    assert not orphaned, (
        "Worker fleet ↔ AVAILABLE_IP_INDICES drift (P0-1): these WORKER_IP_INDEX "
        f"values are declared in Docker Compose {orphaned} but are missing from "
        f"the real AVAILABLE_IP_INDICES output ({sorted(available)})."
    )


def test_rpa_scheduler_has_single_profileless_consumer():
    """rpa_scheduler must be consumed by exactly ONE profile-less service.

    Previously it lived on worker 3 behind the "scale-out" profile (and on
    remote worker nodes), so a central/dual-node deployment had NO consumer
    (NEW-1). The dedicated celery_scheduler service must be the only consumer
    and must not be profile-gated.
    """
    consumers = {worker_name for worker_name, queues in _queues_by_worker().items() if "rpa_scheduler" in queues}
    assert consumers == {"celery_scheduler"}, (
        "rpa_scheduler is a singleton control queue (dispatcher fires every 5s) "
        "and must be consumed only by the dedicated profile-less celery_scheduler, "
        f"not {sorted(consumers)}."
    )
    profiled = _services_with_profiles()
    assert "celery_scheduler" not in profiled, (
        "celery_scheduler (rpa_scheduler consumer) must NOT be behind a compose "
        "profile, or it vanishes on a central/dual-node deployment."
    )


def test_control_queue_is_not_doubly_consumed_by_worker_node(tmp_path: Path):
    """Remote worker nodes must NOT consume the singleton control queue.

    The dispatcher publishes to rpa_scheduler every 5s; if a remote worker (with
    its 360s browser tasks) consumed it, the control loop would starve for up to
    minutes. Only the central celery_scheduler consumes it.
    """
    for worker_ip_index in (2, 3):
        assert "rpa_scheduler" not in _worker_node_queues(
            worker_ip_index, tmp_path
        ), f"worker-node.yml must not consume rpa_scheduler (index {worker_ip_index})."


def test_worker_node_template_consumes_its_own_partitions(tmp_path: Path):
    """Remote workers must consume partitions for their numeric IP index."""
    for worker_ip_index in (2, 3):
        queues = _worker_node_queues(worker_ip_index, tmp_path)
        for base in ROUTED_BASE_QUEUES:
            expected = f"{base}_{worker_ip_index}"
            assert expected in queues, (
                f"worker-node.yml does not consume {expected}; a remote worker "
                f"would never receive routed {base} tasks."
            )


def test_worker_node_template_never_consumes_rpa_scheduler(tmp_path: Path):
    """The shared remote template must never consume the singleton control queue.

    The control queue is owned exclusively by celery_scheduler on the central
    server; remote Worker 2/3 must stay off it so the 5s dispatcher is never
    starved by their long browser tasks (NEW-1 / FIX-A).
    """
    for worker_ip_index in (2, 3):
        assert "rpa_scheduler" not in _worker_node_queues(worker_ip_index, tmp_path)


def test_local_start_script_reserves_scheduler_for_explicit_worker_3():
    """The local all-in-one stack must not reintroduce a generic consumer."""
    start_script = LOCAL_START_SYSTEM.read_text(encoding="utf-8")
    stop_script = LOCAL_STOP_SYSTEM.read_text(encoding="utf-8")
    assert LOCAL_STOP_SYSTEM.read_bytes().startswith(b"#!/bin/bash\n")

    generic_queues = _shell_variable(start_script, "LOCAL_WORKER_QUEUES").split(",")
    scheduler_queues = _shell_variable(start_script, "LOCAL_SCHEDULER_QUEUES").split(",")
    scheduler_nodename = _shell_variable(start_script, "LOCAL_SCHEDULER_NODENAME")
    scheduler_worker_id = _shell_variable(start_script, "LOCAL_SCHEDULER_WORKER_ID")
    scheduler_ip_index = _shell_variable(start_script, "LOCAL_SCHEDULER_IP_INDEX")

    assert "rpa_scheduler" not in generic_queues
    assert scheduler_queues == ["rpa_scheduler"]
    assert scheduler_nodename == "worker_3@%h"
    assert scheduler_worker_id == scheduler_ip_index == "3"

    launcher = _shell_function_body(start_script, "start_local_celery_worker")
    assert 'LOCAL_CELERY_QUEUE_LIST="$queues"' in launcher
    assert 'LOCAL_CELERY_WORKER_ID="$worker_id"' in launcher
    assert 'LOCAL_CELERY_WORKER_IP_INDEX="$worker_ip_index"' in launcher
    assert 'env["WORKER_ID"] = worker_id' in launcher
    assert 'env["WORKER_IP_INDEX"] = worker_ip_index' in launcher
    assert 'env.pop("WORKER_IP_INDEX", None)' in launcher
    assert '"-Q",' in launcher
    assert "queue_list," in launcher
    assert '"-n",' in launcher
    assert "node_name," in launcher

    scheduler_wrapper = _shell_function_body(start_script, "start_local_scheduler_worker")
    assert '"$LOCAL_SCHEDULER_QUEUES"' in scheduler_wrapper
    assert '"$LOCAL_SCHEDULER_NODENAME"' in scheduler_wrapper
    assert '"$LOCAL_SCHEDULER_WORKER_ID"' in scheduler_wrapper
    assert '"$LOCAL_SCHEDULER_IP_INDEX"' in scheduler_wrapper
    assert '"false"' in scheduler_wrapper  # Beat remains on the generic local worker.

    generic_wrapper = _shell_function_body(start_script, "start_local_worker")
    assert '"$LOCAL_WORKER_QUEUES"' in generic_wrapper
    assert '"$LOCAL_GENERIC_WORKER_ID"' in generic_wrapper
    assert '"true"' in generic_wrapper
    assert start_script.index("if ! start_local_scheduler_worker;") < start_script.index("if ! start_local_worker;")
    local_stop = _shell_function_body(start_script, "stop_local_worker")
    assert '"$SCHEDULER_WORKER_PID_FILE"' in local_stop
    assert "output/scheduler_worker.pid" in stop_script


def test_local_launcher_assigns_worker_3_identity_without_env_leakage(tmp_path: Path, monkeypatch):
    """Worker 3 must not inherit a remote Worker 2 identity from ``.env``."""
    scheduler_command, scheduler_kwargs = _launch_local_celery_for_test(
        queue_list="rpa_scheduler",
        node_name="worker_3@%h",
        include_beat=False,
        worker_id="3",
        worker_ip_index="3",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    scheduler_env = scheduler_kwargs["env"]
    assert isinstance(scheduler_env, dict)
    assert scheduler_env["WORKER_ID"] == "3"
    assert scheduler_env["WORKER_IP_INDEX"] == "3"
    assert "LOCAL_CELERY_WORKER_ID" not in scheduler_env
    assert scheduler_command == [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.workers.phase1_tasks:celery_app",
        "worker",
        "-Q",
        "rpa_scheduler",
        "-n",
        "worker_3@%h",
        "-l",
        "info",
        "--pool",
        "solo",
    ]

    generic_command, generic_kwargs = _launch_local_celery_for_test(
        queue_list="waybill_tasks",
        node_name="local_worker@%h",
        include_beat=True,
        worker_id="local_worker",
        worker_ip_index="",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    generic_env = generic_kwargs["env"]
    assert isinstance(generic_env, dict)
    assert generic_env["WORKER_ID"] == "local_worker"
    assert "WORKER_IP_INDEX" not in generic_env
    assert generic_command[-3:] == ["-B", "--pool", "solo"]
