#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Apply automatic fixes for the findings in a quality_report.py JSON report.

Dry run by default: prints the plan and changes nothing until --apply is given.
Standard library only (like quality_report.py), so it runs anywhere `uv` does.
Full documentation and examples: dev_tools/scripts/quality_fix.md

Usage:
    dev_tools/scripts/quality_fix.py --safe                         # show what the safe fixers would do
    dev_tools/scripts/quality_fix.py --safe --apply --recheck        # apply them, then re-run affected checks
    dev_tools/scripts/quality_fix.py --audit-pin --apply shared_libs/otel_lib
    dev_tools/scripts/quality_fix.py --triage dev_tools/reports/triage.md
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import logging
import re
import sys
import tokenize
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, NamedTuple, Optional, Sequence, Set, Tuple, Union

import quality_report as qr

LOG = logging.getLogger("quality_fix")

ROOT_DIR = qr.ROOT_DIR
DEFAULT_REPORT = qr.DEFAULT_OUTPUT.with_suffix(".json")
RECHECK_OUTPUT = qr.DEFAULT_OUTPUT.with_name("quality-report-recheck.html")

# Line-based edits run first, while the report's line numbers are still valid; every later phase may move lines.
PHASE_LINES, PHASE_RUFF, PHASE_MANIFEST, PHASE_LOCK, PHASE_FORMAT = 1, 2, 3, 4, 5
PHASE_LABELS = {
    PHASE_LINES: "Source edits",
    PHASE_RUFF: "Ruff fixes",
    PHASE_MANIFEST: "pyproject.toml edits",
    PHASE_LOCK: "Lock file updates",
    PHASE_FORMAT: "Formatting",
}

# Which quality_report.py check groups to re-run after each fixer.
RECHECK_GROUPS: Dict[str, Tuple[str, ...]] = {
    "ruff": ("ruff",),
    "format": ("ruff",),
    "unused-ignores": ("mypy",),
    "annotate-none": ("mypy",),
    "bandit-timeouts": ("security",),
    "baseline": ("mypy", "security"),
    "audit": ("security",),
    "audit-pin": ("security",),
    "audit-transitive": ("security",),
    "audit-override": ("security",),
}

NONE_HINT = 'Use "-> None" if function does not return a value'
TYPE_IGNORE_RE = re.compile(r"#\s*type:\s*ignore(?:\[(?P<codes>[^\]]*)\])?")
NOSEC_RE = re.compile(r"#\s*nosec\b:?(?P<ids>(?:\s*,?\s*[A-Z]\d{3})*)")
BANDIT_ID_RE = re.compile(r"[A-Z]\d{3}")
UNUSED_CODES_RE = re.compile(r"ignore\[(?P<codes>[^\]]+)\]")
LOCATION_RE = re.compile(r"^(?P<path>[^:]+\.py):(?P<line>\d+)(?::\d+)?$")
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "request"})

NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
FINAL_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")
RELEASE_PREFIX_RE = re.compile(r"^v?(\d+(?:\.\d+)*)")
REQUIREMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)\s*(?P<extras>\[[^\]]*\])?\s*"
    r"(?P<spec>[^;@]*?)\s*(?P<marker>;.*)?$",
    re.DOTALL,
)
CLAUSE_RE = re.compile(r"^\s*(?P<op>~=|===|==|!=|<=|>=|<|>)\s*(?P<version>[^\s,]+)\s*$")


class FixError(Exception):
    """A single fix could not be applied; the rest of the run carries on."""


@dataclass(frozen=True)
class ReportFinding:
    check: str
    component: str
    location: str
    code: str
    message: str
    severity: str
    detail: str = ""
    url: str = ""
    meta: Tuple[Tuple[str, str], ...] = ()

    def meta_value(self, key: str) -> str:
        return dict(self.meta).get(key, "")


@dataclass
class Report:
    path: Path
    meta: Dict[str, str]
    results: List[Dict[str, Any]]
    findings: List[ReportFinding]


@dataclass
class Action:
    phase: int
    fixer: str
    component: str
    description: str
    run: Callable[[], str]
    findings: Tuple[ReportFinding, ...] = ()


