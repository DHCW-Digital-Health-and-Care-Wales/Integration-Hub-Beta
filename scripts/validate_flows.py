"""Validate topology/flows.yaml for structure, references, and cycle safety."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


ALLOWED_TRANSPORTS: frozenset[str] = frozenset(
    {
        "servicebus_queue",
        "servicebus_topic",
        "mllp",
        "http",
    }
)


class FlowValidationError(Exception):
    """Raised when topology validation fails."""


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load topology YAML file into a dictionary."""
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise FlowValidationError(
            "PyYAML is required to validate topology files. Install with: pip install pyyaml"
        ) from exc

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FlowValidationError(f"Failed to read file: {path}") from exc

    try:
        data = yaml.safe_load(content)
    except Exception as exc:
        raise FlowValidationError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise FlowValidationError("Top-level YAML structure must be a mapping/object")

    return data


def _require_list_of_dicts(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Require a list of dictionaries at payload[key]."""
    value = payload.get(key)
    if not isinstance(value, list):
        raise FlowValidationError(f"'{key}' must be a list")

    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise FlowValidationError(f"'{key}[{index}]' must be an object")
        result.append(item)

    return result


def _check_schema(payload: dict[str, Any]) -> None:
    """Validate schema-level fields."""
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, int):
        raise FlowValidationError("'schema_version' must be an integer")

    allow_cycles = payload.get("allow_cycles", False)
    if not isinstance(allow_cycles, bool):
        raise FlowValidationError("'allow_cycles' must be a boolean when provided")


def _build_node_index(nodes: list[dict[str, Any]]) -> set[str]:
    """Validate node identity and return all node ids."""
    node_ids: set[str] = set()

    for index, node in enumerate(nodes):
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise FlowValidationError(f"nodes[{index}].id must be a non-empty string")
        if node_id in node_ids:
            raise FlowValidationError(f"Duplicate node id: {node_id}")
        node_ids.add(node_id)

    return node_ids


def _validate_edges(edges: list[dict[str, Any]], node_ids: set[str]) -> dict[str, list[str]]:
    """Validate edge structure and return adjacency map for graph checks."""
    edge_ids: set[str] = set()
    adjacency: dict[str, list[str]] = defaultdict(list)

    for index, edge in enumerate(edges):
        edge_id = edge.get("id")
        if not isinstance(edge_id, str) or not edge_id:
            raise FlowValidationError(f"edges[{index}].id must be a non-empty string")
        if edge_id in edge_ids:
            raise FlowValidationError(f"Duplicate edge id: {edge_id}")
        edge_ids.add(edge_id)

        source = edge.get("from")
        target = edge.get("to")
        if not isinstance(source, str) or not source:
            raise FlowValidationError(f"edges[{index}].from must be a non-empty string")
        if not isinstance(target, str) or not target:
            raise FlowValidationError(f"edges[{index}].to must be a non-empty string")

        if source not in node_ids:
            raise FlowValidationError(f"edges[{index}].from references unknown node: {source}")
        if target not in node_ids:
            raise FlowValidationError(f"edges[{index}].to references unknown node: {target}")

        transport = edge.get("transport")
        if not isinstance(transport, str) or transport not in ALLOWED_TRANSPORTS:
            allowed = ", ".join(sorted(ALLOWED_TRANSPORTS))
            raise FlowValidationError(
                f"edges[{index}].transport must be one of: {allowed}"
            )

        workflow = edge.get("workflow")
        if not isinstance(workflow, str) or not workflow:
            raise FlowValidationError(f"edges[{index}].workflow must be a non-empty string")

        if transport in {"servicebus_queue", "servicebus_topic"}:
            channel = edge.get("channel")
            if not isinstance(channel, str) or not channel:
                raise FlowValidationError(
                    f"edges[{index}] with transport {transport} must define 'channel'"
                )

        if transport == "mllp":
            host = edge.get("host")
            port = edge.get("port")
            if not isinstance(host, str) or not host:
                raise FlowValidationError("MLLP edge must define non-empty 'host'")
            if not isinstance(port, int) or port <= 0:
                raise FlowValidationError("MLLP edge must define positive integer 'port'")

        adjacency[source].append(target)

    return adjacency


def _validate_views(views: list[dict[str, Any]], node_ids: set[str]) -> None:
    """Validate optional view definitions for diagram subsets."""
    view_ids: set[str] = set()

    for index, view in enumerate(views):
        view_id = view.get("id")
        if not isinstance(view_id, str) or not view_id:
            raise FlowValidationError(f"views[{index}].id must be a non-empty string")
        if view_id in view_ids:
            raise FlowValidationError(f"Duplicate view id: {view_id}")
        view_ids.add(view_id)

        include_nodes = view.get("include_nodes")
        if not isinstance(include_nodes, list) or not include_nodes:
            raise FlowValidationError(
                f"views[{index}].include_nodes must be a non-empty list"
            )

        for node in include_nodes:
            if not isinstance(node, str) or node not in node_ids:
                raise FlowValidationError(
                    f"views[{index}].include_nodes references unknown node: {node}"
                )


def _has_cycle(node_ids: set[str], adjacency: dict[str, list[str]]) -> bool:
    """Detect whether a directed graph contains a cycle using Kahn's algorithm."""
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}

    for source, targets in adjacency.items():
        if source not in indegree:
            continue
        for target in targets:
            indegree[target] += 1

    queue: deque[str] = deque(node for node, degree in indegree.items() if degree == 0)
    visited_count = 0

    while queue:
        node = queue.popleft()
        visited_count += 1
        for target in adjacency.get(node, []):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    return visited_count != len(node_ids)


def validate_topology(path: Path) -> None:
    """Validate a topology file and raise FlowValidationError on failure."""
    payload = _load_yaml_file(path)
    _check_schema(payload)

    nodes = _require_list_of_dicts(payload, "nodes")
    edges = _require_list_of_dicts(payload, "edges")
    views = _require_list_of_dicts(payload, "views") if "views" in payload else []

    node_ids = _build_node_index(nodes)
    adjacency = _validate_edges(edges, node_ids)
    _validate_views(views, node_ids)

    allow_cycles = bool(payload.get("allow_cycles", False))
    if not allow_cycles and _has_cycle(node_ids, adjacency):
        raise FlowValidationError(
            "Cycle detected in topology graph while allow_cycles is false"
        )


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the validator."""
    parser = argparse.ArgumentParser(description="Validate integration flow topology")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("topology/flows.yaml"),
        help="Path to topology yaml file (default: topology/flows.yaml)",
    )
    return parser.parse_args()


def main() -> int:
    """Run topology validation and return process exit code."""
    args = _parse_args()

    try:
        validate_topology(args.file)
    except FlowValidationError as exc:
        print(f"Topology validation failed: {exc}")
        return 1

    print(f"Topology validation passed: {args.file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
