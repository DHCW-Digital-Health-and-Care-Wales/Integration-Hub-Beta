from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Final

from workflow_designer import config
from workflow_designer.models import FlowDefinition

log = logging.getLogger(__name__)

DEFAULT_FLOWS: Final[list[dict[str, str | int | bool]]] = [
    {
        "flow_id": "phw-to-mpi",
        "source_system": "PHW",
        "mllp_port": 2575,
        "hl7_version": "2.5",
        "sending_app": "252",
        "validation_flow": "phw",
        "health_board": "PHW",
        "has_transformer": True,
        "transformer_image_name": "phw-hl7transformer",
        "has_dedicated_sender": False,
        "destination": "MPI",
        "readonly": True,
    },
    {
        "flow_id": "paris-to-mpi",
        "source_system": "PARIS",
        "mllp_port": 2577,
        "hl7_version": "2.5.1",
        "sending_app": "169",
        "validation_flow": "paris",
        "health_board": "PARIS",
        "has_transformer": False,
        "transformer_image_name": "",
        "has_dedicated_sender": False,
        "destination": "MPI",
        "readonly": True,
    },
    {
        "flow_id": "chemocare-to-mpi",
        "source_system": "CHEMO",
        "mllp_port": 2578,
        "hl7_version": "2.4",
        "sending_app": "245,212,192,224",
        "validation_flow": "chemo",
        "health_board": "CHEMO",
        "has_transformer": True,
        "transformer_image_name": "chemo-hl7transformer",
        "has_dedicated_sender": True,
        "destination": "MPI",
        "readonly": True,
    },
    {
        "flow_id": "pims-to-mpi",
        "source_system": "PIMS",
        "mllp_port": 2579,
        "hl7_version": "2.3.1",
        "sending_app": "PIMS",
        "validation_flow": "pims",
        "health_board": "PIMS",
        "has_transformer": True,
        "transformer_image_name": "pims-hl7transformer",
        "has_dedicated_sender": True,
        "destination": "MPI",
        "readonly": True,
    },
    {
        "flow_id": "wds-to-mpi",
        "source_system": "WDS",
        "mllp_port": 2582,
        "hl7_version": "2.5",
        "sending_app": "129",
        "validation_flow": "wds",
        "health_board": "WDS",
        "has_transformer": True,
        "transformer_image_name": "wds-hl7transformer",
        "has_dedicated_sender": False,
        "destination": "MPI",
        "readonly": True,
    },
]


class FlowStore:
    """JSON-backed flow definition store."""

    def __init__(self, json_path: str | None = None) -> None:
        self._path = Path(json_path or config.FLOWS_JSON_PATH)

    def get_all(self) -> list[FlowDefinition]:
        return sorted(self._load_all(), key=lambda flow: flow.flow_id)

    def get(self, flow_id: str) -> FlowDefinition | None:
        for flow in self._load_all():
            if flow.flow_id == flow_id:
                return flow
        return None

    def save(self, flow: FlowDefinition) -> FlowDefinition:
        flows = {existing.flow_id: existing for existing in self._load_all()}
        flows[flow.flow_id] = flow
        self._write_all(list(flows.values()))
        log.info("Saved flow definition %s", flow.flow_id)
        return flow

    def delete(self, flow_id: str) -> bool:
        flows = self._load_all()
        remaining = [flow for flow in flows if flow.flow_id != flow_id]
        if len(remaining) == len(flows):
            return False
        self._write_all(remaining)
        log.info("Deleted flow definition %s", flow_id)
        return True

    def _load_all(self) -> list[FlowDefinition]:
        self._ensure_seeded()
        with self._path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [FlowDefinition.from_dict(item) for item in data]

    def _ensure_seeded(self) -> None:
        if self._path.exists():
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        seed_flows = [FlowDefinition.from_dict(item).to_dict() for item in DEFAULT_FLOWS]
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(seed_flows, handle, indent=2)
        log.info("Seeded workflow store at %s", self._path)

    def _write_all(self, flows: list[FlowDefinition]) -> None:
        ordered_flows = sorted(flows, key=lambda item: item.flow_id)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump([flow.to_dict() for flow in ordered_flows], handle, indent=2)
