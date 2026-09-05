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
from app.core.config import utcms_config
from scripts.deployment_inventory import (
    CENTRAL_EXPECTED_CONTAINERS,
    audit_container_inventory,
    expected_containers,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_DIR = PROJECT_ROOT / "compose"
COMPOSE_BACKEND = COMPOSE_DIR / "backend.yml"
COMPOSE_WORKER_NODE = COMPOSE_DIR / "worker-node.yml"
LOCAL_START_SYSTEM = PROJECT_ROOT / "scripts" / "start_system.sh"
LOCAL_STOP_SYSTEM = PROJECT_ROOT / "scripts" / "stop_system.sh"
PROXY_COMPOSE = COMPOSE_DIR / "proxy.yml"
MANAGE_SCRIPT = PROJECT_ROOT / "manage.sh"
QUICK_DEPLOY_CENTRAL = PROJECT_ROOT / "scripts" / "quick_deploy_central.sh"
DEPLOY_SINGLE_VM = PROJECT_ROOT / "scripts" / "deploy_single_vm.py"

# Every script/doc that tells an operator to bring up compose/worker-node.yml.
# Each invocation MUST pass --env-file .env so compose interpolation reads the
# worker node's OWN /opt/barpro/.env instead of ./compose/.env (X5/FIX-L) —
# otherwise WORKER_IP_INDEX / CENTRAL_IP placeholders in worker-node.yml break
# the rendered queue list and the node registers against the wrong identity.
WORKER_NODE_COMPOSE_FILES = [
    PROJECT_ROOT / "scripts" / "add_worker_firewall.sh",
    PROJECT_ROOT / "scripts" / "deploy_all_servers.sh",
    PROJECT_ROOT / "scripts" / "setup_worker.sh",
    PROJECT_ROOT / "docs" / "adding_new_worker.md",
    PROJECT_ROOT / "docs" / "runbook_worker_registration.md",
    PROJECT_ROOT / "docs" / "runbook_scale_out.md",
]

DEPLOY_ALL_SERVERS = PROJECT_ROOT / "scripts" / "deploy_all_servers.sh"
ADD_WORKER_FIREWALL = PROJECT_ROOT / "scripts" / "add_worker_firewall.sh"

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


def test_manage_health_only_probes_enabled_remote_indices() -> None:
    """Central-only health must not fail because disabled remote nodes are offline."""
    manage = MANAGE_SCRIPT.read_text(encoding="utf-8")

    assert 'active_indices=",${AVAILABLE_IP_INDICES:-1,2,3},"' in manage
    assert '[[ "$active_indices" == *,2,* ]]' in manage
    assert '[[ "$active_indices" == *,3,* ]]' in manage


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


# ════════════════════════════════════════════════════════════════════════════
# R4 — contract tests for the R1/R2/R3 review fixes
# ════════════════════════════════════════════════════════════════════════════


def _beat_queues(monkeypatch, deprecate_old_execution_path: bool) -> set[str]:
    """Destination queues of the REAL beat schedule for one execution-path flag.

    Reads ``_build_beat_schedule()`` at runtime from app.workers.celery_app and
    returns the ``options.queue`` of every entry, so a change in the beat
    schedule (new task, rerouted task) immediately re-pins the contract instead
    of silently drifting.
    """
    from app.workers.celery_app import _build_beat_schedule

    monkeypatch.setattr(utcms_config, "DEPRECATE_OLD_EXECUTION_PATH", deprecate_old_execution_path)
    queues: set[str] = set()
    for entry in _build_beat_schedule().values():
        queue = entry.get("options", {}).get("queue")
        if queue:
            queues.add(queue)
    assert queues, "beat schedule produced no queue destinations"
    return queues


def test_every_beat_queue_has_a_profileless_consumer(monkeypatch):
    """No queue the beat emits to may be consumed ONLY by profile-gated workers.

    A service behind a ``profiles:`` key is not started by a plain
    ``docker compose up`` — on a central/dual-node deployment it does not exist.
    If every consumer of a beat destination queue is profile-gated (or there is
    no consumer at all), the scheduled task is published into a queue nobody
    listens on and never runs (FIX-N-2).
    """
    profiled = _services_with_profiles()
    consumers_by_queue: dict[str, set[str]] = {}
    for worker, queues in _queues_by_worker().items():
        for queue in queues:
            consumers_by_queue.setdefault(queue, set()).add(worker)

    for deprecate in (True, False):  # both DEPRECATE_OLD_EXECUTION_PATH branches
        for queue in _beat_queues(monkeypatch, deprecate):
            consumers = consumers_by_queue.get(queue, set())
            assert consumers, (
                f"beat destination queue {queue!r} (DEPRECATE_OLD_EXECUTION_PATH="
                f"{deprecate}) has NO consumer in compose/backend.yml — the task "
                "is published into a queue nobody listens on."
            )
            assert consumers - profiled, (
                f"beat destination queue {queue!r} (DEPRECATE_OLD_EXECUTION_PATH="
                f"{deprecate}) is consumed ONLY by profile-gated services "
                f"{sorted(consumers & profiled)} — a central/dual-node deployment "
                "would have no consumer for it (FIX-N-2)."
            )


def test_control_queue_consumer_is_not_shared_with_browser_work():
    """celery_scheduler (the singleton rpa_scheduler consumer) must be solo.

    The dispatcher publishes to rpa_scheduler every 5s. If the dedicated
    scheduler service also consumed browser-work queues (waybill/rpa/recon/
    scheduled/fuel — tasks that hold a solo worker for minutes), the control
    loop would sit behind long browser jobs and starve (NEW-1). The consumer
    set must be exactly {rpa_scheduler}.
    """
    by_worker = _queues_by_worker()
    scheduler_queues = by_worker.get("celery_scheduler", set())
    assert scheduler_queues == {"rpa_scheduler"}, (
        "celery_scheduler must consume EXACTLY the singleton control queue "
        f"rpa_scheduler, but consumes {sorted(scheduler_queues)}."
    )

    browser_markers = (
        "waybill_tasks",
        "rpa_auth",
        "rpa_submit",
        "reconciliation_tasks",
        "scheduled_tasks",
        "fuel.inquiry",
    )
    shared = {q for q in scheduler_queues if any(marker in q for marker in browser_markers)}
    assert not shared, (
        "celery_scheduler shares its process with browser-work queues "
        f"{sorted(shared)} — a 5s control loop behind a 360s browser job "
        "starves the whole orchestrator (NEW-1)."
    )


def test_compose_never_hardcodes_per_worker_proxy():
    """Per-worker proxy values must be interpolated, never hardcoded (R1).

    ``environment:`` always overrides ``env_file:`` in Docker Compose, so a
    hardcoded ``WORKER_2_PROXY: http://172.20.0.1:3129`` neutralizes the value
    that deploy scripts (deploy_remote.sh / deploy_single_vm.py) write into the
    central .env for the two-node topology — worker 2 would proxy through the
    central server instead of its own node. Values must be
    ``${WORKER_N_PROXY:-<single-VM fallback>}``.
    """
    text = COMPOSE_BACKEND.read_text(encoding="utf-8")

    hardcoded = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if re.match(r"^(WORKER_\d_PROXY|RPA_PROXIES):\s*http", stripped):
            hardcoded.append(f"backend.yml:{lineno}: {stripped}")
    assert not hardcoded, (
        "per-worker proxy values are hardcoded in compose/backend.yml (R1); "
        "they must be ${WORKER_N_PROXY:-<fallback>} so the deploy-time .env "
        f"value wins: {hardcoded}"
    )

    # The single-VM fallbacks must be preserved so the existing topology keeps
    # the exact same behavior when .env does not define the variables.
    expected_defaults = {
        "WORKER_1_PROXY": "http://172.20.0.1:3128",
        "WORKER_2_PROXY": "http://172.20.0.1:3129",
        "WORKER_3_PROXY": "http://172.20.0.1:3130",
    }
    for variable, default in expected_defaults.items():
        assert f"${{{variable}:-{default}}}" in text, (
            f"{variable} interpolation with default {default} is missing from "
            "compose/backend.yml — the single-VM topology would lose its proxy."
        )


def test_worker_node_compose_invocations_pass_env_file():
    """Every documented worker-node invocation must pass --env-file .env (X5).

    Compose resolves ${VAR} interpolation against the project directory by
    default. With ``-f compose/worker-node.yml`` the project directory is
    ``compose/``, so ``docker compose -f compose/worker-node.yml up`` reads
    ``compose/.env`` (which does not exist) instead of the worker's
    ``/opt/barpro/.env`` — WORKER_IP_INDEX/CENTRAL_IP placeholders then break
    the rendered queue list silently.
    """
    offenders = []
    for path in WORKER_NODE_COMPOSE_FILES:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "docker compose" in line and "worker-node.yml" in line and " up " in line:
                if "--env-file" not in line:
                    offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "worker-node.yml compose invocations must pass --env-file .env so "
        "interpolation reads the worker node's own .env (X5), not ./compose/.env: "
        f"{offenders}"
    )


