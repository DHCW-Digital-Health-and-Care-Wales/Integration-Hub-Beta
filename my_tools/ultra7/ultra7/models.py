"""Data model for Ultra7 projects, endpoints, and messages."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

MessageFormat = Literal["hl7", "xml", "json"]
EndpointKind = Literal["mllp", "rest", "soap"]
IterationMode = Literal["increment", "list", "timestamp"]


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
    """The highlighted substring (if any) that gets recomputed on each repeat send."""
    enabled: bool = True
    """Whether this message is included in batch (Send) runs; disabled messages are skipped."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "format": self.format,
            "content": self.content,
            "iteration": self.iteration.to_dict() if self.iteration else None,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        iteration_data = data.get("iteration")
        return cls(
            id=data.get("id", _new_id()),
            name=data["name"],
            format=data["format"],
            content=data["content"],
            iteration=IterationSpec.from_dict(iteration_data) if iteration_data else None,
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "host": self.host,
            "port": self.port,
            "url": self.url,
            "headers": dict(self.headers),
            "soap_action": self.soap_action,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Endpoint:
        return cls(
            kind=data.get("kind", "mllp"),
            host=data.get("host", ""),
            port=data.get("port"),
            url=data.get("url", ""),
            headers=dict(data.get("headers", {})),
            soap_action=data.get("soap_action", ""),
            timeout_seconds=data.get("timeout_seconds", 5.0),
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