@dataclass
class Plan:
    actions: List[Action] = field(default_factory=list)
    claimed: Set[ReportFinding] = field(default_factory=set)
    skipped: List[Tuple[ReportFinding, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def merge(self, other: Plan) -> None:
        self.actions.extend(other.actions)
        self.claimed |= other.claimed
        self.skipped.extend(other.skipped)
        self.notes.extend(other.notes)


@dataclass
class Options:
    ruff: bool = False
    ruff_unsafe: bool = False
    format: bool = False
    audit: bool = False
    audit_pin: bool = False
    audit_transitive: bool = False
    audit_override: bool = False
    allow_major: bool = False
    unused_ignores: bool = False
    annotate_none: bool = False
    bandit_timeouts: bool = False
    timeout_seconds: int = 30
    baseline: bool = False

    def selected(self) -> List[str]:
        names = {
            "ruff": self.ruff, "format": self.format, "audit": self.audit, "audit-pin": self.audit_pin,
            "audit-transitive": self.audit_transitive, "audit-override": self.audit_override,
            "unused-ignores": self.unused_ignores, "annotate-none": self.annotate_none,
            "bandit-timeouts": self.bandit_timeouts, "baseline": self.baseline,
        }
        return [name for name, enabled in names.items() if enabled]


# --------------------------------------------------------------------------------------------------
# Report loading
# --------------------------------------------------------------------------------------------------

def load_report(path: Path, components: Optional[Set[str]] = None) -> Report:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = [r for r in data.get("results", []) if components is None or r.get("component") in components]
    findings = []
    for result in results:
        for raw in result.get("findings") or []:
            findings.append(ReportFinding(
                check=result.get("check", ""),
                component=result.get("component", ""),
                location=raw.get("location", ""),
                code=raw.get("code", ""),
                message=raw.get("message", ""),
                severity=raw.get("severity", ""),
                detail=raw.get("detail", ""),
                url=raw.get("url", ""),
                meta=tuple(sorted((str(k), str(v)) for k, v in (raw.get("meta") or {}).items())),
            ))
    return Report(path=path, meta=data.get("meta", {}), results=results, findings=findings)


def source_location(finding: ReportFinding, root: Path) -> Tuple[Path, int]:
    """Resolve a finding's `path:line[:col]` to a Python file inside the repo (never outside it)."""
    match = LOCATION_RE.match(finding.location)
    if not match:
        raise FixError(f"unsupported location {finding.location!r}")
    path = (root / match["path"]).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise FixError(f"{match['path']} is not a file in the repo")
    return path, int(match["line"])


# --------------------------------------------------------------------------------------------------
# Source editing helpers
# --------------------------------------------------------------------------------------------------

def _read_lines(path: Path) -> List[str]:
    # Bytes round-trip keeps the file's own line endings on every platform.
    return path.read_bytes().decode("utf-8").splitlines(keepends=True)


def _write_validated(path: Path, original: List[str], updated: List[str]) -> None:
    if len(updated) != len(original):
        raise FixError("edit would change the line count")
    text = "".join(updated)
    try:
        ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        raise FixError(f"edit would break syntax ({exc.msg}); left unchanged") from exc
    path.write_bytes(text.encode("utf-8"))


def _line(lines: List[str], line_no: int) -> Tuple[str, str]:
    if not 1 <= line_no <= len(lines):
        raise FixError(f"line {line_no} is past the end of the file (report out of date?)")
    raw = lines[line_no - 1]
    body = raw.rstrip("\r\n")
    return body, raw[len(body):]


class LineInfo(NamedTuple):
    comments: Dict[int, int]
    no_append: Set[int]


def line_info(text: str) -> LineInfo:
    """Map each row to its comment column, and find rows where a trailing comment would land inside a string."""
    comments: Dict[int, int] = {}
    no_append: Set[int] = set()
    string_starts = {tokenize.FSTRING_START, getattr(tokenize, "TSTRING_START", tokenize.FSTRING_START)}
    string_ends = {tokenize.FSTRING_END, getattr(tokenize, "TSTRING_END", tokenize.FSTRING_END)}
    open_rows: List[int] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                comments[tok.start[0]] = tok.start[1]
            elif tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                no_append.update(range(tok.start[0], tok.end[0]))
            elif tok.type in string_starts:
                open_rows.append(tok.start[0])
            elif tok.type in string_ends and open_rows:
                no_append.update(range(open_rows.pop(), tok.end[0]))
    except (tokenize.TokenError, SyntaxError) as exc:
        raise FixError(f"cannot tokenize file: {exc}") from exc
    return LineInfo(comments, no_append)


def _split_comment(body: str, col: Optional[int]) -> Tuple[str, str]:
    return (body, "") if col is None else (body[:col], body[col:])


def _join_comments(code: str, *comments: str) -> str:
    parts = []
    for comment in comments:
        text = comment.strip()
        if text and text != "#":
            parts.append(text if text.startswith("#") else f"# {text}")
    if not parts:
        return code.rstrip()
    if not code.strip():
        return code + "  ".join(parts)
    return code.rstrip() + "  " + "  ".join(parts)


def _remove_spans(text: str, spans: Iterable[Tuple[int, int]]) -> str:
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + " " + text[end:]
    return re.sub(r"\s{3,}#", "  #", text)


def _codes(text: Optional[str]) -> List[str]:
    return [c.strip() for c in (text or "").split(",") if c.strip()]


def _merge(existing: Sequence[str], new: Sequence[str]) -> List[str]:
    return list(dict.fromkeys([*existing, *new]))


def _char_col(line: str, byte_col: int) -> int:
    """ast column offsets are UTF-8 byte offsets; convert to a str index."""
    return len(line.encode("utf-8")[:byte_col].decode("utf-8", errors="ignore"))


def _end(node: ast.AST) -> Tuple[int, int]:
    end_line, end_col = getattr(node, "end_lineno", None), getattr(node, "end_col_offset", None)
    if end_line is None or end_col is None:
        raise FixError("syntax tree has no end position")
    return end_line, end_col


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# --------------------------------------------------------------------------------------------------
# Line fixers (never add or remove lines, so later line numbers in the report stay valid)
# --------------------------------------------------------------------------------------------------

def remove_unused_ignore(path: Path, line_no: int, message: str) -> str:
    lines = _read_lines(path)
    body, ending = _line(lines, line_no)
    code, comment = _split_comment(body, line_info("".join(lines)).comments.get(line_no))
    match = TYPE_IGNORE_RE.search(comment)
    if not match:
        raise FixError(f"line {line_no} has no 'type: ignore' comment (report out of date?)")
    unused_match = UNUSED_CODES_RE.search(message)
    unused = set(_codes(unused_match["codes"])) if unused_match else set()
    existing = _codes(match["codes"])
    remaining = [c for c in existing if c not in unused] if unused and existing else []
    replacement = f"# type: ignore[{', '.join(remaining)}]" if remaining else ""
    updated = list(lines)
    updated[line_no - 1] = _join_comments(code, comment[:match.start()] + replacement + comment[match.end():]) + ending
    _write_validated(path, lines, updated)
    return f"removed unused ignore{' codes ' + ', '.join(sorted(unused)) if remaining else ''}"


def add_suppressions(path: Path, line_no: int, mypy_codes: Sequence[str], bandit_ids: Sequence[str]) -> str:
    """Add or extend `# type: ignore[...]` and `# nosec ...` on a line. type: ignore must lead the comment."""
    lines = _read_lines(path)
    body, ending = _line(lines, line_no)
    info = line_info("".join(lines))
    if line_no in info.no_append:
        raise FixError(f"line {line_no} is inside a multi-line string")
    code, comment = _split_comment(body, info.comments.get(line_no))
    if code.rstrip().endswith("\\"):
        raise FixError(f"line {line_no} ends with a backslash continuation")
    ignore, nosec = TYPE_IGNORE_RE.search(comment), NOSEC_RE.search(comment)
    rest = _remove_spans(comment, [m.span() for m in (ignore, nosec) if m])

    ignore_text = ""
    if ignore and ignore["codes"] is None:
        ignore_text = ignore.group(0)
    elif ignore or mypy_codes:
        ignore_text = f"# type: ignore[{', '.join(_merge(_codes(ignore['codes'] if ignore else None), mypy_codes))}]"

    nosec_text = ""
    if nosec and not BANDIT_ID_RE.findall(nosec["ids"]):
        nosec_text = nosec.group(0).strip()
    elif nosec or bandit_ids:
        existing_ids = BANDIT_ID_RE.findall(nosec["ids"]) if nosec else []
        nosec_text = f"# nosec {', '.join(_merge(existing_ids, bandit_ids))}"

    new_body = _join_comments(code, ignore_text, rest, nosec_text)
    if new_body == body:
        return "already suppressed"
    updated = list(lines)
    updated[line_no - 1] = new_body + ending
    _write_validated(path, lines, updated)
    return "suppressed " + ", ".join([*mypy_codes, *bandit_ids])


def _returns_value(func: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> bool:
    stack: List[ast.AST] = list(func.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Return) and node.value is not None:
            if not (isinstance(node.value, ast.Constant) and node.value.value is None):
                return True
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            return True
        stack.extend(ast.iter_child_nodes(node))
    return False


def _signature_colon(text: str, def_row: int) -> Tuple[int, int]:
    depth, seen_def = 0, False
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.start[0] < def_row:
            continue
        if not seen_def:
            seen_def = tok.type == tokenize.NAME and tok.string == "def"
            continue
        if tok.type == tokenize.OP:
            if tok.string in ("(", "[", "{"):
                depth += 1
            elif tok.string in (")", "]", "}"):
                depth -= 1
            elif tok.string == ":" and depth == 0:
                return tok.start
    raise FixError("could not find the end of the function signature")


def add_none_return(path: Path, line_no: int) -> str:
    lines = _read_lines(path)
    _line(lines, line_no)
    text = "".join(lines)
    func = next((n for n in ast.walk(ast.parse(text)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.lineno == line_no), None)
    if func is None:
        raise FixError(f"no function definition on line {line_no} (report out of date?)")
    if func.returns is not None:
        raise FixError(f"{func.name}() already has a return annotation")
    if _returns_value(func):
        raise FixError(f"{func.name}() returns or yields a value")
    row, col = _signature_colon(text, line_no)
    body, ending = _line(lines, row)
    updated = list(lines)
    updated[row - 1] = body[:col] + " -> None" + body[col:] + ending
    _write_validated(path, lines, updated)
    return f"added '-> None' to {func.name}()"


def add_request_timeout(path: Path, line_no: int, seconds: int) -> str:
    lines = _read_lines(path)
    _line(lines, line_no)
    calls = [n for n in ast.walk(ast.parse("".join(lines))) if isinstance(n, ast.Call) and n.lineno == line_no
             and isinstance(n.func, ast.Attribute) and n.func.attr in HTTP_METHODS
             and not any(k.arg == "timeout" for k in n.keywords)]
    if not calls:
        raise FixError(f"no HTTP call without a timeout on line {line_no} (report out of date?)")
    call = min(calls, key=lambda c: c.col_offset)
    if any(k.arg is None for k in call.keywords):
        raise FixError("call passes **kwargs, which may already contain a timeout; fix by hand")
    items: List[ast.AST] = [*call.args, *call.keywords]
    if items:
        row, byte_col = max(_end(item) for item in items)
        col, insertion = _char_col(lines[row - 1], byte_col), f", timeout={seconds}"
    else:
        row, byte_col = _end(call.func)
        body = lines[row - 1]
        paren = body.find("(", _char_col(body, byte_col))
        if paren < 0:
            raise FixError("could not find the call's opening parenthesis")
        col, insertion = paren + 1, f"timeout={seconds}"
    body, ending = _line(lines, row)
    updated = list(lines)
    updated[row - 1] = body[:col] + insertion + body[col:] + ending
    _write_validated(path, lines, updated)
    return f"added timeout={seconds}"


# --------------------------------------------------------------------------------------------------
# Versions and requirements (a deliberately small subset of PEP 440 / PEP 508, stdlib only)
# --------------------------------------------------------------------------------------------------

def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def release_parts(version: str) -> Optional[List[int]]:
    match = RELEASE_PREFIX_RE.match(version.strip())
    return [int(p) for p in match.group(1).split(".")] if match else None


def release_key(version: str) -> Optional[Tuple[int, ...]]:
    """Comparable release tuple with trailing zeros dropped (1.2 == 1.2.0). Pre/post/dev suffixes are ignored."""
    parts = release_parts(version)
    if parts is None:
        return None
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _padded(parts: Sequence[int], length: int) -> List[int]:
    return (list(parts) + [0] * length)[:length]


def choose_fix_version(installed: str, fixed_in: Sequence[str], allow_major: bool) -> Tuple[Optional[str], str]:
    """Pick the lowest final release that fixes the advisory, preferring the installed major version."""
    current = release_key(installed)
    if current is None:
        return None, f"cannot parse installed version {installed!r}"
    candidates = sorted(
        (v for v in fixed_in if FINAL_VERSION_RE.match(v) and (release_key(v) or ()) > current),
        key=lambda v: release_key(v) or (),
    )
    if not candidates:
        return None, "no fixed release is available"
    same_major = [v for v in candidates if (release_key(v) or (0,))[0] == current[0]]
    if same_major:
        return same_major[0], ""
    if allow_major:
        return candidates[0], ""
    return None, f"the fix needs a major upgrade to {candidates[0]} (use --allow-major)"


def requirement_name(requirement: str) -> Optional[str]:
    match = REQUIREMENT_RE.match(requirement)
    return canonical_name(match["name"]) if match else None


def clause_allows(op: str, version: str, target: str) -> bool:
    if op == "===":
        return version == target
    target_parts = release_parts(target)
    if version.endswith(".*") and op in ("==", "!="):
        prefix = release_parts(version[:-2])
        if prefix is None or target_parts is None:
            return False
        matches = _padded(target_parts, len(prefix)) == prefix
        return matches if op == "==" else not matches
    v, t = release_key(version), release_key(target)
    if v is None or t is None or target_parts is None:
        return False
    if op == "~=":
        parts = release_parts(version) or []
        return len(parts) >= 2 and t >= v and _padded(target_parts, len(parts) - 1) == parts[:-1]
    checks: Dict[str, bool] = {"==": t == v, "!=": t != v, ">=": t >= v, ">": t > v, "<=": t <= v, "<": t < v}
    return checks.get(op, False)


class ReqUpdate(NamedTuple):
    status: str  # "unchanged" | "changed" | "blocked"
    value: str  # new requirement string, or the reason it is blocked
    allows: bool  # whether the original requirement already allows the target version


def update_requirement(requirement: str, target: str) -> ReqUpdate:
    """Raise a requirement so it allows (and, where it has a floor or pin, requires) `target`, keeping its style."""
    match = REQUIREMENT_RE.match(requirement)
    if not match:
        return ReqUpdate("blocked", f"cannot parse requirement {requirement!r}", False)
    spec = match["spec"]
    clauses: List[Tuple[str, str]] = []
    for raw in (c for c in spec.split(",") if c.strip()):
        clause = CLAUSE_RE.match(raw)
        if not clause:
            return ReqUpdate("blocked", f"cannot parse specifier {raw.strip()!r}", False)
        clauses.append((clause["op"], clause["version"]))
    allows = all(clause_allows(op, v, target) for op, v in clauses)
    target_key = release_key(target) or ()

    new: List[Tuple[str, str]] = []
    has_floor = False
    for op, version in clauses:
        ok = clause_allows(op, version, target)
        key = release_key(version.removesuffix(".*")) or ()
        if op == "==" and not version.endswith(".*"):
            has_floor = True
            new.append((op, version if ok or key > target_key else target))
        elif op in (">=", ">"):
            has_floor = True
            new.append((">=", target) if key < target_key else (op, version))
        elif op == "~=":
            has_floor = True
            if not ok:
                return ReqUpdate("blocked", f"'~={version}' excludes {target}", allows)
            if key < target_key and len(release_parts(version) or []) == len(release_parts(target) or []):
                new.append(("~=", target))
            else:
                new.append((op, version))
                if key < target_key:
                    new.append((">=", target))
        elif not ok:
            return ReqUpdate("blocked", f"'{op}{version}' excludes {target}", allows)
        else:
            has_floor = has_floor or op == "==="
            new.append((op, version))
    if not has_floor:
        new.insert(0, (">=", target))
    if new == clauses:
        return ReqUpdate("unchanged", requirement, allows)
    separator = ", " if ", " in spec else ","
    new_spec = separator.join(op + version for op, version in new)
    return ReqUpdate("changed", requirement[:match.start("spec")] + new_spec + requirement[match.end("spec"):], allows)


# --------------------------------------------------------------------------------------------------
# pyproject.toml / uv.lock helpers
# --------------------------------------------------------------------------------------------------

def load_pyproject(directory: Path) -> Dict[str, Any]:
    path = directory / "pyproject.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        LOG.warning("Cannot read %s: %s", path, exc)
        return {}


def requirement_entries(data: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Every (section, requirement) string in a parsed pyproject.toml that uv resolves."""
    project = data.get("project", {})
    uv = data.get("tool", {}).get("uv", {})
    entries: List[Tuple[str, Any]] = [("project.dependencies", r) for r in project.get("dependencies", [])]
    for extra, reqs in project.get("optional-dependencies", {}).items():
        entries += [(f"project.optional-dependencies.{extra}", r) for r in reqs]
    for group, reqs in data.get("dependency-groups", {}).items():
        entries += [(f"dependency-groups.{group}", r) for r in reqs]
    for key in ("dev-dependencies", "override-dependencies", "constraint-dependencies"):
        entries += [(f"tool.uv.{key}", r) for r in uv.get(key, [])]
    return [(section, r) for section, r in entries if isinstance(r, str)]


def build_source_graph(root: Path, components: Iterable[str]) -> Dict[str, List[str]]:
    """component -> components it pulls in through `[tool.uv.sources]` path entries."""
    known = set(components)
    graph: Dict[str, List[str]] = {}
    for component in sorted(known):
        sources = load_pyproject(root / component).get("tool", {}).get("uv", {}).get("sources", {})
        found: List[str] = []
        for spec in sources.values():
            for entry in spec if isinstance(spec, list) else [spec]:
                if not (isinstance(entry, dict) and isinstance(entry.get("path"), str)):
                    continue
                try:
                    rel = (root / component / entry["path"]).resolve().relative_to(root.resolve()).as_posix()
                except ValueError:
                    continue
                if rel in known and rel not in found:
                    found.append(rel)
        graph[component] = found
    return graph


def dependency_closure(component: str, graph: Dict[str, List[str]]) -> List[str]:
    order, queue = [], [component]
    while queue:
        current = queue.pop(0)
        if current not in order:
            order.append(current)
            queue.extend(graph.get(current, []))
    return order


def dependents_of(changed: Set[str], graph: Dict[str, List[str]]) -> Set[str]:
    """Components whose lock files embed metadata from any changed component (including the changed ones)."""
    return {c for c in graph if changed & set(dependency_closure(c, graph))}


def lock_contains(root: Path, component: str, package: str) -> bool:
    lock = root / component / "uv.lock"
    try:
        text = lock.read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(rf'^name = "{re.escape(package)}"$', text, re.MULTILINE) is not None


def _toml_check(path: Path, text: str, expected: str) -> None:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise FixError(f"edit would make {path.name} invalid TOML ({exc}); left unchanged") from exc
    if expected not in (r for _, r in requirement_entries(data)):
        raise FixError(f"{expected!r} is not visible in {path.name} after the edit; left unchanged")


def replace_requirement(path: Path, old: str, new: str) -> str:
    text = path.read_bytes().decode("utf-8")
    count = 0
    for quote in ('"', "'"):
        needle = f"{quote}{old}{quote}"
        count += text.count(needle)
        text = text.replace(needle, f"{quote}{new}{quote}")
    if not count:
        raise FixError(f"{old!r} not found as a plain string in {path.name}")
    _toml_check(path, text, new)
    path.write_bytes(text.encode("utf-8"))
    return f"{old!r} -> {new!r}"


def add_override(path: Path, requirement: str) -> str:
    text = path.read_bytes().decode("utf-8")
    entry = json.dumps(requirement)
    existing = re.search(r"^\s*override-dependencies\s*=\s*\[", text, re.MULTILINE)
    header = re.search(r"^\[tool\.uv\][ \t]*$", text, re.MULTILINE)
    if existing:
        text = text[:existing.end()] + entry + ", " + text[existing.end():]
    elif header:
        eol = text.find("\n", header.end())
        line = f"override-dependencies = [{entry}]\n"
        text = text + "\n" + line if eol < 0 else text[:eol + 1] + line + text[eol + 1:]
    else:
        text = text.rstrip("\n") + f"\n\n[tool.uv]\noverride-dependencies = [{entry}]\n"
    _toml_check(path, text, requirement)
    path.write_bytes(text.encode("utf-8"))
    return f"added override {requirement!r}"


def run_checked(cmd: Sequence[str], cwd: Path, ok_codes: Sequence[int] = (0,)) -> str:
    proc = qr.run_command(cmd, cwd)
    if proc.returncode not in ok_codes:
        raise FixError(f"`{' '.join(cmd)}` exited {proc.returncode}:\n{qr.tail(proc.stdout + proc.stderr, 15)}")
    return ""


# --------------------------------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------------------------------

def _line_action(finding: ReportFinding, fixer: str, root: Path, description: str, plan: Plan,
                 func: Callable[..., str], *extra: Any) -> None:
    try:
        path, line_no = source_location(finding, root)
    except FixError as exc:
        plan.skipped.append((finding, str(exc)))
        return
    plan.actions.append(Action(PHASE_LINES, fixer, finding.component, f"{finding.location}: {description}",
                               partial(func, path, line_no, *extra), (finding,)))
    plan.claimed.add(finding)


def plan_line_fixes(report: Report, opts: Options, root: Path) -> Plan:
    plan = Plan()
    for f in report.findings:
        if f.check == "mypy" and opts.unused_ignores and f.code == "unused-ignore":
            _line_action(f, "unused-ignores", root, "remove unused type: ignore", plan, remove_unused_ignore, f.message)
        elif (f.check == "mypy" and opts.annotate_none and f.code == "no-untyped-def"
              and f.message.startswith("Function is missing a return type annotation") and NONE_HINT in f.detail):
            _line_action(f, "annotate-none", root, "add '-> None'", plan, add_none_return)
        elif f.check == "bandit" and opts.bandit_timeouts and f.code == "B113":
            _line_action(f, "bandit-timeouts", root, f"add timeout={opts.timeout_seconds}", plan,
                         add_request_timeout, opts.timeout_seconds)
    return plan


def plan_baseline(report: Report, claimed: Set[ReportFinding], root: Path) -> Plan:
    plan = Plan()
    grouped: Dict[Tuple[Path, int], Tuple[str, List[str], List[str], List[ReportFinding]]] = {}
    for f in report.findings:
        if f in claimed:
            continue
        is_mypy = f.check == "mypy" and f.severity == "error" and bool(f.code) and f.code != "unused-ignore"
        is_bandit = f.check == "bandit" and BANDIT_ID_RE.fullmatch(f.code) is not None
        if not (is_mypy or is_bandit):
            continue
        try:
            path, line_no = source_location(f, root)
        except FixError as exc:
            plan.skipped.append((f, str(exc)))
            continue
        _, mypy_codes, bandit_ids, members = grouped.setdefault((path, line_no), (f.component, [], [], []))
        (mypy_codes if is_mypy else bandit_ids).append(f.code)
        members.append(f)
    for (path, line_no), (component, raw_codes, raw_ids, members) in sorted(grouped.items()):
        mypy_codes, bandit_ids = _merge([], raw_codes), _merge([], raw_ids)
        plan.actions.append(Action(
            PHASE_LINES, "baseline", component,
            f"{_relative(path, root)}:{line_no}: suppress {', '.join([*mypy_codes, *bandit_ids])}",
            partial(add_suppressions, path, line_no, mypy_codes, bandit_ids),
            tuple(members),
        ))
        plan.claimed.update(members)
    return plan


def plan_ruff(report: Report, unsafe: bool, root: Path) -> Plan:
    plan = Plan()
    applicable = ("safe", "unsafe") if unsafe else ("safe",)
    by_component: Dict[str, List[ReportFinding]] = {}
    for f in report.findings:
        if f.check == "ruff" and f.meta_value("fix") in applicable:
            by_component.setdefault(f.component, []).append(f)
    for component, findings in sorted(by_component.items()):
        cmd = ["uv", "run", "ruff", "check", ".", "--fix", *(["--unsafe-fixes"] if unsafe else [])]
        plan.actions.append(Action(
            PHASE_RUFF, "ruff", component, f"`{' '.join(cmd)}` ({len(findings)} fixable finding(s))",
            # ruff exits 1 when unfixable findings remain, which is not a failure of the fix itself.
            partial(run_checked, cmd, root / component, (0, 1)),
            tuple(findings),
        ))
        plan.claimed.update(findings)
    return plan


def plan_audit(report: Report, opts: Options, root: Path, components: Sequence[str]) -> Plan:
    plan = Plan()
    graph = build_source_graph(root, components)
    pyprojects: Dict[str, Dict[str, Any]] = {}

    def manifest(component: str) -> Dict[str, Any]:
        if component not in pyprojects:
            pyprojects[component] = load_pyproject(root / component)
        return pyprojects[component]

    # 1. Pick a target version per (component, package).
    targets: Dict[Tuple[str, str], str] = {}
    members: Dict[Tuple[str, str], List[ReportFinding]] = {}
    for f in report.findings:
        if f.check != "audit" or f.code == "adverse-status":
            continue
        package = f.meta_value("package")
        if not NAME_RE.match(package):
            plan.skipped.append((f, f"invalid package name {package!r}"))
            continue
        fixed_in = [v.strip() for v in f.meta_value("fixed_in").split(",")]
        version, reason = choose_fix_version(f.meta_value("installed"), fixed_in, opts.allow_major)
        if version is None:
            plan.skipped.append((f, reason))
            continue
        key = (f.component, canonical_name(package))
        if key not in targets or (release_key(version) or ()) > (release_key(targets[key]) or ()):
            targets[key] = version
        members.setdefault(key, []).append(f)

    # 2. Decide how each one is fixed: manifest edit, new direct/override requirement, or lock-only upgrade.
    edits: Dict[Tuple[str, str], str] = {}  # (declaring component, requirement) -> target
    additions: Dict[Tuple[str, str], str] = {}  # (component, package) -> target
    lock_targets: Dict[str, Dict[str, str]] = {}
    for (component, package), version in sorted(targets.items()):
        declared = [(c, req) for c in dependency_closure(component, graph)
                    for _, req in requirement_entries(manifest(c)) if requirement_name(req) == package]
        updates = [(c, req, update_requirement(req, version)) for c, req in declared]
        blocked = next(((c, req, u) for c, req, u in updates
                        if u.status == "blocked" or (not opts.audit_pin and not u.allows)), None)
        if blocked:
            c, req, u = blocked
            reason = u.value if u.status == "blocked" else "use --audit-pin to update it"
            for f in members[(component, package)]:
                plan.skipped.append((f, f"{req!r} in {c}/pyproject.toml blocks {package}=={version}: {reason}"))
            continue
        if opts.audit_pin:
            for c, req, u in updates:
                if u.status == "changed":
                    current = edits.get((c, req))
                    if current is None or (release_key(version) or ()) > (release_key(current) or ()):
                        edits[(c, req)] = version
        if not declared and (opts.audit_transitive or opts.audit_override):
            additions[(component, package)] = version
        lock_targets.setdefault(component, {})[package] = version
        plan.claimed.update(members[(component, package)])

    # 3. Manifest edits. A shared lib edited for several consumers gets the highest target.
    edited: Dict[str, Dict[str, str]] = {}
    for (component, req), version in sorted(edits.items()):
        update = update_requirement(req, version)
        if update.status != "changed":
            plan.notes.append(f"{component}: {req!r} could not be raised to {version}: {update.value}")
            continue
        path = root / component / "pyproject.toml"
        plan.actions.append(Action(
            PHASE_MANIFEST, "audit-pin", component, f"{component}/pyproject.toml: {req!r} -> {update.value!r}",
            partial(replace_requirement, path, req, update.value),
        ))
        edited.setdefault(component, {})[requirement_name(req) or ""] = version
    for (component, package), version in sorted(additions.items()):
        requirement = f"{package}>={version}"
        if opts.audit_override:
            path = root / component / "pyproject.toml"
            plan.actions.append(Action(
                PHASE_MANIFEST, "audit-override", component,
                f"{component}/pyproject.toml: add {requirement!r} to [tool.uv] override-dependencies",
                partial(add_override, path, requirement),
            ))
        else:
            cmd = ["uv", "add", "--frozen", requirement]
            plan.actions.append(Action(
                PHASE_MANIFEST, "audit-transitive", component, f"`{' '.join(cmd)}` (direct minimum version)",
                partial(run_checked, cmd, root / component),
            ))
        edited.setdefault(component, {})[package] = version

    # 4. Re-lock everything affected, after every manifest has been edited (path deps embed manifest metadata).
    for component in sorted(set(lock_targets) | dependents_of(set(edited), graph)):
        if not (root / component / "uv.lock").is_file():
            continue
        wanted = dict(lock_targets.get(component, {}))
        for dep in dependency_closure(component, graph):
            for package, version in edited.get(dep, {}).items():
                if lock_contains(root, component, package) and (
                        release_key(version) or ()) > (release_key(wanted.get(package, "0")) or ()):
                    wanted[package] = version
        cmd = ["uv", "--native-tls", "lock"]
        for package, version in sorted(wanted.items()):
            cmd += ["--upgrade-package", f"{package}=={version}"]
        fixed = tuple(f for (c, package), fs in members.items() if c == component and package in wanted for f in fs
                      if f in plan.claimed)
        plan.actions.append(Action(PHASE_LOCK, "audit", component, f"`{' '.join(cmd)}`",
                                   partial(run_checked, cmd, root / component), fixed))
    return plan


def component_of(path: str, components: Sequence[str]) -> Optional[str]:
    matches = [c for c in components if path == c or path.startswith(c + "/")]
    return max(matches, key=len) if matches else None


def changed_python_files(root: Path) -> List[str]:
    proc = qr.run_command(["git", "diff", "--name-only", "HEAD"], root)
    if proc.returncode != 0:
        raise FixError(f"git diff failed: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line.endswith(".py")]


def format_changed_files(root: Path, components: Sequence[str]) -> str:
    by_component: Dict[str, List[str]] = {}
    for rel in changed_python_files(root):
        component = component_of(rel, components)
        if component and (root / rel).is_file():
            by_component.setdefault(component, []).append(Path(rel).relative_to(component).as_posix())
    for component, files in sorted(by_component.items()):
        run_checked(["uv", "run", "ruff", "format", *files], root / component)
    count = sum(len(files) for files in by_component.values())
    return f"formatted {count} file(s) in {len(by_component)} component(s)"


def build_plan(report: Report, opts: Options, root: Path, components: Sequence[str]) -> Plan:
    plan = Plan()
    plan.merge(plan_line_fixes(report, opts, root))
    if opts.ruff:
        plan.merge(plan_ruff(report, opts.ruff_unsafe, root))
    if opts.audit:
        plan.merge(plan_audit(report, opts, root, components))
    if opts.baseline:
        plan.merge(plan_baseline(report, plan.claimed, root))
    if opts.format:
        plan.actions.append(Action(PHASE_FORMAT, "format", "(changed files)",
                                   "`uv run ruff format` on every .py file changed by this run",
                                   partial(format_changed_files, root, components)))
    plan.actions.sort(key=lambda a: a.phase)
    return plan


# --------------------------------------------------------------------------------------------------
# Output: plan, triage, recheck
# --------------------------------------------------------------------------------------------------

def log_plan(plan: Plan) -> None:
    if not plan.actions:
        LOG.info("Nothing to fix with the selected fixers.")
    current = None
    for action in plan.actions:
        if action.phase != current:
            current = action.phase
            LOG.info("")
            LOG.info("== %s ==", PHASE_LABELS[current])
        LOG.info("  [%s] %s: %s", action.fixer, action.component, action.description)
    log_skipped(plan)


def log_skipped(plan: Plan) -> None:
    if plan.skipped:
        LOG.info("")
        LOG.info("== Not fixable automatically (%d) ==", len(plan.skipped))
        for finding, reason in plan.skipped:
            LOG.info("  [%s] %s %s %s: %s", finding.check, finding.component, finding.location, finding.code, reason)
    for note in plan.notes:
        LOG.warning("Note: %s", note)


def execute(plan: Plan) -> List[Tuple[Action, str]]:
    failures: List[Tuple[Action, str]] = []
    current = None
    for action in plan.actions:
        if action.phase != current:
            current = action.phase
            LOG.info("")
            LOG.info("== %s ==", PHASE_LABELS[current])
        try:
            outcome = action.run()
        except (FixError, OSError, SyntaxError, ValueError) as exc:
            failures.append((action, str(exc)))
            LOG.error("  FAILED [%s] %s: %s\n    %s", action.fixer, action.component, action.description,
                      str(exc).replace("\n", "\n    "))
            continue
        suffix = f" ({outcome})" if outcome and outcome not in action.description else ""
        LOG.info("  OK     [%s] %s: %s%s", action.fixer, action.component, action.description, suffix)
    return failures


def fixer_hint(f: ReportFinding) -> str:
    """Name the switch that would fix a finding, for findings left over because that fixer wasn't selected."""
    if f.check == "ruff" and f.meta_value("fix") in ("safe", "unsafe"):
        return "--ruff" if f.meta_value("fix") == "safe" else "--ruff-unsafe"
    if f.check == "mypy" and f.code == "unused-ignore":
        return "--unused-ignores"
    if (f.check == "mypy" and f.code == "no-untyped-def" and NONE_HINT in f.detail
            and f.message.startswith("Function is missing a return type annotation")):
        return "--annotate-none"
    if f.check == "bandit" and f.code == "B113":
        return "--bandit-timeouts"
    if f.check == "audit" and FINAL_VERSION_RE.match(f.meta_value("fixed_in").split(",")[0].strip()):
        return "--audit-pin"
    return ""


def triage_rows(report: Report, plan: Plan) -> List[Dict[str, str]]:
    reasons = {f: reason for f, reason in plan.skipped}
    rows = []
    for f in report.findings:
        if f not in plan.claimed:
            hint = fixer_hint(f)
            note = reasons.get(f) or (f"auto-fixable with {hint}" if hint else "")
            rows.append({"component": f.component, "check": f.check, "location": f.location, "code": f.code,
                         "message": f.message, "url": f.url, "note": note, "fixer": hint})
    for result in report.results:
        if result.get("status") == "error":
            rows.append({"component": result.get("component", ""), "check": result.get("check", ""),
                         "location": "", "code": "check-error", "message": "The check itself failed to run",
                         "url": "", "note": qr.tail(result.get("output", ""), 3), "fixer": ""})
    return sorted(rows, key=lambda r: (r["component"], r["check"], r["location"]))


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def triage_summary(rows: List[Dict[str, str]]) -> str:
    by_check = Counter(r["check"] for r in rows)
    fixable = sum(1 for r in rows if r["fixer"])
    parts = [", ".join(f"{check} {count}" for check, count in sorted(by_check.items()))]
    if fixable:
        parts.append(f"{fixable} auto-fixable with: {' '.join(sorted({r['fixer'] for r in rows if r['fixer']}))}")
    return "; ".join(p for p in parts if p)


def write_triage(path: Path, report: Report, plan: Plan, opts: Options) -> List[Dict[str, str]]:
    rows = triage_rows(report, plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps({"report": report.meta, "fixers": opts.selected(), "findings": rows}, indent=2),
                        encoding="utf-8")
        return rows
    lines = [
        "# Quality triage",
        "",
        f"Report: `{_relative(report.path, ROOT_DIR)}`, generated {report.meta.get('generated', '?')} "
        f"on `{report.meta.get('branch', '?')}` @ `{report.meta.get('commit', '?')}`.",
        f"Fixers assumed applied: {', '.join(opts.selected()) or 'none'}.",
        f"Findings remaining: **{len(rows)}** ({triage_summary(rows) or 'none'}).",
    ]
    current = None
    for row in rows:
        if row["component"] != current:
            current = row["component"]
            lines += ["", f"## {current}", "", "| Check | Location | Code | Message | Note |", "|---|---|---|---|---|"]
        code = f"[{_md(row['code'])}]({row['url']})" if row["url"] else _md(row["code"])
        lines.append(f"| {row['check']} | `{_md(row['location'])}` | {code} | {_md(row['message'])} "
                     f"| {_md(row['note'])} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


def _finding_key(f: ReportFinding) -> Tuple[str, str, str, str, str]:
    # Line numbers move when code is edited, so compare on file + code + message instead.
    return (f.check, f.component, f.code, f.location.split(":", 1)[0], f.message)


def recheck(before: Report, components: Sequence[str], groups: Sequence[str]) -> None:
    checks = qr.resolve_checks(",".join(groups))
    LOG.info("")
    LOG.info("== Re-running %s for %d component(s) ==", ", ".join(groups), len(components))
    qr.main([*components, "--checks", ",".join(groups), "--output", str(RECHECK_OUTPUT)])
    after = load_report(RECHECK_OUTPUT.with_suffix(".json"))
    old = Counter(_finding_key(f) for f in before.findings if f.component in components and f.check in checks)
    new = Counter(_finding_key(f) for f in after.findings)
    LOG.info("")
    LOG.info("%-45s %-7s %6s %9s %5s", "Component", "Check", "Fixed", "Remaining", "New")
    for component in components:
        for check in checks:
            o = Counter({k: v for k, v in old.items() if k[0] == check and k[1] == component})
            n = Counter({k: v for k, v in new.items() if k[0] == check and k[1] == component})
            if o or n:
                LOG.info("%-45s %-7s %6d %9d %5d", component, check, sum((o - n).values()), sum((o & n).values()),
                         sum((n - o).values()))
    LOG.info("Recheck report: %s", RECHECK_OUTPUT)


# --------------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------------

def parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply automatic fixes for findings in a quality_report.py JSON report (dry run by default).",
        epilog="Full documentation: dev_tools/scripts/quality_fix.md",
    )
    parser.add_argument("components", nargs="*", help="Only fix these components (default: all in the report)")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Report JSON (default: %(default)s)")
    parser.add_argument("--apply", action="store_true", help="Make the changes (default: print the plan only)")

    fixers = parser.add_argument_group("fixers")
    fixers.add_argument("--safe", action="store_true",
                        help="Shortcut for --ruff --audit --audit-pin --unused-ignores")
    fixers.add_argument("--ruff", action="store_true", help="ruff check --fix (safe fixes) where findings are fixable")
    fixers.add_argument("--ruff-unsafe", action="store_true", help="Also apply ruff's unsafe fixes (implies --ruff)")
    fixers.add_argument("--format", action="store_true", help="ruff format the .py files changed by this run")
    fixers.add_argument("--audit", action="store_true", help="Upgrade vulnerable packages in uv.lock only")
    fixers.add_argument("--audit-pin", action="store_true",
                        help="Also raise pins/floors in pyproject.toml, incl. shared libs (implies --audit)")
    transitive = fixers.add_mutually_exclusive_group()
    transitive.add_argument("--audit-transitive", action="store_true",
                            help="Add a direct 'pkg>=fixed' for undeclared vulnerable packages (implies --audit)")
    transitive.add_argument("--audit-override", action="store_true",
                            help="Like --audit-transitive but via [tool.uv] override-dependencies")
    fixers.add_argument("--allow-major", action="store_true", help="Allow audit fixes that cross a major version")
    fixers.add_argument("--unused-ignores", action="store_true", help="Remove unused '# type: ignore' comments")
    fixers.add_argument("--annotate-none", action="store_true",
                        help="Add '-> None' where mypy says the function returns nothing")
    fixers.add_argument("--bandit-timeouts", action="store_true", help="Add timeout= to HTTP calls (bandit B113)")
    fixers.add_argument("--timeout-seconds", type=int, default=30, help="Timeout for --bandit-timeouts (default 30)")
    fixers.add_argument("--baseline", action="store_true",
                        help="Suppress remaining mypy/bandit findings with '# type: ignore[...]' / '# nosec ...'")

    output = parser.add_argument_group("output and safety")
    output.add_argument("--triage", type=Path, help="Write findings left for a human to this .md or .json file")
    output.add_argument("--recheck", action="store_true", help="After --apply, re-run the affected checks")
    output.add_argument("--allow-dirty", action="store_true", help="Allow --apply with uncommitted changes")
    return parser.parse_args(argv)


def options_from_args(args: argparse.Namespace) -> Options:
    opts = Options(
        ruff=args.ruff or args.ruff_unsafe or args.safe,
        ruff_unsafe=args.ruff_unsafe,
        format=args.format,
        audit_pin=args.audit_pin or args.safe,
        audit_transitive=args.audit_transitive,
        audit_override=args.audit_override,
        allow_major=args.allow_major,
        unused_ignores=args.unused_ignores or args.safe,
        annotate_none=args.annotate_none,
        bandit_timeouts=args.bandit_timeouts,
        timeout_seconds=args.timeout_seconds,
        baseline=args.baseline,
    )
    opts.audit = args.audit or opts.audit_pin or opts.audit_transitive or opts.audit_override
    return opts


def _git_dirty_files(root: Path) -> List[str]:
    proc = qr.run_command(["git", "status", "--porcelain", "--untracked-files=no"], root)
    if proc.returncode != 0:
        return [f"(git status failed: {proc.stderr.strip()})"]
    return [line[3:] for line in proc.stdout.splitlines() if line.strip()]


def _recheck_targets(plan: Plan, failures: List[Tuple[Action, str]], components: Sequence[str],
                     root: Path) -> Tuple[List[str], List[str]]:
    failed = {id(action) for action, _ in failures}
    done = [a for a in plan.actions if id(a) not in failed]
    touched = {a.component for a in done if a.component in components}
    try:
        touched |= {c for c in (component_of(p, components) for p in changed_python_files(root)) if c}
    except FixError:
        pass
    groups = {g for a in done for g in RECHECK_GROUPS.get(a.fixer, ())}
    if done:
        groups.add("tests")
    return sorted(touched), [g for g in qr.CHECK_GROUPS if g in groups]


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    opts = options_from_args(args)
    if not opts.selected() and not args.triage:
        LOG.error("Choose at least one fixer (e.g. --safe) or --triage. See --help.")
        return 2
    if args.timeout_seconds <= 0:
        LOG.error("--timeout-seconds must be positive")
        return 2

    report_path: Path = args.report.resolve()
    if not report_path.is_file():
        LOG.error("Report %s not found; run dev_tools/scripts/quality_report.py first.", report_path)
        return 2
    components = qr.discover_components(ROOT_DIR)
    selected: Optional[Set[str]] = None
    if args.components:
        selected = {c.strip("/") for c in args.components}
        unknown = sorted(selected - set(components))
        if unknown:
            LOG.error("Unknown components: %s", ", ".join(unknown))
            return 2
    try:
        report = load_report(report_path, selected)
    except (OSError, ValueError) as exc:
        LOG.error("Cannot read report %s: %s", report_path, exc)
        return 2

    head = qr.run_command(["git", "rev-parse", "--short", "HEAD"], ROOT_DIR).stdout.strip()
    if report.meta.get("commit") and head and report.meta["commit"] != head:
        LOG.warning("Report was generated at %s but HEAD is %s; line-based fixes may not match the code.",
                    report.meta["commit"], head)
    dirty = _git_dirty_files(ROOT_DIR) if args.apply and not args.allow_dirty else []
    if dirty:
        LOG.error("Uncommitted changes in the working tree:\n  %s\nCommit or stash them first so `git diff` shows "
                  "only this script's changes, or pass --allow-dirty to fix on top of them.", "\n  ".join(dirty))
        return 2

    plan = build_plan(report, opts, ROOT_DIR, components)
    LOG.info("Report: %s (generated %s, commit %s)", _relative(report_path, ROOT_DIR),
             report.meta.get("generated", "?"), report.meta.get("commit", "?"))
    LOG.info("Fixers: %s", ", ".join(opts.selected()) or "none")

    failures: List[Tuple[Action, str]] = []
    if args.apply:
        failures = execute(plan)
        for action, error in failures:
            plan.claimed -= set(action.findings)
            plan.skipped += [(f, f"automatic fix failed: {(error.splitlines() or [''])[0]}") for f in action.findings]
        log_skipped(plan)
    else:
        log_plan(plan)

    if args.triage:
        rows = write_triage(args.triage.resolve(), report, plan, opts)
        LOG.info("")
        LOG.info("Triage: %d finding(s) written to %s", len(rows), args.triage)
        if rows:
            LOG.info("  %s", triage_summary(rows))

    LOG.info("")
    if not args.apply:
        LOG.info("Dry run: %d action(s) planned, nothing changed. Re-run with --apply to make the changes.",
                 len(plan.actions))
        return 0
    LOG.info("%d action(s) applied, %d failed. Review with `git diff`; undo with `git restore .`.",
             len(plan.actions) - len(failures), len(failures))

    if args.recheck and plan.actions:
        targets, groups = _recheck_targets(plan, failures, components, ROOT_DIR)
        if targets and groups:
            recheck(report, targets, groups)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