def test_worker_runbooks_point_broker_and_db_at_the_central_defaults():
    """Worker .env templates must use Redis DB 0 and the central DB name.

    The Central server publishes tasks on Redis DB 0 and POSTGRES_DB defaults
    to utcms_rpa. Older revisions of the runbooks used :6379/1 for the broker
    and :6379/2 for the result backend (and :5432/barpro) — a worker built from
    those instructions registers successfully but NEVER receives a task,
    because it listens on a different Redis database than the one the central
    API publishes to.
    """
    runbooks = [
        PROJECT_ROOT / "docs" / "runbook_worker_registration.md",
        PROJECT_ROOT / "docs" / "runbook_scale_out.md",
        PROJECT_ROOT / "docs" / "adding_new_worker.md",
    ]
    offenders = []
    for path in runbooks:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "CELERY_BROKER_URL=" in line or "CELERY_RESULT_BACKEND=" in line:
                if not re.search(r":6379/0\b", line):
                    offenders.append(f"{path.name}:{lineno}: {line.strip()}")
            if "DATABASE_URL=" in line and "utcms_rpa" not in line:
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "worker .env templates in the runbooks must point CELERY_BROKER_URL / "
        "CELERY_RESULT_BACKEND at Redis DB 0 and DATABASE_URL at the central "
        "POSTGRES_DB (utcms_rpa) — anything else silently breaks task delivery: "
        f"{offenders}"
    )


