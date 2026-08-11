from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    """Logical data contract independent of the vendor that supplies it."""

    name: str
    frequency: str
    timezone: str
    price_semantics: str = "unspecified"
    adjustment: str = "raw"
    session: str = "provider"
    fields: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)


class DataCatalog:
    def __init__(self) -> None:
        self._specs: dict[str, DatasetSpec] = {}

    def register(self, spec: DatasetSpec) -> None:
        existing = self._specs.get(spec.name)
        if existing is not None and existing != spec:
            raise ValueError(f"dataset {spec.name!r} already registered with different semantics")
        self._specs[spec.name] = spec

    def get(self, name: str) -> DatasetSpec:
        return self._specs[name]
