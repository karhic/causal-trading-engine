from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Protocol

from ..models import DataEvent


class LiveDataAdapter(Protocol):
    def stream(self) -> AsyncIterable[DataEvent]: ...