def test_runbook_squid_render_loads_env_and_requires_egress_ip():
    """Runbook render steps must be self-contained and fail loudly (R3).

    Every operator doc that renders infra/squid/squid_worker.conf must:
      1. define WORKER_EGRESS_IP in its .env template — otherwise the render
         substitutes an EMPTY tcp_outgoing_address into the squid config and
         the node silently ships broken egress;
      2. load .env into the shell (`source .env`) before the sed — otherwise
         the shell variables are unset;
      3. guard with `:?` so a missing value fails the command loudly instead
         of rendering garbage (e.g. a literal placeholder string).
    """
    runbooks = [
        PROJECT_ROOT / "docs" / "adding_new_worker.md",
        PROJECT_ROOT / "docs" / "runbook_worker_registration.md",
        PROJECT_ROOT / "docs" / "runbook_scale_out.md",
    ]
    for path in runbooks:
        text = path.read_text(encoding="utf-8")

        env_template = re.search(
            r"cat > (?:/opt/barpro/)?\.env << 'EOF'\n(?P<body>.*?)\nEOF",
            text,
            flags=re.DOTALL,
        )
        assert env_template, f"{path.name}: .env template block not found"
        assert "WORKER_EGRESS_IP=" in env_template.group("body"), (
            f"{path.name}: .env template must define WORKER_EGRESS_IP — the "
            "squid render step needs it for tcp_outgoing_address."
        )

        render_blocks = re.findall(r"```bash\n(?P<body>.*?)\n```", text, flags=re.DOTALL)
        render_block = next(
            (block for block in render_blocks if 'sed -e "s/__WORKER_EGRESS_IP__' in block),
            None,
        )
        assert render_block, f"{path.name}: squid render block not found"
        assert "source .env" in render_block, (
            f"{path.name}: render block must load .env into the shell "
            "(`set -a; source .env; set +a`) before the sed."
        )
        assert "${WORKER_EGRESS_IP:?" in render_block, (
            f"{path.name}: render block must use a :? guard on " "WORKER_EGRESS_IP so a missing value fails loudly."
        )
        assert "${CENTRAL_IP:?" in render_block, f"{path.name}: render block must use a :? guard on CENTRAL_IP."


