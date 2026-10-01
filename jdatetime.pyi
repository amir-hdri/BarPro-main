"""Minimal type stub for the ``jdatetime`` package (Jalali calendar).

The installed ``jdatetime`` distribution ships no ``py.typed`` marker, so mypy
reports ``import-untyped`` for it. This stub covers the API surface used by the
codebase (``jdatetime.date.fromgregorian`` / ``fromisoformat`` /
``togregorian`` / ``isoformat``). ``.pyi`` files are never imported at runtime.
"""

import datetime
from typing import Any

class date:
    @classmethod
    def fromgregorian(cls, date: datetime.date | None = ..., **kwargs: Any) -> date: ...
    @classmethod
    def fromisoformat(cls, date_string: str) -> date: ...
    def togregorian(self) -> datetime.date: ...
    def isoformat(self) -> str: ...
