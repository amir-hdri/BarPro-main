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

These tests pin the contract: every queue the code can dispatch to must appear
in some worker's ``-Q`` list.
"""

from __future__ import annotations

import re
from pathlib import Path

from unittest.mock import patch

from app.core.circuit_breaker import get_routed_queue

COMPOSE_BACKEND = Path(__file__).resolve().parent.parent / "compose" / "backend.yml"

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

IP_INDICES = (1, 2, 3)


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


def _routed_targets(base_queue: str) -> set[str]:
    """All queue names get_routed_queue() can produce for a base queue."""
    targets: set[str] = set()
    for idx in IP_INDICES:
        with patch("app.core.circuit_breaker.get_next_ip_index_sync", return_value=idx):
            targets.add(get_routed_queue(base_queue))
    return targets


def test_compose_defines_worker_queues():
    """Sanity check that the compose parsing found something at all."""
    consumed = _consumed_queues()
    assert consumed, "no -Q queues parsed from compose/backend.yml"
    assert "waybill_tasks" in consumed


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
    for idx in IP_INDICES:
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


def test_worker_node_template_consumes_its_own_partitions():
    """The remote worker template must consume its ${WORKER_ID} partitions."""
    template = COMPOSE_BACKEND.parent / "worker-node.yml"
    text = template.read_text(encoding="utf-8")

    q_match = re.search(r"-Q\s+(\S+)", text)
    assert q_match, "no -Q argument found in compose/worker-node.yml"
    queues = {q.strip() for q in q_match.group(1).split(",")}

    for base in ROUTED_BASE_QUEUES:
        expected = f"{base}_${{WORKER_ID}}"
        assert expected in queues, (
            f"worker-node.yml does not consume {expected}; a remote worker "
            f"would never receive routed {base} tasks."
        )