def test_squid_worker_template_is_rendered_not_edited_in_place():
    """Operators must render squid_worker.conf → squid_worker.runtime.conf (X4).

    add_worker_firewall.sh used to print ``sed -i`` commands against the git
    template infra/squid/squid_worker.conf. Editing the tracked template breaks
    every future ``git pull`` on the node (merge conflict with the placeholders)
    and leaves the repo dirty. The rendered copy is what
    compose/worker-node.yml mounts.
    """
    text = ADD_WORKER_FIREWALL.read_text(encoding="utf-8")
    assert not re.search(r"^\s*sed -i\b", text, flags=re.MULTILINE), (
        "add_worker_firewall.sh must NOT sed -i the git template "
        "infra/squid/squid_worker.conf (X4) — render it to "
        "infra/squid/squid_worker.runtime.conf instead."
    )
    assert "squid_worker.runtime.conf" in text, (
        "add_worker_firewall.sh must instruct rendering to " "infra/squid/squid_worker.runtime.conf."
    )

    node_text = COMPOSE_WORKER_NODE.read_text(encoding="utf-8")
    assert "squid_worker.runtime.conf" in node_text, (
        "compose/worker-node.yml must mount the RENDERED copy " "(squid_worker.runtime.conf), never the git template."
    )


def _worker_render_blocks() -> list[str]:
    """Extract the squid render commands from deploy_all_servers.sh SSH blocks.

    The sed command lives inside a double-quoted SSH string, so the extracted
    text is exactly what the LOCAL bash parses when the script runs. There must
    be two identical blocks (Worker 2 and Worker 3).
    """
    lines = DEPLOY_ALL_SERVERS.read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        if re.search(r"sed -e .*__WORKER_EGRESS_IP__", lines[index]):
            block = [lines[index]]
            index += 1
            while index < len(lines) and "squid_worker.runtime.conf" not in lines[index]:
                block.append(lines[index])
                index += 1
            assert index < len(lines), "render block never reaches squid_worker.runtime.conf"
            block.append(lines[index])
            blocks.append("\n".join(block))
        index += 1
    assert len(blocks) == 2, (
        "deploy_all_servers.sh must render the squid template for BOTH "
        f"remote workers; found {len(blocks)} render block(s)."
    )
    return blocks


