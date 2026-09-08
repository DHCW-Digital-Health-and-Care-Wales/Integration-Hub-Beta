"""Resolve (HL7 version, message structure) -> XSD path.

Scans ``schemas/<version>/`` (standard, default) and ``custom_schemas/<version>/`` (used only for the
specific structures that actually have a custom schema) once, indexing by directory scan + filename
normalisation rather than a hard-coded format string - the two trees use different filename
conventions today ("{version}_{structure}.xsd" vs "{structure}_{version}.xsd", see design report
section 2.1), so a template-formatted path would get one of them wrong.

Custom schemas are **not** a priority/override tier over standard ones (confirmed decision, design
report section 7.2): a custom schema is always named differently from its official counterpart, so
there is no filename collision to arbitrate. Checking the custom index first and falling back to the
standard index is equivalent to "only use custom where it's actually needed", since presence in
custom_schemas/ for a given (version, structure) is itself the signal that a custom schema is required.

If neither index has an entry, ``SchemaNotFoundError`` is raised - there is no flat/best-effort
fallback (confirmed decision, design report section 7.3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from .exceptions import SchemaNotFoundError

_NON_STRUCTURE_STEMS = {"fields", "segments", "types"}


def normalize_version(raw_version: str) -> str:
    """Normalise a raw MSH-12.1 value (e.g. "2.5.1") to a schema folder key (e.g. "2_5_1")."""
    return raw_version.strip().replace(".", "_")


def _structure_from_standard_filename(version_key: str, stem: str) -> Optional[str]:
    """"{version}_{structure}.xsd", e.g. "2_5_1_ADT_A05" -> "ADT_A05"."""
    prefix = f"{version_key}_"
    if not stem.startswith(prefix):
        return None
    remainder = stem[len(prefix) :]
    if not remainder or remainder in _NON_STRUCTURE_STEMS:
        return None
    return remainder


def _structure_from_custom_filename(version_key: str, stem: str) -> Optional[str]:
    """"{structure}_{version}.xsd", e.g. "ORU_R01_2_5_1" -> "ORU_R01"."""
    suffix = f"_{version_key}"
    if not stem.endswith(suffix):
        return None
    remainder = stem[: -len(suffix)]
    return remainder or None


class SchemaResolver:
    """Resolves (version, structure) -> XSD path, indexing ``schemas_dir``/``custom_schemas_dir`` lazily."""

    def __init__(self, schemas_dir: Path, custom_schemas_dir: Path) -> None:
        self._schemas_dir = schemas_dir
        self._custom_schemas_dir = custom_schemas_dir
        self._standard_index: Optional[Dict[Tuple[str, str], Path]] = None
        self._custom_index: Optional[Dict[Tuple[str, str], Path]] = None

    @staticmethod
    def _build_index(
        root_dir: Path, structure_from_filename: Callable[[str, str], Optional[str]]
    ) -> Dict[Tuple[str, str], Path]:
        index: Dict[Tuple[str, str], Path] = {}
        if not root_dir.is_dir():
            return index
        for version_dir in root_dir.iterdir():
            if not version_dir.is_dir():
                continue
            version_key = version_dir.name
            for xsd_path in version_dir.glob("*.xsd"):
                structure = structure_from_filename(version_key, xsd_path.stem)
                if structure:
                    index[(version_key, structure)] = xsd_path
        return index

    def _standard(self) -> Dict[Tuple[str, str], Path]:
        if self._standard_index is None:
            self._standard_index = self._build_index(self._schemas_dir, _structure_from_standard_filename)
        return self._standard_index

    def _custom(self) -> Dict[Tuple[str, str], Path]:
        if self._custom_index is None:
            self._custom_index = self._build_index(self._custom_schemas_dir, _structure_from_custom_filename)
        return self._custom_index

    def resolve(self, version: str, structure: str) -> Path:
        version_key = normalize_version(version)

        custom_path = self._custom().get((version_key, structure))
        if custom_path is not None:
            return custom_path

        standard_path = self._standard().get((version_key, structure))
        if standard_path is not None:
            return standard_path

        raise SchemaNotFoundError(
            f"No schema found for HL7 version '{version}' (normalised '{version_key}') and structure "
            f"'{structure}' under {self._schemas_dir} or {self._custom_schemas_dir}"
        )


_PACKAGE_ROOT = Path(__file__).resolve().parent
_DEFAULT_SCHEMAS_DIR = _PACKAGE_ROOT / "schemas"
_DEFAULT_CUSTOM_SCHEMAS_DIR = _PACKAGE_ROOT / "custom_schemas"

default_resolver = SchemaResolver(_DEFAULT_SCHEMAS_DIR, _DEFAULT_CUSTOM_SCHEMAS_DIR)


def resolve_schema_path(version: str, structure: str, resolver: Optional[SchemaResolver] = None) -> Path:
    """Resolve the XSD path for (version, structure) using ``resolver`` (defaults to the package's
    own ``schemas/``/``custom_schemas/`` directories).
    """
    return (resolver or default_resolver).resolve(version, structure)
