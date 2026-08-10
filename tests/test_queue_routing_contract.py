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

import re
from pathlib import Path
from unittest.mock import patch

from app.core.circuit_breaker import get_available_ip_indices, get_routed_queue

COMPOSE_DIR = Path(__file__).resolve().parent.parent / "compose"
COMPOSE_BACKEND = COMPOSE_DIR / "backend.yml"
COMPOSE_WORKER_NODE = COMPOSE_DIR / "worker-node.yml"

# Every compose file that can declare a concrete ``WORKER_IP_INDEX: <n>``.
# ``compose/worker-node.yml`` only uses the ``${WORKER_IP_INDEX}`` placeholder,
# so it contributes no concrete index itself — its template contract is pinned
# separately by ``test_worker_node_template_consumes_its_own_partitions``.
COMPOSE_FILES = sorted(
    [
        *COMPOSE_DIR.glob("*.yml"),
        Path(__file__).resolve().parent.parent / "docker-compose.yml",
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


def _consumed_queues() -> set[str]:
    """Parse every queue named in a ``-Q`` argument in compose/backend.yml."""
    text = COMPOSE_BACKEND.read_text(encoding="utf-8")
    consumed: set[str] = set()

    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() != "- -Q":
            continue
        # The queue list is the next non-empty list item.
        for candidate in lines[i + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                continue
            queue_csv = stripped.removeprefix("- ").strip()
            consumed.update(q.strip() for q in queue_csv.split(",") if q.strip())
            break

    return consumed


def _routed_ip_indices() -> list[int]:
    """The live routing pool — the real ``get_available_ip_indices()`` output.

    This is the anti-blindspot core: the routing tests must never hardcode the
    index set, or a drift between ``AVAILABLE_IP_INDICES`` and the compose
    fleet goes unnoticed. An empty pool raises a clear error instead of letting
    the routing tests pass vacuously.
    """
    indices = get_available_ip_indices()
    assert indices, (
        "AVAILABLE_IP_INDICES resolved to an empty index pool — the dispatcher "
        "cannot route to any worker queue. Check the AVAILABLE_IP_INDICES "
        "environment variable (e.g. AVAILABLE_IP_INDICES='1,2,3')."
    )
    return indices


def _worker_ip_indices_by_file() -> dict[int, list[str]]:
    """Map every concrete ``WORKER_IP_INDEX: <n>`` declared in the compose files.

    Only literal numeric values are collected; template placeholders such as
    ``${WORKER_IP_INDEX}`` (compose/worker-node.yml) carry no fleet information
    by themselves and are skipped. Quoted YAML scalars (``"3"`` / ``'3'``) and
    trailing inline comments (``3 # third worker``) are accepted so a trivial
    formatting change can never silently disable the P0-1 guard. The returned
    dict maps each declared index to the names of the files that declare it,
    for actionable failure output.
    """
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


def _routed_targets(base_queue: str) -> set[str]:
    """All queue names get_routed_queue() can produce for a base queue.

    The index set comes from the real ``get_available_ip_indices()`` — never
    from a hardcoded tuple — so the consumer contract is checked against the
    actual routing pool. Only the per-call selector (which does Redis I/O) is
    stubbed.
    """
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
    """The routing pool must never be empty.

    A broken ``AVAILABLE_IP_INDICES`` (unset to an empty value, or garbage)
    would otherwise let every routing test pass vacuously and mask the P0-1
    drift this module exists to catch.
    """
    indices = get_available_ip_indices()
    assert indices, (
        "get_available_ip_indices() returned an empty pool. Fix the "
        "AVAILABLE_IP_INDICES environment variable before running the routing "
        "contract tests."
    )


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
    """Explicit guard for the exact queue family that regressed."""
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


def test_every_worker_ip_index_is_available():
    """P0-1 guard: every worker declared in compose must be routable.

    The dispatcher round-robins only over ``get_available_ip_indices()`` (i.e.
    ``AVAILABLE_IP_INDICES``). If a compose file still declares a worker whose
    ``WORKER_IP_INDEX`` is missing from that list — e.g.
    ``AVAILABLE_IP_INDICES="1,2"`` while ``celery_worker_3`` keeps
    ``WORKER_IP_INDEX: 3`` — the worker consumes queues the dispatcher never
    sends to and idles forever (P0-1), with no error anywhere.

    This test reads the *real* ``get_available_ip_indices()`` output (never
    mocked) and fails with an explicit message on any mismatch, so the bug is
    caught in CI the moment the fleet and the environment drift apart.
    """
    available = set(get_available_ip_indices())
    declared = _worker_ip_indices_by_file()

    assert declared, "no concrete WORKER_IP_INDEX values parsed from compose files"

    orphaned = {idx: files for idx, files in declared.items() if idx not in available}
    assert not orphaned, (
        "Worker fleet ↔ AVAILABLE_IP_INDICES drift (P0-1): these WORKER_IP_INDEX "
        f"values are declared in Docker Compose {orphaned} but are missing from "
        f"the real AVAILABLE_IP_INDICES output ({sorted(available)}). The "
        "dispatcher only routes to get_available_ip_indices(), so the affected "
        "worker(s) consume queues that are never dispatched to and stay idle "
        "forever. Either add the missing index(es) to AVAILABLE_IP_INDICES or "
        "remove/retire the worker service from the compose file."
    )


def test_worker_node_template_consumes_its_own_partitions():
    """The remote worker template must consume its ${WORKER_IP_INDEX} partitions.

    The partition suffix must be the numeric IP index (WORKER_IP_INDEX), NOT the
    registry identity (WORKER_ID). get_routed_queue() suffixes with the numeric
    IP index from AVAILABLE_IP_INDICES (waybill_tasks_2, ...), so a template
    consuming waybill_tasks_${WORKER_ID} with WORKER_ID="worker_4" would create
    waybill_tasks_worker_4 — which nobody dispatches to.
    """
    text = COMPOSE_WORKER_NODE.read_text(encoding="utf-8")

    q_match = re.search(r"-Q\s+(\S+)", text)
    assert q_match, "no -Q argument found in compose/worker-node.yml"
    queues = {q.strip() for q in q_match.group(1).split(",")}

    for base in ROUTED_BASE_QUEUES:
        expected = f"{base}_${{WORKER_IP_INDEX}}"
        assert (
            expected in queues
        ), f"worker-node.yml does not consume {expected}; a remote worker would never receive routed {base} tasks."