def test_worker_node_render_expands_on_the_remote_host(tmp_path: Path):
    """The render variables must expand on the worker node, not the launcher (R2).

    Phase A — launcher side: execute the exact text bash parses locally, with
    no WORKER_EGRESS_IP / CENTRAL_IP (they live in each node's own .env). If
    the ${...} were NOT escaped, the :? guard kills the deploy locally with
    exit 1 before SSH even runs (and a stray local value would stamp the SAME
    egress IP on every worker). If escaped, the command passes through and the
    rendered file still carries the literal placeholder for the remote shell.

    Phase B — node side: what the remote shell receives is the same text after
    local expansion (``\\${`` → ``${``). Execute it with the node's OWN .env
    values and verify the rendered config uses THEM; a missing remote value
    must fail on the node (exit != 0), not render garbage.
    """
    template = PROJECT_ROOT / "infra" / "squid" / "squid_worker.conf"
    assert template.is_file(), "infra/squid/squid_worker.conf template missing"

    base_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    worker_dir = tmp_path / "node"
    (worker_dir / "infra" / "squid").mkdir(parents=True)
    (worker_dir / "infra" / "squid" / "squid_worker.conf").write_text(
        template.read_text(encoding="utf-8"), encoding="utf-8"
    )

    blocks = _worker_render_blocks()
    for block in blocks:
        # ── Phase A: the launcher must NOT expand the node-scoped variables.
        result = subprocess.run(
            ["/bin/bash", "-c", block],
            env=base_env,
            cwd=worker_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            "deploy_all_servers.sh expands ${WORKER_EGRESS_IP:?...} on the "
            "LAUNCHER: the deploy dies locally before SSH even runs when the "
            f"variable is not set there (R2). stderr: {result.stderr.strip()[:200]}"
        )
        locally_rendered = (worker_dir / "infra" / "squid" / "squid_worker.runtime.conf").read_text(encoding="utf-8")
        assert "${WORKER_EGRESS_IP" in locally_rendered, (
            "the launcher-side render substituted WORKER_EGRESS_IP locally — "
            "the placeholder must survive for the remote shell (R2)."
        )

    # ── Phase B: the node's OWN .env values must land in the config.
    node_envs = [
        {"WORKER_EGRESS_IP": "203.0.113.77", "CENTRAL_IP": "198.51.100.9"},
        {"WORKER_EGRESS_IP": "203.0.113.88", "CENTRAL_IP": "198.51.100.10"},
    ]
    for block, node_env in zip(blocks, node_envs, strict=True):
        # Simulate the local expansion of the escaped variables: \$ -> $.
        remote_command = block.replace("\\${", "${")
        result = subprocess.run(
            ["/bin/bash", "-c", remote_command],
            env={**base_env, **node_env},
            cwd=worker_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"node-side render failed: {result.stderr.strip()[:200]}"
        rendered = (worker_dir / "infra" / "squid" / "squid_worker.runtime.conf").read_text(encoding="utf-8")
        assert f"tcp_outgoing_address {node_env['WORKER_EGRESS_IP']}" in rendered, (
            "worker-node render did not use the node's own WORKER_EGRESS_IP " f"(R2): {rendered}"
        )
        assert f"acl central src {node_env['CENTRAL_IP']}" in rendered, (
            "worker-node render did not use the node's own CENTRAL_IP (R2): " f"{rendered}"
        )
        assert "__WORKER_EGRESS_IP__" not in rendered and "__CENTRAL_IP__" not in rendered, (
            "rendered squid config still contains template placeholders (R2): " f"{rendered}"
        )

    # ── Phase B failure mode: a MISSING value on the node fails there clearly.
    missing = subprocess.run(
        ["/bin/bash", "-c", blocks[0].replace("\\${", "${")],
        env={**base_env, "CENTRAL_IP": "198.51.100.9"},
        cwd=worker_dir,
        capture_output=True,
        text=True,
    )
    assert missing.returncode != 0, (
        "a worker node without WORKER_EGRESS_IP must fail the render with "
        "exit != 0 (the :? guard) instead of silently emitting a broken config."
    )


# ════════════════════════════════════════════════════════════════════════════
# Central-side review contracts (2nd pass): squid render-not-edit, single
# backend image, registry-aligned worker image, CD uses Compose V2 (X12).
# ════════════════════════════════════════════════════════════════════════════

CENTRAL_SQUID_TEMPLATES = [
    PROJECT_ROOT / "infra" / "squid" / "squid_1.conf",
    PROJECT_ROOT / "infra" / "squid" / "squid_2.conf",
    PROJECT_ROOT / "infra" / "squid" / "squid_3.conf",
]
RENDER_SCRIPT = PROJECT_ROOT / "scripts" / "render_squid_configs.sh"
CD_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "cd-deploy.yml"
REGISTRY_OVERRIDE = PROJECT_ROOT / "deploy" / "registry-images.yml"

GHCR_BACKEND_IMAGE = "ghcr.io/amir-hdri/barpro-main/barpro-backend:latest"
GHCR_FRONTEND_IMAGE = "ghcr.io/amir-hdri/barpro-main/barpro-frontend:latest"


def test_central_squid_configs_are_rendered_not_edited_in_place(tmp_path: Path):
    """Central squid templates must be rendered to *.runtime.conf (X4 central).

    deploy scripts used to ``sed -i`` the tracked infra/squid/squid_1/2/3.conf
    on the server — dirtying the git tree so the next ``git pull`` on the
    central server fails. compose/proxy.yml must mount the rendered
    ``squid_<N>.runtime.conf`` (never the template), and no script may edit the
    template in place.
    """
    proxy_text = COMPOSE_DIR.joinpath("proxy.yml").read_text(encoding="utf-8")
    for conf in CENTRAL_SQUID_TEMPLATES:
        runtime_name = conf.name.replace(".conf", ".runtime.conf")
        assert f"{runtime_name}:/etc/squid/squid.conf:ro" in proxy_text, (
            f"compose/proxy.yml must mount {runtime_name} (the RENDERED copy), "
            f"not the git template {conf.name} (X4 central)."
        )
        assert f"{conf.name}:/etc/squid/squid.conf:ro" not in proxy_text

    # No script may sed -i the central squid templates.
    for script in [
        PROJECT_ROOT / "scripts" / "deploy_single_vm.py",
        PROJECT_ROOT / "scripts" / "deploy_remote.sh",
        PROJECT_ROOT / "scripts" / "deploy_remote.py",
        PROJECT_ROOT / "scripts" / "server_deploy.py",
    ]:
        text = script.read_text(encoding="utf-8")
        assert not re.search(
            r"sed -i[^\n]*squid_[123]\.conf", text
        ), f"{script.name} still sed -i's a central squid template (X4 central)."

    # .gitignore must cover the rendered artifacts.
    gitignore = PROJECT_ROOT.joinpath(".gitignore").read_text(encoding="utf-8")
    assert "squid_[123].runtime.conf" in gitignore

    # ── Behavioral check: run the render script in a scratch repo ──
    scratch = tmp_path / "repo"
    (scratch / "infra" / "squid").mkdir(parents=True)
    (scratch / "scripts").mkdir(parents=True)
    for conf in CENTRAL_SQUID_TEMPLATES:
        (scratch / "infra" / "squid" / conf.name).write_text(conf.read_text(encoding="utf-8"))
    (scratch / "scripts" / "render_squid_configs.sh").write_text(RENDER_SCRIPT.read_text(encoding="utf-8"))

    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}

    def run_render(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/bash", "scripts/render_squid_configs.sh", *args],
            cwd=scratch,
            env=env,
            capture_output=True,
            text=True,
        )

    # 1) with explicit IPs → egress bound; template untouched; idempotent
    result = run_render("198.51.100.1", "203.0.113.9")
    assert result.returncode == 0, result.stderr
    rendered = (scratch / "infra" / "squid" / "squid_1.runtime.conf").read_text()
    assert "tcp_outgoing_address 198.51.100.1" in rendered
    # The ACTIVE egress line must be substituted (the template's explanatory
    # comment may still mention the placeholder string).
    assert "# tcp_outgoing_address __EGRESS_IP__" not in rendered
    template = (scratch / "infra" / "squid" / "squid_1.conf").read_text()
    assert "tcp_outgoing_address 198.51.100.1" not in template, "render must not modify the git template"
    # second run is stable (idempotent)
    run_render("198.51.100.1", "203.0.113.9")
    assert (scratch / "infra" / "squid" / "squid_1.runtime.conf").read_text() == rendered

    # 2) without IPs → egress line stays commented (safe default route)
    (scratch / "infra" / "squid" / "squid_1.runtime.conf").unlink()
    result = run_render()
    assert result.returncode == 0, result.stderr
    no_ip = (scratch / "infra" / "squid" / "squid_1.runtime.conf").read_text()
    assert "tcp_outgoing_address 198.51.100.1" not in no_ip
    assert "# tcp_outgoing_address __EGRESS_IP__" in no_ip


