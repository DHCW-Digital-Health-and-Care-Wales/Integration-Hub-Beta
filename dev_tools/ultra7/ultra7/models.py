"""Data model for Ultra7 projects, endpoints, and messages."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

MessageFormat = Literal["hl7", "xml", "json"]
EndpointKind = Literal["mllp", "rest", "soap"]
MllpMode = Literal["per_message", "stream", "pipelined"]
IterationMode = Literal["increment", "list", "timestamp", "nhs_number"]


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class IterationSpec:
    """Describes a highlighted substring of a message that changes on each repeat send.

    `start`/`end` are character offsets into `Message.content` (end exclusive).
    """

    start: int
    end: int
    mode: IterationMode = "increment"
    step: int = 1
    """Increment mode: amount added to the parsed integer per send."""
    pad_width: int = 0
    """Increment mode: zero-pad the result to this width; 0 preserves the original width."""
    values: list[str] = field(default_factory=list)
    """List mode: values cycled through in order, one per send."""
    timestamp_format: str = "%Y%m%d%H%M%S"
    """Timestamp mode: strftime format used to generate the replacement value."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "mode": self.mode,
            "step": self.step,
            "pad_width": self.pad_width,
            "values": list(self.values),
            "timestamp_format": self.timestamp_format,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IterationSpec:
        return cls(
            start=data["start"],
            end=data["end"],
            mode=data.get("mode", "increment"),
            step=data.get("step", 1),
            pad_width=data.get("pad_width", 0),
            values=list(data.get("values", [])),
            timestamp_format=data.get("timestamp_format", "%Y%m%d%H%M%S"),
        )


@dataclass
class Message:
    """A single test message that can be loaded into a project."""

    name: str
    format: MessageFormat
    content: str
    id: str = field(default_factory=_new_id)
    iteration: IterationSpec | None = None
    """Primary iteration field (kept in sync with `iterations[0]` for backwards compatibility)."""
    iterations: list[IterationSpec] = field(default_factory=list)
    """All marked iteration fields that get recomputed on each repeat send."""
    enabled: bool = True
    """Whether this message is included in batch (Send) runs; disabled messages are skipped."""

    def __post_init__(self) -> None:
        if self.iteration is not None and not self.iterations:
            self.iterations = [self.iteration]
        elif self.iterations and self.iteration is None:
            self.iteration = self.iterations[0]

    def all_iterations(self) -> list[IterationSpec]:
        """Return all configured iteration specs (synced with legacy single `iteration`)."""
        if self.iterations:
            return list(self.iterations)
        return [self.iteration] if self.iteration is not None else []

    def set_iterations(self, specs: list[IterationSpec]) -> None:
        self.iterations = sorted(specs, key=lambda s: s.start)
        self.iteration = self.iterations[0] if self.iterations else None

    def to_dict(self) -> dict[str, Any]:
        specs = self.all_iterations()
        return {
            "id": self.id,
            "name": self.name,
            "format": self.format,
            "content": self.content,
            "iteration": specs[0].to_dict() if specs else None,
            "iterations": [s.to_dict() for s in specs],
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        iterations_data = data.get("iterations")
        if isinstance(iterations_data, list) and iterations_data:
            specs = [IterationSpec.from_dict(item) for item in iterations_data]
            return cls(
                id=data.get("id", _new_id()),
                name=data["name"],
                format=data["format"],
                content=data["content"],
                iteration=specs[0],
                iterations=specs,
                enabled=data.get("enabled", True),
            )
        iteration_data = data.get("iteration")
        spec = IterationSpec.from_dict(iteration_data) if iteration_data else None
        return cls(
            id=data.get("id", _new_id()),
            name=data["name"],
            format=data["format"],
            content=data["content"],
            iteration=spec,
            iterations=[spec] if spec else [],
            enabled=data.get("enabled", True),
        )


@dataclass
class Endpoint:
    """Connection details for the target being tested."""

    kind: EndpointKind = "mllp"
    host: str = ""
    port: int | None = None
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    soap_action: str = ""
    timeout_seconds: float = 5.0
    mllp_mode: MllpMode = "per_message"

    @property
    def is_configured(self) -> bool:
        """Return True if this endpoint has the minimum connection details required to send."""
        if self.kind == "mllp":
            return bool(self.host.strip() and self.port is not None and 1 <= self.port <= 65535)
        url = self.url.strip()
        scheme, sep, rest = url.partition("://")
        return bool(sep and scheme.lower() in ("http", "https") and rest.strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "host": self.host,
            "port": self.port,
            "url": self.url,
            "headers": dict(self.headers),
            "soap_action": self.soap_action,
            "timeout_seconds": self.timeout_seconds,
            "mllp_mode": self.mllp_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Endpoint:
        raw_mode = data.get("mllp_mode", "per_message")
        mllp_mode: MllpMode = raw_mode if raw_mode in ("per_message", "stream", "pipelined") else "per_message"
        return cls(
            kind=data.get("kind", "mllp"),
            host=data.get("host", ""),
            port=data.get("port"),
            url=data.get("url", ""),
            headers=dict(data.get("headers", {})),
            soap_action=data.get("soap_action", ""),
            timeout_seconds=data.get("timeout_seconds", 5.0),
            mllp_mode=mllp_mode,
        )


@dataclass
class Project:
    """A named collection of messages and an endpoint, persisted to disk."""

    name: str
    endpoint: Endpoint = field(default_factory=Endpoint)
    messages: list[Message] = field(default_factory=list)
    repeat_count: int = 1
    delay_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "endpoint": self.endpoint.to_dict(),
            "messages": [m.to_dict() for m in self.messages],
            "repeat_count": self.repeat_count,
            "delay_ms": self.delay_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        return cls(
            name=data["name"],
            endpoint=Endpoint.from_dict(data.get("endpoint", {})),
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            repeat_count=data.get("repeat_count", 1),
            delay_ms=data.get("delay_ms", 0),
        )
