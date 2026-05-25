import contextvars
import uuid
from dataclasses import dataclass
from typing import Optional


correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")
task_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("task_id", default="-")
tenant_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="-")
batch_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("batch_id", default="-")
worker_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("worker_id", default="-")


@dataclass
class ExecutionContextTokens:
    correlation_id: contextvars.Token
    task_id: contextvars.Token
    tenant_id: contextvars.Token
    batch_id: contextvars.Token
    worker_id: contextvars.Token


@dataclass
class ExecutionContextSnapshot:
    correlation_id: str = "-"
    task_id: str = "-"
    tenant_id: str = "-"
    batch_id: str = "-"
    worker_id: str = "-"


def generate_correlation_id() -> str:
    return str(uuid.uuid4())


def bind_execution_context(
    correlation_id: Optional[str] = None,
    task_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    worker_id: Optional[str] = None,
) -> ExecutionContextTokens:
    return ExecutionContextTokens(
        correlation_id=correlation_id_ctx.set((correlation_id or "-").strip() or "-"),
        task_id=task_id_ctx.set((task_id or "-").strip() or "-"),
        tenant_id=tenant_id_ctx.set((tenant_id or "-").strip() or "-"),
        batch_id=batch_id_ctx.set((batch_id or "-").strip() or "-"),
        worker_id=worker_id_ctx.set((worker_id or "-").strip() or "-"),
    )


def reset_execution_context(tokens: ExecutionContextTokens) -> None:
    correlation_id_ctx.reset(tokens.correlation_id)
    task_id_ctx.reset(tokens.task_id)
    tenant_id_ctx.reset(tokens.tenant_id)
    batch_id_ctx.reset(tokens.batch_id)
    worker_id_ctx.reset(tokens.worker_id)


def get_execution_context() -> ExecutionContextSnapshot:
    return ExecutionContextSnapshot(
        correlation_id=correlation_id_ctx.get(),
        task_id=task_id_ctx.get(),
        tenant_id=tenant_id_ctx.get(),
        batch_id=batch_id_ctx.get(),
        worker_id=worker_id_ctx.get(),
    )