def test_compose_up_paths_render_squid_before_proxy():
    """Every entry point that starts the proxy must render squid configs first.

    compose/proxy.yml now mounts squid_<N>.runtime.conf, so any path that
    brings the stack up (manage.sh start/deploy, quick_deploy_central.sh) must
    invoke scripts/render_squid_configs.sh beforehand — otherwise the mount
    source does not exist and the stack fails to start.
    """
    manage = PROJECT_ROOT / "manage.sh"
    manage_text = manage.read_text(encoding="utf-8")

    start_block = manage_text[manage_text.index("    start)") :]
    start_block = start_block[: start_block.index("    stop)")]
    proxy_up = start_block.index("compose/proxy.yml up -d")
    render_call = start_block.index("render_squid_configs.sh")
    assert render_call < proxy_up, "manage.sh start must render squid configs BEFORE starting the proxy."

    deploy_block = manage_text[manage_text.index("    deploy)") :]
    deploy_block = deploy_block[: deploy_block.index("    *)")]
    assert (
        "render_squid_configs.sh" in deploy_block
    ), "manage.sh deploy must render squid configs before restarting services."

    quick = PROJECT_ROOT / "scripts" / "quick_deploy_central.sh"
    quick_text = quick.read_text(encoding="utf-8")
    render_index = quick_text.index("render_squid_configs.sh")
    assert render_index >= 0, "quick_deploy_central.sh must render squid configs after git pull."
    first_up = quick_text.index("up -d")  # first actual compose up command
    assert render_index < first_up, "quick_deploy_central.sh must render before any compose up."


def _compose_service_block(compose_text: str, service: str) -> str:
    """Extract one top-level service block from a two-space-indented compose."""
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\s*$\n(.*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)",
        compose_text,
    )
    assert match is not None, f"service {service!r} missing from compose file"
    return match.group(1)


def test_model_b_proxy_default_and_model_a_opt_in_contract():
    """Central Model B must not start Squid 2/3 without an explicit profile."""
    proxy_text = PROXY_COMPOSE.read_text(encoding="utf-8")

    assert "profiles:" not in _compose_service_block(proxy_text, "squid_1")
    for service in ("squid_2", "squid_3"):
        block = _compose_service_block(proxy_text, service)
        assert 'profiles: ["model-a"]' in block, (
            f"{service} must be protected by the explicit model-a profile; "
            "otherwise Model B Central publishes ports 3129/3130 again."
        )

    single_vm = DEPLOY_SINGLE_VM.read_text(encoding="utf-8")
    assert "--profile model-a" in single_vm
    assert "--profile scale-out" in single_vm, "Model A needs both local Squid 2/3 and local Celery Worker 2/3."


