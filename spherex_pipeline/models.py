from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedFilename:
    filename: str
    product: str
    planning_period: str
    large_slew_counter: str
    small_slew_counter: int
    detector: int
    instrument: str
    pipeline_level: str
    pipeline_version: str
    processing_date: str

    @property
    def observation_id(self) -> str:
        return (
            f"{self.planning_period}_{self.large_slew_counter}."
            f"{self.small_slew_counter}"
        )


@dataclass(frozen=True)
class RemoteObject:
    bucket: str
    key: str
    size_bytes: int
    etag: str
    last_modified: str
    storage_class: str | None
    checksum_algorithms: str | None
    parsed: ParsedFilename | None

    @property
    def signature(self) -> tuple[int, str, str]:
        return (self.size_bytes, self.etag, self.last_modified)
