"""Load/save Ultra7 projects as JSON files on disk."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .models import Project

DEFAULT_PROJECTS_DIR = Path.home() / ".ultra7" / "projects"

_INVALID_NAME_CHARS = re.compile(r"[^A-Za-z0-9 _-]")


def project_filename(name: str) -> str:
    """Sanitize a project name into a safe filename (no path separators)."""
    safe = _INVALID_NAME_CHARS.sub("_", name).strip()
    if not safe:
        raise ValueError("Project name must contain at least one valid character")
    return f"{safe}.json"


class ProjectStore:
    """Reads and writes project JSON files under a projects directory."""

    def __init__(self, projects_dir: Path | str = DEFAULT_PROJECTS_DIR) -> None:
        self.projects_dir = Path(projects_dir)

    def ensure_dir(self) -> None:
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> list[str]:
        """Return project names found on disk, sorted alphabetically."""
        self.ensure_dir()
        return sorted(p.stem for p in self.projects_dir.glob("*.json"))

    def load(self, name: str) -> Project:
        path = self.projects_dir / project_filename(name)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return Project.from_dict(data)

    def save(self, project: Project) -> None:
        """Write the project atomically (temp file + rename) to avoid corruption."""
        self.ensure_dir()
        path = self.projects_dir / project_filename(project.name)
        tmp_path = path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(project.to_dict(), f, indent=2)
        os.replace(tmp_path, path)

    def delete(self, name: str) -> None:
        path = self.projects_dir / project_filename(name)
        path.unlink(missing_ok=True)

    def exists(self, name: str) -> bool:
        return (self.projects_dir / project_filename(name)).exists()