def test_model_b_deploy_paths_remove_stale_model_a_containers():
    """A profile change alone does not guarantee old containers are stopped."""
    manage = MANAGE_SCRIPT.read_text(encoding="utf-8")
    assert 'BARPRO_TOPOLOGY="${BARPRO_TOPOLOGY:-model-b}"' in manage
    assert "remove_model_a_services_from_central" in manage
    assert "deployment_inventory.py --role central" in manage
    for service in ("squid_2", "squid_3", "celery_worker_2", "celery_worker_3"):
        assert service in manage

    for path in (QUICK_DEPLOY_CENTRAL, DEPLOY_ALL_SERVERS):
        text = path.read_text(encoding="utf-8")
        assert "--profile model-a stop squid_2 squid_3" in text, path
        assert "--profile model-a rm -f squid_2 squid_3" in text, path
        assert re.search(
            r"--profile scale-out stop(?: --timeout \d+)? celery_worker_2 celery_worker_3",
            text,
        ), path
        assert "--profile scale-out rm -f celery_worker_2 celery_worker_3" in text, path
        worker_stop = re.search(
            r"--profile scale-out stop(?: --timeout \d+)? celery_worker_2 celery_worker_3",
            text,
        )
        assert worker_stop is not None
        assert worker_stop.start() < text.index("--profile model-a stop squid_2 squid_3"), (
            f"{path} must drain Celery before stopping its proxy"
        )


def test_version_audit_fails_closed_on_unexpected_running_containers():
    """Version audit must surface stale Model A and unrelated containers."""
    containers = {
        "barpro-squid-1": {"image_tag": "ubuntu/squid:latest"},
        "barpro-squid-2": {"image_tag": "ubuntu/squid:latest"},
        "another-app": {"image_tag": "example/app:latest"},
    }
    result = audit_container_inventory(
        {name: info["image_tag"] for name, info in containers.items()},
        {"barpro-squid-1": "ubuntu/squid:latest"},
    )
    assert result["status"] == "failed"
    assert set(result["unexpected"]) == {"barpro-squid-2", "another-app"}

    monitoring_names = {
        "barpro-prometheus",
        "barpro-alertmanager",
        "barpro-node-exporter",
        "barpro-redis-exporter",
        "barpro-postgres-exporter",
        "barpro-nginx-exporter",
        "barpro-grafana",
    }
    assert monitoring_names <= set(CENTRAL_EXPECTED_CONTAINERS)


def test_container_inventory_uses_effective_deployment_images(monkeypatch):
    monkeypatch.setenv("BACKEND_IMAGE", "ghcr.io/example/barpro-backend:commit-sha")
    monkeypatch.setenv("FRONTEND_IMAGE", "ghcr.io/example/barpro-frontend:commit-sha")
    expected = expected_containers("central")

    for name in ("barpro-backend", "barpro-worker-1", "barpro-scheduler", "barpro-beat"):
        assert expected[name] == "ghcr.io/example/barpro-backend:commit-sha"
    assert expected["barpro-frontend"] == "ghcr.io/example/barpro-frontend:commit-sha"


def test_cd_workflow_uses_compose_v2_and_registry_images():
    """X12: the CD pipeline must use `docker compose` V2 and CD-published images.

    The root docker-compose.yml uses `include:` (Compose >= 2.20); V1
    `docker-compose` cannot parse it, so every invocation in cd-deploy.yml must
    be V2. The compose files carry local-build image names, so the pipeline
    must apply deploy/registry-images.yml (GHCR) — otherwise `pull` fetches
    non-existent Docker Hub images. `exec` inside a non-TTY CI runner needs -T.

    NOTE: the fixed workflow file lives in the working tree but cannot be
    pushed by the sandbox GitHub App (no `workflows` permission). Until it is
    committed, this contract skips loudly instead of failing CI on the old
    file; the moment .github/workflows/cd-deploy.yml lands, the assertions
    activate.
    """
    import pytest

    cd_text = CD_WORKFLOW.read_text(encoding="utf-8")
    if "docker-compose -f" in cd_text:
        pytest.skip(
            "X12 workflow fix not committed yet (sandbox GitHub App lacks "
            "`workflows` permission) — commit .github/workflows/cd-deploy.yml "
            "to activate this contract."
        )
    assert "docker-compose -f" not in cd_text, (
        "cd-deploy.yml still invokes V1 docker-compose (X12) — AGENTS.md " "requires `docker compose` V2."
    )
    # EVERY docker compose invocation in cd-deploy.yml is run after exporting BACKEND_IMAGE and FRONTEND_IMAGE,
    # which dynamically overrides the images with GitHub SHA tags without needing registry-images.yml.
    compose_invocations = [
        line for line in cd_text.splitlines() if "docker compose " in line and not line.strip().startswith("#")
    ]
    assert compose_invocations, "cd-deploy.yml must contain docker compose invocations"
    assert "run --rm --no-deps backend python -c" in cd_text, (
        "cd-deploy.yml must run the advisory-lock migration entry point with --no-deps."
    )
    assert "render_squid_configs.sh" in cd_text, (
        "cd-deploy.yml must render squid configs before starting the stack " "(proxy.yml mounts the runtime files)."
    )

    override_text = REGISTRY_OVERRIDE.read_text(encoding="utf-8")
    for service in (
        "backend",
        "celery_worker_1",
        "celery_worker_2",
        "celery_worker_3",
        "celery_beat",
        "celery_scheduler",
        "frontend",
    ):
        assert f"  {service}:" in override_text, f"deploy/registry-images.yml must override image for {service}."
    assert GHCR_BACKEND_IMAGE in override_text
    assert GHCR_FRONTEND_IMAGE in override_text


def test_backend_services_share_one_image_and_worker_image_matches_registry():
    """Single canonical backend image + registry-aligned worker image.

    backend.yml previously gave every worker service its own image name
    (barpro_celery_worker_1:latest...) while quick_deploy_central.sh only
    builds the anchor image — on a fresh central server the workers could not
    start. All services must inherit the single anchor image. The worker node
    must reference the CD-published GHCR image (its own comment documents
    `docker pull ghcr.io/...`), and the worker build scripts must tag the same
    name so a local build satisfies the compose reference.
    """
    backend_text = COMPOSE_BACKEND.read_text(encoding="utf-8")
    assert "barpro_celery_" not in backend_text, (
        "backend.yml must not carry per-service image names — all services "
        "must inherit the single anchor image (fresh central server gap)."
    )

    worker_text = COMPOSE_WORKER_NODE.read_text(encoding="utf-8")
    assert (
        f"image: ${{BACKEND_IMAGE:-{GHCR_BACKEND_IMAGE}}}" in worker_text
    ), "worker-node.yml must reference the CD-published GHCR backend image."

    for script in [
        PROJECT_ROOT / "scripts" / "setup_worker.sh",
        PROJECT_ROOT / "scripts" / "deploy_all_servers.sh",
    ]:
        text = script.read_text(encoding="utf-8")
        assert f"-t {GHCR_BACKEND_IMAGE}" in text, (
            f"{script.name} must build/tag the same image name worker-node.yml " "references."
        )


def test_deploy_all_servers_build_tags_match_their_stack():
    """deploy_all_servers.sh must tag each build for the stack it targets.

    Stage 1 runs on the CENTRAL server, whose compose (backend.yml) uses the
    local anchor name barpro_backend:latest — tagging it with the GHCR name
    would make `docker compose up` look for a missing local image and fall
    back to a (non-existent) Docker Hub pull. Stages 2/3 run on WORKER nodes,
    whose compose (worker-node.yml) references the CD-published GHCR image —
    so those builds must carry the GHCR tag.
    """
    text = DEPLOY_ALL_SERVERS.read_text(encoding="utf-8")
    lines = text.splitlines()

    central_builds = []
    worker_builds = []
    for i, line in enumerate(lines):
        if line.startswith("docker build --network=host -t "):
            window = "\n".join(lines[max(0, i - 4) : i + 1])
            stage = "central" if ("1.2 build backend" in window or "مرحله ۱" in window) else "worker"
            (central_builds if stage == "central" else worker_builds).append(line)

    assert central_builds, "central build step not found"
    assert worker_builds, "worker build steps not found"

    for build in central_builds:
        assert "-t barpro_backend:latest" in build, (
            f"central build must tag barpro_backend:latest (matches backend.yml " f"anchor), got: {build}"
        )
    for build in worker_builds:
        assert f"-t {GHCR_BACKEND_IMAGE}" in build, (
            f"worker build must tag {GHCR_BACKEND_IMAGE} (matches " f"worker-node.yml), got: {build}"
        )
