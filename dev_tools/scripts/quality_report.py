#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Run ruff, mypy, unit tests and security checks for every component and write one HTML report.

Mirrors the commands in pipeline-ado/pr-validation.yml and dev_tools/scripts/run-all-*.sh using each
tool's machine-readable output, then renders a self-contained HTML file (no CDN assets) plus a JSON
sidecar. Tests run with pytest where the component's check.sh does (as CI's usePytest does),
otherwise unittest. Standard library only, so it runs anywhere `uv` does.

Usage:
    dev_tools/scripts/quality_report.py                      # all checks, all components
    dev_tools/scripts/quality_report.py --changed origin/main
    dev_tools/scripts/quality_report.py --checks ruff,bandit dashboard senders/hl7_sender
    dev_tools/scripts/quality_report.py --output /tmp/report.html --open
"""

from __future__ import annotations

import argparse
import concurrent.futures
import html
import json
import logging
import os
import re
import subprocess  # nosec B404
import sys
import tempfile
import time
import tomllib
import webbrowser
import xml.etree.ElementTree as ET  # nosec B405
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOG = logging.getLogger("quality_report")

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT_DIR / "dev_tools" / "reports" / "quality-report.html"
DEFAULT_TIMEOUT = 300.0

CHECKS: tuple[str, ...] = ("ruff", "mypy", "tests", "bandit", "audit")
DEFAULT_CHECK_GROUPS: tuple[str, ...] = ("ruff", "mypy", "tests", "security")
CHECK_GROUPS: dict[str, tuple[str, ...]] = {
    "ruff": ("ruff",),
    "mypy": ("mypy",),
    "tests": ("tests",),
    "bandit": ("bandit",),
    "audit": ("audit",),
    "security": ("bandit", "audit"),
}
CHECK_LABELS: dict[str, str] = {
    "ruff": "Ruff",
    "mypy": "Mypy",
    "tests": "Tests",
    "bandit": "Bandit",
    "audit": "Dependencies",
}
TAB_OF_CHECK: dict[str, str] = {
    "ruff": "ruff", "mypy": "mypy", "tests": "tests", "bandit": "security", "audit": "security",
}
TAB_LABELS: dict[str, str] = {"ruff": "Ruff", "mypy": "Mypy", "tests": "Tests", "security": "Security"}

# Known no-fix advisory for a transitive Pygments dependency; keep in sync with run-all-security.sh.
AUDIT_IGNORES: tuple[str, ...] = ("GHSA-5239-wwwm-4pmq",)

# Codes documented on mypy's "optional checks" page rather than the default error-code page.
MYPY_OPTIONAL_CODES = frozenset({
    "type-arg", "no-untyped-def", "redundant-cast", "redundant-self", "comparison-overlap", "no-untyped-call",
    "no-any-return", "no-any-unimported", "unreachable", "deprecated", "redundant-expr", "possibly-undefined",
    "truthy-bool", "truthy-iterable", "ignore-without-code", "unused-awaitable", "unused-ignore",
    "explicit-override", "mutable-override", "unimported-reveal", "explicit-any", "exhaustive-match",
    "untyped-decorator",
})

STATUS_ORDER = {"error": 0, "fail": 1, "pass": 2, "skipped": 3}

FindingKey = tuple[str, str, str, str, str]


@dataclass
class Finding:
    location: str
    code: str
    message: str
    severity: str
    url: str = ""
    detail: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)


@dataclass
class CheckResult:
    check: str
    component: str
    status: str  # pass | fail | error | skipped
    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, float] = field(default_factory=dict)
    output: str = ""
    duration: float = 0.0
    runner: str = ""


@dataclass
class RunConfig:
    timeout: float | None = DEFAULT_TIMEOUT
    tls_flags: tuple[str, ...] = ()
    audit_ignores: tuple[str, ...] = AUDIT_IGNORES
    audit_ignore_flag: str = "--ignore"
    sync_mode: str = "targeted"  # targeted | all | none
    source_graph: dict[str, list[str]] | None = None


@dataclass
class ReportDelta:
    baseline_commit: str = ""
    baseline_generated: str = ""
    new_count: int = 0
    fixed_count: int = 0
    new_by_check: dict[str, int] = field(default_factory=dict)
    fixed_by_check: dict[str, int] = field(default_factory=dict)
    new_by_pair: dict[tuple[str, str], int] = field(default_factory=dict)
    fixed_by_pair: dict[tuple[str, str], int] = field(default_factory=dict)
    new_finding_indices: dict[tuple[str, str], set[int]] = field(default_factory=dict)


# --------------------------------------------------------------------------------------------------
# Helpers & component graph
# --------------------------------------------------------------------------------------------------

def safe_url(url: str) -> str:
    """Only allow http(s) links into the report, so tool output can't inject javascript: URLs."""
    return url if re.match(r"^https?://", url or "", re.IGNORECASE) else ""


def advisory_url(advisory_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._:-]+", advisory_id or ""):
        return ""
    if advisory_id.startswith("GHSA-"):
        return f"https://github.com/advisories/{advisory_id}"
    if advisory_id.startswith("CVE-"):
        return f"https://nvd.nist.gov/vuln/detail/{advisory_id}"
    return f"https://osv.dev/vulnerability/{advisory_id}"


def mypy_doc_url(code: str) -> str:
    if not code:
        return ""
    page = "error_code_list2.html" if code in MYPY_OPTIONAL_CODES else "error_code_list.html"
    return f"https://mypy.readthedocs.io/en/stable/{page}#code-{code}"


def relative_path(path: str, base: Path, root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def tail(text: str, lines: int = 80) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def _decode(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def discover_components(root: Path) -> list[str]:
    """Same discovery rule as the run-all-*.sh scripts: any pyproject.toml up to two directories deep."""
    found = set()
    for pattern in ("*/pyproject.toml", "*/*/pyproject.toml"):
        for pyproject in root.glob(pattern):
            rel = pyproject.parent.relative_to(root)
            if not {".venv", "node_modules"} & set(rel.parts):
                found.add(rel.as_posix())
    return sorted(found)


def load_pyproject(directory: Path) -> dict[str, Any]:
    path = directory / "pyproject.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        LOG.warning("Cannot read %s: %s", path, exc)
        return {}


def build_source_graph(root: Path, components: Iterable[str]) -> dict[str, list[str]]:
    """Map each component to components it pulls in through `[tool.uv.sources]` path entries."""
    known = set(components)
    resolved_root = root.resolve()
    graph: dict[str, list[str]] = {}
    for component in sorted(known):
        sources = load_pyproject(root / component).get("tool", {}).get("uv", {}).get("sources", {})
        found: list[str] = []
        for spec in sources.values():
            for entry in spec if isinstance(spec, list) else [spec]:
                if not (isinstance(entry, dict) and isinstance(entry.get("path"), str)):
                    continue
                try:
                    rel = (root / component / entry["path"]).resolve().relative_to(resolved_root).as_posix()
                except ValueError:
                    continue
                if rel in known and rel not in found:
                    found.append(rel)
        graph[component] = found
    return graph


def dependency_closure(component: str, graph: dict[str, list[str]]) -> list[str]:
    order: list[str] = []
    queue = [component]
    while queue:
        current = queue.pop(0)
        if current not in order:
            order.append(current)
            queue.extend(graph.get(current, []))
    return order


def dependents_of(changed: set[str], graph: dict[str, list[str]]) -> set[str]:
    """Components that depend on (directly or transitively) any component in `changed`, including `changed`."""
    return {c for c in graph if changed & set(dependency_closure(c, graph))}


def component_of(path: str, components: Sequence[str]) -> str | None:
    normalized = path.strip("/")
    matches = [c for c in components if normalized == c or normalized.startswith(c + "/")]
    return max(matches, key=len) if matches else None


def local_path_packages(component: str, root: Path, graph: dict[str, list[str]] | None = None) -> list[str]:
    """Package names of local path dependencies (direct and transitive) for `component`."""
    closure = dependency_closure(component, graph) if graph is not None else [component]
    packages: set[str] = set()
    for current in closure:
        data = load_pyproject(root / current)
        if current != component:
            proj_name = data.get("project", {}).get("name")
            if isinstance(proj_name, str) and proj_name:
                packages.add(proj_name)
        sources = data.get("tool", {}).get("uv", {}).get("sources", {})
        for pkg_name, spec in sources.items():
            entries = spec if isinstance(spec, list) else [spec]
            if any(isinstance(entry, dict) and isinstance(entry.get("path"), str) for entry in entries):
                packages.add(pkg_name)
    return sorted(packages)


def changed_components(root: Path, components: Sequence[str], ref: str = "HEAD",
                       graph: dict[str, list[str]] | None = None) -> list[str]:
    """Return discovered components touched vs `ref` (plus untracked files and downstream dependents)."""
    diff = run_command(["git", "diff", "--name-only", ref], root)
    if diff.returncode != 0:
        raise ValueError(f"git diff {ref!r} failed: {(diff.stderr or diff.stdout).strip()}")
    untracked = run_command(["git", "ls-files", "--others", "--exclude-standard"], root)
    paths = [line.strip() for line in (diff.stdout + "\n" + untracked.stdout).splitlines() if line.strip()]
    touched = {comp for path in paths if (comp := component_of(path, components)) is not None}
    if not touched:
        return []
    resolved_graph = graph if graph is not None else build_source_graph(root, components)
    return sorted(dependents_of(touched, resolved_graph))


# --------------------------------------------------------------------------------------------------
# Parsers (pure functions over tool output)
# --------------------------------------------------------------------------------------------------

def parse_ruff(stdout: str, cwd: Path, root: Path) -> list[Finding]:
    findings = []
    for item in json.loads(stdout or "[]"):
        if not isinstance(item, dict):
            continue
        location = item.get("location") or {}
        fix = item.get("fix") or {}
        filename = item.get("filename") or ""
        loc_path = relative_path(filename, cwd, root) if filename else ""
        findings.append(Finding(
            location=f"{loc_path}:{location.get('row', 0)}:{location.get('column', 0)}",
            code=item.get("code") or "syntax-error",
            message=item.get("message", ""),
            severity="error",
            url=safe_url(item.get("url") or ""),
            meta={"rule": item.get("name") or "", "fix": fix.get("applicability", "") if fix else ""},
        ))
    return findings


def parse_mypy(stdout: str, cwd: Path, root: Path) -> list[Finding]:
    """Parse `mypy -O json` (one object per line); notes are folded into the preceding error."""
    findings: list[Finding] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        message = item.get("message", "")
        severity = item.get("severity") or "error"
        if severity == "note":
            if findings:
                findings[-1].detail = "\n".join(filter(None, [findings[-1].detail, message]))
            continue
        code = item.get("code") or ""
        findings.append(Finding(
            location=f"{relative_path(item.get('file', ''), cwd, root)}:{item.get('line', 0)}:{item.get('column', 0)}",
            code=code,
            message=message,
            severity=severity,
            url=mypy_doc_url(code),
            detail=item.get("hint") or "",
        ))
    return findings


_EQ_SEPARATOR = "=" * 70
_DASH_SEPARATOR = "-" * 70
_RAN_RE = re.compile(r"^Ran (\d+) tests? in ([\d.]+)s$", re.MULTILINE)
_RESULT_RE = re.compile(r"^(OK|FAILED|NO TESTS RAN)(?: \((.*)\))?\s*$", re.MULTILINE)
_FAILURE_HEADER_RE = re.compile(r"^(FAIL|ERROR|UNEXPECTED SUCCESS): (.+)$")
_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+)')


def _unittest_failure_blocks(output: str) -> list[tuple[str, str, str, str]]:
    """Return (kind, test id, docstring, traceback) for each ====-delimited failure block."""
    lines = output.splitlines()
    blocks = []
    i, total = 0, len(lines)
    while i < total:
        if lines[i] != _EQ_SEPARATOR:
            i += 1
            continue
        j = i + 1
        while j < total and lines[j] not in (_DASH_SEPARATOR, _EQ_SEPARATOR):
            j += 1
        header = lines[i + 1:j]
        match = _FAILURE_HEADER_RE.match(header[0]) if header else None
        if j >= total or lines[j] != _DASH_SEPARATOR or match is None:
            i = j
            continue
        k = j + 1
        while k < total and lines[k] != _EQ_SEPARATOR and not (
            lines[k] == _DASH_SEPARATOR and k + 1 < total and lines[k + 1].startswith("Ran ")
        ):
            k += 1
        blocks.append((match.group(1), match.group(2), "\n".join(header[1:]), "\n".join(lines[j + 1:k]).strip()))
        i = k
    return blocks


def _is_project_path(candidate: Path, resolved_root: Path) -> bool:
    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    if not resolved.is_relative_to(resolved_root):
        return False
    return not ({".venv", "site-packages"} & set(resolved.parts))


def _last_project_frame(traceback: str, root: Path) -> str:
    resolved_root = root.resolve()
    location = ""
    for path, line in _FRAME_RE.findall(traceback):
        candidate = Path(path)
        if _is_project_path(candidate, resolved_root):
            location = f"{relative_path(path, root, root)}:{line}"
    return location


def parse_unittest(output: str, root: Path) -> tuple[dict[str, float] | None, list[Finding]]:
    """Parse `python -m unittest -v` output. Returns (None, []) if no run summary was printed."""
    ran_matches = list(_RAN_RE.finditer(output))
    if not ran_matches:
        return None, []
    ran = ran_matches[-1]
    summary: dict[str, float] = {
        "ran": int(ran.group(1)), "duration": float(ran.group(2)), "failures": 0, "errors": 0, "skipped": 0,
        "expected_failures": 0, "unexpected_successes": 0,
    }
    result = _RESULT_RE.search(output, ran.end())
    if result and result.group(2):
        for part in result.group(2).split(","):
            key, _, value = part.strip().partition("=")
            if value.isdigit():
                summary[key.replace(" ", "_")] = int(value)
    not_passed = sum(summary[k] for k in
                     ("failures", "errors", "skipped", "expected_failures", "unexpected_successes"))
    summary["passed"] = max(0, summary["ran"] - not_passed)

    findings = []
    for kind, test_id, docstring, traceback in _unittest_failure_blocks(output):
        last_line = next((ln for ln in reversed(traceback.splitlines()) if ln.strip()), "")
        findings.append(Finding(
            location=_last_project_frame(traceback, root),
            code=test_id,
            message=last_line or docstring or kind,
            severity=kind,
            detail="\n".join(filter(None, [docstring, traceback])),
        ))
    if summary["ran"] == 0:
        findings.append(Finding(location="tests/", code="no-tests", message="unittest discover found no tests",
                                severity="ERROR"))
    return summary, findings


_PYTEST_FRAME_RE = re.compile(r"^(\S+\.py):(\d+): ", re.MULTILINE)


def parse_junit(xml_text: str, cwd: Path, root: Path) -> tuple[dict[str, float], list[Finding]]:
    """Parse a pytest `--junitxml` report (root is <testsuites> or a single <testsuite>)."""
    # The XML is written by pytest on this machine during the run, not taken from an untrusted source.
    document = ET.fromstring(xml_text)  # nosec B314
    suites = list(document.iter("testsuite"))
    summary: dict[str, float] = {
        "ran": sum(int(s.get("tests", 0)) for s in suites),
        "failures": sum(int(s.get("failures", 0)) for s in suites),
        "errors": sum(int(s.get("errors", 0)) for s in suites),
        "skipped": sum(int(s.get("skipped", 0)) for s in suites),
        "duration": sum(float(s.get("time", 0)) for s in suites),
    }
    summary["passed"] = max(0, summary["ran"] - summary["failures"] - summary["errors"] - summary["skipped"])

    resolved_root = root.resolve()
    findings = []
    for case in document.iter("testcase"):
        for outcome in case:
            if outcome.tag not in ("failure", "error"):
                continue
            traceback = (outcome.text or "").strip()
            location = _last_project_frame(traceback, root)
            if not location:
                for path, line in _PYTEST_FRAME_RE.findall(traceback):
                    candidate = Path(path) if Path(path).is_absolute() else (cwd / path)
                    if _is_project_path(candidate, resolved_root):
                        location = f"{relative_path(path, cwd, root)}:{line}"
            message = (outcome.get("message") or "").strip().splitlines()
            findings.append(Finding(
                location=location,
                code=f"{case.get('classname', '')}::{case.get('name', '')}",
                message=message[0] if message else outcome.tag,
                severity="FAIL" if outcome.tag == "failure" else "ERROR",
                detail=traceback,
            ))
    if summary["ran"] == 0:
        findings.append(Finding(location="tests/", code="no-tests", message="pytest collected no tests",
                                severity="ERROR"))
    return summary, findings


def uses_pytest(cwd: Path) -> bool:
    """A component's check.sh is its canonical quality gate; follow it when it runs pytest."""
    check_script = cwd / "check.sh"
    if not check_script.is_file():
        return False
    lines = check_script.read_text(encoding="utf-8").splitlines()
    return any(re.search(r"\bpytest\b", line) for line in lines if not line.lstrip().startswith("#"))


def parse_bandit(stdout: str, cwd: Path, root: Path) -> list[Finding]:
    data = json.loads(stdout or "{}")
    findings = []
    for item in data.get("results", []):
        cwe = item.get("issue_cwe") or {}
        more_info = safe_url(item.get("more_info") or "")
        links = [("Bandit docs", more_info)] if more_info else []
        cwe_link = safe_url(cwe.get("link") or "")
        if cwe_link:
            links.append((f"CWE-{cwe.get('id')}", cwe_link))
        findings.append(Finding(
            location=f"{relative_path(item.get('filename', ''), cwd, root)}:{item.get('line_number', 0)}",
            code=item.get("test_id", ""),
            message=item.get("issue_text", ""),
            severity=(item.get("issue_severity") or "UNDEFINED").upper(),
            url=more_info,
            detail=item.get("code") or "",
            links=links,
            meta={"confidence": (item.get("issue_confidence") or "").upper(), "test": item.get("test_name") or "",
                  "col": str(item["col_offset"]) if isinstance(item.get("col_offset"), int) else ""},
        ))
    for error in data.get("errors", []):
        findings.append(Finding(
            location=relative_path(error.get("filename", ""), cwd, root),
            code="scan-error",
            message=error.get("reason", ""),
            severity="ERROR",
        ))
    return findings


def parse_uv_audit(stdout: str) -> tuple[dict[str, float], list[Finding]]:
    data = json.loads(stdout or "{}")
    findings = []
    for vuln in data.get("vulnerabilities", []):
        dependency = vuln.get("dependency") or {}
        display_id = vuln.get("display_id") or vuln.get("id") or ""
        advisory_ids = [display_id] + [a for a in vuln.get("aliases") or [] if a != display_id]
        links = [(a, advisory_url(a)) for a in advisory_ids if advisory_url(a)]
        fixes = vuln.get("fix_versions") or []
        name, version = dependency.get("name", "?"), dependency.get("version", "?")
        findings.append(Finding(
            location=f"{name}=={version}",
            code=display_id,
            message=vuln.get("summary") or "",
            severity="FIX AVAILABLE" if fixes else "NO FIX",
            url=safe_url(vuln.get("link") or "") or advisory_url(display_id),
            detail=vuln.get("description") or "",
            links=links,
            meta={"package": name, "installed": version, "fixed_in": ", ".join(fixes) or "\u2014",
                  "published": (vuln.get("published") or "")[:10]},
        ))
    for status in data.get("adverse_statuses", []):
        findings.append(Finding(location="", code="adverse-status", message=json.dumps(status, sort_keys=True),
                                severity="WARNING"))
    summary = {k: float(v) for k, v in (data.get("summary") or {}).items() if isinstance(v, (int, float))}
    return summary, findings


# --------------------------------------------------------------------------------------------------
# Baseline comparison
# --------------------------------------------------------------------------------------------------

def finding_key(check: str, component: str, code: str, location: str, message: str) -> FindingKey:
    """Stable identity for a finding across edits (ignores line/column numbers which shift)."""
    return (check, component, code, location.split(":", 1)[0], message)


def compare_reports(previous: dict[str, Any], current: Sequence[CheckResult]) -> ReportDelta:
    """Compare current results against a previous JSON report, scoped to current (check, component) pairs."""
    raw_meta = previous.get("meta")
    prev_meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    delta = ReportDelta(
        baseline_commit=str(prev_meta.get("commit", "")),
        baseline_generated=str(prev_meta.get("generated", "")),
    )
    current_pairs = {(r.check, r.component) for r in current}

    prev_by_pair: dict[tuple[str, str], Counter[FindingKey]] = {}
    for raw_result in previous.get("results") or []:
        if not isinstance(raw_result, dict):
            continue
        pair = (str(raw_result.get("check", "")), str(raw_result.get("component", "")))
        if pair not in current_pairs:
            continue
        counter = prev_by_pair.setdefault(pair, Counter())
        for raw_finding in raw_result.get("findings") or []:
            if not isinstance(raw_finding, dict):
                continue
            key = finding_key(
                pair[0], pair[1],
                str(raw_finding.get("code", "")),
                str(raw_finding.get("location", "")),
                str(raw_finding.get("message", "")),
            )
            counter[key] += 1

    for result in current:
        pair = (result.check, result.component)
        prev_counter = prev_by_pair.get(pair, Counter())
        remaining_prev = Counter(prev_counter)
        curr_counter: Counter[FindingKey] = Counter()
        new_indices: set[int] = set()
        for idx, f in enumerate(result.findings):
            key = finding_key(result.check, result.component, f.code, f.location, f.message)
            curr_counter[key] += 1
            if remaining_prev[key] > 0:
                remaining_prev[key] -= 1
            else:
                new_indices.add(idx)

        new_count = len(new_indices)
        fixed_count = sum((prev_counter - curr_counter).values())
        if new_indices:
            delta.new_finding_indices[pair] = new_indices
        if new_count:
            delta.new_count += new_count
            delta.new_by_check[result.check] = delta.new_by_check.get(result.check, 0) + new_count
            delta.new_by_pair[pair] = new_count
        if fixed_count:
            delta.fixed_count += fixed_count
            delta.fixed_by_check[result.check] = delta.fixed_by_check.get(result.check, 0) + fixed_count
            delta.fixed_by_pair[pair] = fixed_count

    return delta


# --------------------------------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------------------------------

def _tool_env() -> dict[str, str]:
    # Drop VIRTUAL_ENV (this script's own env) so `uv run` uses each component's .venv without warnings.
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    env["NO_COLOR"] = "1"
    return env


def run_command(cmd: Sequence[str], cwd: Path, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    # Fixed argv built in this module; never a shell.
    return subprocess.run(  # nosec B603
        list(cmd), cwd=cwd, capture_output=True, text=True, env=_tool_env(), check=False, timeout=timeout,
    )


def _result(check: str, component: str, returncode: int, findings: list[Finding], started: float,
            raw_output: str, summary: dict[str, float] | None = None) -> CheckResult:
    if returncode == 0 and not findings:
        status = "pass"
    elif findings:
        status = "fail"
    else:
        status = "error"
    return CheckResult(
        check=check, component=component, status=status, findings=findings, summary=summary or {},
        output=tail(raw_output) if status == "error" else "", duration=time.monotonic() - started,
    )


def _package_dir(cwd: Path) -> str | None:
    return cwd.name if (cwd / cwd.name).is_dir() else None


def _has_bandit_config(cwd: Path) -> bool:
    pyproject = cwd / "pyproject.toml"
    if not pyproject.is_file():
        return False
    return "bandit" in load_pyproject(cwd).get("tool", {})


def uv_tls_flags(root: Path) -> tuple[str, ...]:
    """Use `--system-certs` on modern uv (avoiding `--native-tls` deprecation warnings), else `--native-tls`."""
    try:
        proc = run_command(["uv", "--help"], root, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return ("--native-tls",)
    help_text = proc.stdout + proc.stderr
    if "--system-certs" in help_text:
        return ("--system-certs",)
    if "--native-tls" in help_text:
        return ("--native-tls",)
    return ()


def uv_audit_available(root: Path) -> bool:
    try:
        return run_command(["uv", "audit", "--help"], root, timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def uv_audit_ignore_flag(root: Path) -> str:
    """Prefer `--ignore-until-fixed` so ignored advisories resurface automatically once a fix ships."""
    try:
        proc = run_command(["uv", "audit", "--help"], root, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return "--ignore"
    return "--ignore-until-fixed" if "--ignore-until-fixed" in (proc.stdout + proc.stderr) else "--ignore"


def run_ruff(component: str, root: Path, cfg: RunConfig | None = None) -> CheckResult:
    cfg = cfg or RunConfig()
    cwd, started = root / component, time.monotonic()
    # Mirrors CI (pr-validation.yml) and avoids syncing each component's .venv just to lint.
    proc = run_command(["uv", "tool", "run", *cfg.tls_flags, "ruff", "check", ".", "--output-format", "json"],
                       cwd, timeout=cfg.timeout)
    try:
        findings = parse_ruff(proc.stdout, cwd, root)
    except (ValueError, KeyError):
        findings = []
    return _result("ruff", component, proc.returncode, findings, started, proc.stdout + proc.stderr)


def run_mypy(component: str, root: Path, cfg: RunConfig | None = None) -> CheckResult:
    cfg = cfg or RunConfig()
    cwd, started = root / component, time.monotonic()
    targets = [_package_dir(cwd) or "."] + (["tests"] if (cwd / "tests").is_dir() else [])
    # Same pinning as run-all-mypy.sh: Python 3.13 target, OS trust store for corporate TLS proxies.
    proc = run_command(["uv", "tool", "run", *cfg.tls_flags, "--python", "3.13", "mypy", *targets,
                        "--ignore-missing-imports", "-O", "json"], cwd, timeout=cfg.timeout)
    try:
        findings = parse_mypy(proc.stdout, cwd, root)
    except ValueError:
        findings = []
    return _result("mypy", component, proc.returncode, findings, started, proc.stdout + proc.stderr)


def _sync_command(component: str, root: Path, cfg: RunConfig) -> list[str]:
    cmd = ["uv", "sync", *cfg.tls_flags, "--locked", "--all-groups"]
    if cfg.sync_mode == "all":
        cmd.append("--reinstall")
    elif cfg.sync_mode == "targeted":
        # Only reinstall local path dependencies (e.g. shared_libs/*) so uv doesn't waste time
        # reinstalling unchanged third-party wheels while still picking up local library edits.
        for pkg in local_path_packages(component, root, cfg.source_graph):
            cmd.extend(["--reinstall-package", pkg])
    return cmd


def run_tests(component: str, root: Path, cfg: RunConfig | None = None) -> CheckResult:
    cfg = cfg or RunConfig()
    cwd, started = root / component, time.monotonic()
    if not (cwd / "tests").is_dir():
        return CheckResult("tests", component, "skipped", output="No tests/ directory")
    if cfg.sync_mode != "none":
        sync = run_command(_sync_command(component, root, cfg), cwd, timeout=cfg.timeout)
        if sync.returncode != 0:
            return CheckResult("tests", component, "error", output=tail(sync.stdout + sync.stderr),
                               duration=time.monotonic() - started)
    runner = "pytest" if uses_pytest(cwd) else "unittest"
    summary: dict[str, float] | None
    if runner == "pytest":
        with tempfile.TemporaryDirectory() as tmp:
            junit = Path(tmp) / "junit.xml"
            proc = run_command(["uv", "run", "--no-sync", "pytest", "tests", "-q", "-p", "no:cacheprovider",
                                f"--junitxml={junit}"], cwd, timeout=cfg.timeout)
            try:
                summary, findings = parse_junit(junit.read_text(encoding="utf-8"), cwd, root)
            except (OSError, ET.ParseError):
                summary, findings = None, []
    else:
        proc = run_command(["uv", "run", "--no-sync", "python", "-m", "unittest", "discover", "tests", "-v"],
                           cwd, timeout=cfg.timeout)
        summary, findings = parse_unittest(proc.stdout + proc.stderr, root)
    output = proc.stdout + proc.stderr
    if summary is None:
        return CheckResult("tests", component, "error", output=tail(output), duration=time.monotonic() - started,
                           runner=runner)
    result = _result("tests", component, proc.returncode, findings, started, output, summary)
    result.runner = runner
    return result


def run_bandit(component: str, root: Path, cfg: RunConfig | None = None) -> CheckResult:
    cfg = cfg or RunConfig()
    cwd, started = root / component, time.monotonic()
    package = _package_dir(cwd)
    if package:
        targets = [package] + (["tests"] if (cwd / "tests").is_dir() else [])
    else:
        targets = [".", "-x", "./.venv"]
    config_args = ["-c", "pyproject.toml"] if _has_bandit_config(cwd) else []
    proc = run_command(["uv", "tool", "run", *cfg.tls_flags, "bandit", *config_args, "-r", *targets,
                        "--severity-level", "medium", "-f", "json", "-q"], cwd, timeout=cfg.timeout)
    try:
        findings = parse_bandit(proc.stdout, cwd, root)
    except ValueError:
        findings = []
    return _result("bandit", component, proc.returncode, findings, started, proc.stdout + proc.stderr)


def run_audit(component: str, root: Path, cfg: RunConfig | None = None) -> CheckResult:
    cfg = cfg or RunConfig()
    cwd, started = root / component, time.monotonic()
    ignores = [arg for advisory in cfg.audit_ignores for arg in (cfg.audit_ignore_flag, advisory)]
    proc = run_command(["uv", "audit", *cfg.tls_flags, "--locked", "--output-format", "json", *ignores],
                       cwd, timeout=cfg.timeout)
    try:
        summary, findings = parse_uv_audit(proc.stdout)
    except ValueError:
        summary, findings = {}, []
    return _result("audit", component, proc.returncode, findings, started, proc.stdout + proc.stderr, summary)


def _safe_run(check: str, component: str, runner: Callable[[str, Path, RunConfig], CheckResult],
              root: Path, cfg: RunConfig) -> CheckResult:
    started = time.monotonic()
    try:
        return runner(component, root, cfg)
    except subprocess.TimeoutExpired as exc:
        partial = tail(_decode(exc.stdout) + "\n" + _decode(exc.stderr), 40)
        msg = f"Timed out after {exc.timeout:.0f}s"
        if partial:
            msg = f"{msg}\n\n{partial}"
        return CheckResult(check, component, "error", output=msg, duration=time.monotonic() - started)
    except OSError as exc:
        return CheckResult(check, component, "error", output=f"Failed to execute {check}: {exc}",
                           duration=time.monotonic() - started)


# --------------------------------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------------------------------

def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def anchor_id(check: str, component: str) -> str:
    return f"{check}--{_slug(component)}"


def _status_chip(status: str, text: str | None = None) -> str:
    return f'<span class="chip chip--{_e(status)}">{_e(text or status.upper())}</span>'


def _severity_chip(severity: str) -> str:
    return f'<span class="sev sev--{_slug(severity)}">{_e(severity)}</span>'


def _link(url: str, text: str) -> str:
    url = safe_url(url)
    if not url:
        return _e(text)
    return f'<a href="{_e(url)}" target="_blank" rel="noopener noreferrer">{_e(text)}</a>'


def _message_cell(finding: Finding, is_new: bool = False) -> str:
    badge = '<span class="badge-new">NEW</span> ' if is_new else ""
    if not finding.detail:
        return f"{badge}{_e(finding.message)}"
    return (f'<details class="detail"><summary>{badge}{_e(finding.message)}</summary>'
            f'<pre>{_e(finding.detail)}</pre></details>')


def _links_cell(finding: Finding) -> str:
    return " ".join(f'<span class="ext">{_link(url, label)}</span>' for label, url in finding.links)


Column = tuple[str, Callable[[Finding], str]]

COLUMNS: dict[str, list[Column]] = {
    "ruff": [
        ("Location", lambda f: f"<code>{_e(f.location)}</code>"),
        ("Rule", lambda f: _link(f.url, f.code)),
        ("Message", _message_cell),
        ("Fix", lambda f: _e(f.meta.get("fix", ""))),
    ],
    "mypy": [
        ("Location", lambda f: f"<code>{_e(f.location)}</code>"),
        ("Code", lambda f: _link(f.url, f.code) if f.code else "&mdash;"),
        ("Message", _message_cell),
    ],
    "tests": [
        ("Result", lambda f: _severity_chip(f.severity)),
        ("Test", lambda f: f"<code>{_e(f.code)}</code>"),
        ("Message", _message_cell),
        ("Location", lambda f: f"<code>{_e(f.location)}</code>" if f.location else "&mdash;"),
    ],
    "bandit": [
        ("Severity", lambda f: _severity_chip(f.severity)),
        ("Confidence", lambda f: _e(f.meta.get("confidence", ""))),
        ("Location", lambda f: f"<code>{_e(f.location)}</code>"),
        ("Test", lambda f: _link(f.url, f"{f.code} {f.meta.get('test', '')}".strip())),
        ("Issue", _message_cell),
        ("Links", _links_cell),
    ],
    "audit": [
        ("Status", lambda f: _severity_chip(f.severity)),
        ("Package", lambda f: f"<code>{_e(f.meta.get('package', f.location))}</code>"),
        ("Installed", lambda f: _e(f.meta.get("installed", ""))),
        ("Fixed in", lambda f: _e(f.meta.get("fixed_in", ""))),
        ("Advisory", lambda f: _link(f.url, f.code)),
        ("Summary", _message_cell),
        ("Links", _links_cell),
    ],
}


def _search_text(finding: Finding) -> str:
    parts = [finding.location, finding.code, finding.message, finding.severity, *finding.meta.values()]
    return " ".join(parts).lower()


def _findings_table(check: str, findings: list[Finding], new_indices: set[int] | None = None) -> str:
    columns = COLUMNS[check]
    head = "".join(f"<th>{_e(name)}</th>" for name, _ in columns)
    rows = []
    for idx, finding in enumerate(findings):
        is_new = bool(new_indices and idx in new_indices)
        cells = "".join(
            f'<td class="msg">{_message_cell(finding, is_new=is_new)}</td>' if render is _message_cell
            else f"<td>{render(finding)}</td>"
            for _, render in columns
        )
        new_attr = ' data-new="1"' if is_new else ""
        rows.append(
            f'<tr data-sev="{_e(finding.severity)}" data-text="{_e(_search_text(finding))}"{new_attr}>{cells}</tr>'
        )
    return (f'<div class="table-wrap"><table class="findings"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _tests_bar(summary: dict[str, float], runner: str) -> str:
    ran = summary.get("ran", 0) or 0
    if not ran:
        return ""
    segments = [
        ("passed", "passed", summary.get("passed", 0)),
        ("failed", "failed", summary.get("failures", 0)),
        ("errored", "errored", summary.get("errors", 0)),
        ("xfailed", "expected fail", summary.get("expected_failures", 0)),
        ("xpassed", "unexpected pass", summary.get("unexpected_successes", 0)),
        ("skipped", "skipped", summary.get("skipped", 0)),
    ]
    bar = "".join(f'<span class="bar__{cls}" style="width:{100 * count / ran:.2f}%"></span>'
                  for cls, _, count in segments if count)
    legend = " &middot; ".join(f"{int(count)} {label}" for _, label, count in segments if count)
    via = f" with {_e(runner)}" if runner else ""
    return (f'<div class="tests-summary"><div class="bar">{bar}</div>'
            f'<div class="muted">{int(ran)} run{via} in {summary.get("duration", 0):.2f}s &middot; {legend}</div>'
            '</div>')


def _issue_label(result: CheckResult) -> str:
    count = len(result.findings)
    if result.check == "tests" and result.summary:
        return f"{int(result.summary.get('passed', 0))}/{int(result.summary.get('ran', 0))} passed"
    noun = "vulnerability" if result.check == "audit" else "issue"
    plural = "vulnerabilities" if result.check == "audit" else "issues"
    return f"{count} {noun if count == 1 else plural}"


def _delta_inline(new_count: int, fixed_count: int) -> str:
    parts = []
    if new_count:
        parts.append(f'<span class="delta-new">+{new_count} new</span>')
    if fixed_count:
        parts.append(f'<span class="delta-fixed">&minus;{fixed_count} fixed</span>')
    return " &middot; ".join(parts)


def _component_card(result: CheckResult, delta: ReportDelta | None = None) -> str:
    pair = (result.check, result.component)
    new_indices = delta.new_finding_indices.get(pair) if delta else None
    if result.status == "error":
        body = ('<p class="tool-error">The tool did not complete. Last output:</p>'
                f'<pre class="raw">{_e(result.output)}</pre>')
    elif result.status == "skipped":
        body = f'<p class="muted">Skipped{": " + _e(result.output) if result.output else ""}.</p>'
    elif result.findings:
        body = _findings_table(result.check, result.findings, new_indices=new_indices)
    elif result.status == "fail" and result.output:
        body = ('<p class="tool-error">Check exited non-zero without structured findings. Last output:</p>'
                f'<pre class="raw">{_e(result.output)}</pre>')
    else:
        body = '<p class="ok-text">No issues found.</p>'
    if result.check == "tests":
        body = _tests_bar(result.summary, result.runner) + body
    open_attr = " open" if result.status in ("fail", "error") else ""
    delta_html = ""
    if delta:
        inline = _delta_inline(delta.new_by_pair.get(pair, 0), delta.fixed_by_pair.get(pair, 0))
        if inline:
            delta_html = f" &middot; {inline}"
    return (
        f'<details class="comp" id="{anchor_id(result.check, result.component)}" data-status="{_e(result.status)}" '
        f'data-name="{_e(result.component.lower())}"{open_attr}>'
        f'<summary>{_status_chip(result.status)}<span class="comp__name">{_e(result.component)}</span>'
        f'<span class="comp__meta">{_e(_issue_label(result))}{delta_html} &middot; {result.duration:.1f}s</span>'
        f'</summary><div class="comp__body">{body}</div></details>'
    )


def _toolbar(results: list[CheckResult], has_new: bool = False) -> str:
    severities = sorted({f.severity for r in results for f in r.findings})
    options = "".join(f'<option value="{_e(s)}">{_e(s)}</option>' for s in severities)
    severity_select = (f'<select data-severity aria-label="Severity"><option value="">All severities</option>'
                       f'{options}</select>') if len(severities) > 1 else ""
    new_only = '<label class="toggle"><input type="checkbox" data-new-only> New only</label>' if has_new else ""
    return (
        '<div class="toolbar">'
        '<input type="search" data-filter placeholder="Filter by component, file, code or message\u2026" '
        'aria-label="Filter">'
        f'{severity_select}'
        '<label class="toggle"><input type="checkbox" data-failing-only> Problems only</label>'
        f'{new_only}'
        '<button type="button" class="btn" data-reset hidden>Reset</button>'
        '<span class="match-count" data-match-count></span>'
        '<button type="button" class="btn" data-expand="open">Expand all</button>'
        '<button type="button" class="btn" data-expand="close">Collapse all</button>'
        '</div>'
    )


def _sorted_results(results: Iterable[CheckResult]) -> list[CheckResult]:
    return sorted(results, key=lambda r: (STATUS_ORDER.get(r.status, 9), r.component))


def _audit_ignore_banner(ignores: Sequence[str], ignore_flag: str) -> str:
    if not ignores:
        return ""
    mode = "until a fix is published" if ignore_flag == "--ignore-until-fixed" else "configured ignore list"
    links = ", ".join(_link(advisory_url(adv), adv) for adv in ignores)
    return f'<p class="notice">Ignored advisories ({_e(mode)}): {links}</p>'


def _check_section(check: str, results: list[CheckResult], heading: bool, delta: ReportDelta | None = None,
                   banner: str = "") -> str:
    cards = "".join(_component_card(r, delta=delta) for r in _sorted_results(results))
    title = f'<h2 class="section-title">{_e(CHECK_LABELS[check])}</h2>' if heading else ""
    return f'<section class="check-section">{title}{banner}{cards}</section>'


def _tab_status(results: list[CheckResult]) -> str:
    statuses = {r.status for r in results}
    for status in ("error", "fail"):
        if status in statuses:
            return status
    return "pass" if "pass" in statuses else "skipped"


def _tab_badge_text(results: list[CheckResult]) -> str:
    issues = sum(len(r.findings) for r in results)
    errors = sum(1 for r in results if r.status == "error")
    if errors and issues:
        return f"{issues} + {errors}!"
    if errors:
        return f"{errors}!"
    return str(issues)


def _kpi_card(check: str, results: list[CheckResult], delta: ReportDelta | None = None) -> str:
    status = _tab_status(results)
    ran = [r for r in results if r.status != "skipped"]
    passing = sum(1 for r in ran if r.status == "pass")
    if check == "tests":
        total_ran = int(sum(r.summary.get("ran", 0) for r in results))
        failed = int(sum(r.summary.get("failures", 0) + r.summary.get("errors", 0) for r in results))
        value, caption = f"{total_ran}", f"tests run &middot; {failed} failed"
    elif check == "audit":
        value, caption = f"{sum(len(r.findings) for r in results)}", "known vulnerabilities"
    elif check == "bandit":
        high = sum(1 for r in results for f in r.findings if f.severity == "HIGH")
        value, caption = f"{sum(len(r.findings) for r in results)}", f"medium+ issues &middot; {high} high"
    else:
        value, caption = f"{sum(len(r.findings) for r in results)}", "issues"
    errors = sum(1 for r in results if r.status == "error")
    error_note = f' &middot; <span class="err-text">{errors} tool error{"s" if errors != 1 else ""}</span>' \
        if errors else ""
    delta_note = ""
    if delta:
        inline = _delta_inline(delta.new_by_check.get(check, 0), delta.fixed_by_check.get(check, 0))
        if inline:
            delta_note = f" &middot; {inline}"
    return (
        f'<a class="kpi kpi--{_e(status)}" href="#{TAB_OF_CHECK[check]}">'
        f'<div class="kpi__label">{_e(CHECK_LABELS[check])}</div>'
        f'<div class="kpi__value">{value}</div><div class="kpi__caption">{caption}</div>'
        f'<div class="kpi__foot">{passing}/{len(ran)} components clean{error_note}{delta_note}</div></a>'
    )


def _matrix(components: list[str], checks: list[str], by_key: dict[tuple[str, str], CheckResult]) -> str:
    head = "".join(f"<th>{_e(CHECK_LABELS[c])}</th>" for c in checks)
    rows = []
    for component in components:
        cells = []
        for check in checks:
            result = by_key.get((check, component))
            if result is None:
                cells.append("<td></td>")
                continue
            text = {"pass": "\u2713", "skipped": "\u2014", "error": "!"}.get(result.status, str(len(result.findings)))
            title = f"{CHECK_LABELS[check]}: {result.status} ({_issue_label(result)})"
            cells.append(f'<td><a class="cell cell--{_e(result.status)}" title="{_e(title)}" '
                         f'href="#{anchor_id(check, component)}">{_e(text)}</a></td>')
        rows.append(f'<tr><th scope="row"><code>{_e(component)}</code></th>{"".join(cells)}</tr>')
    return (f'<div class="table-wrap"><table class="matrix"><thead><tr><th>Component</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _header_delta_chip(delta: ReportDelta | None) -> str:
    if delta is None:
        return ""
    ref = delta.baseline_commit or delta.baseline_generated or "previous"
    if delta.new_count == 0 and delta.fixed_count == 0:
        return f'<span class="delta-pill delta-pill--same">No change vs {_e(ref)}</span>'
    parts = []
    if delta.new_count:
        parts.append(f"+{delta.new_count} new")
    if delta.fixed_count:
        parts.append(f"\u2212{delta.fixed_count} fixed")
    cls = "delta-pill--worse" if delta.new_count else "delta-pill--better"
    return f'<span class="delta-pill {cls}">{_e(" · ".join(parts))} vs {_e(ref)}</span>'


def render_html(results: list[CheckResult], meta: dict[str, Any], delta: ReportDelta | None = None) -> str:
    checks = [c for c in CHECKS if any(r.check == c for r in results)]
    components = sorted({r.component for r in results})
    by_key = {(r.check, r.component): r for r in results}
    tabs = [t for t in TAB_LABELS if any(TAB_OF_CHECK[c] == t for c in checks)]
    overall = "pass" if all(r.status in ("pass", "skipped") for r in results) else "fail"
    audit_ignores = meta.get("audit_ignores") or []
    audit_ignore_flag = str(meta.get("audit_ignore_flag") or "--ignore")

    tab_buttons = [
        ('<button role="tab" id="tab-btn-overview" aria-controls="tab-overview" '
         'data-tab="overview" aria-selected="true">Overview</button>')
    ]
    panels = [
        ('<section class="tab-panel" id="tab-overview" role="tabpanel" aria-labelledby="tab-btn-overview">'
         f'<div class="kpis">{"".join(_kpi_card(c, [r for r in results if r.check == c], delta) for c in checks)}</div>'
         '<h2 class="section-title">Components</h2>'
         f'{_matrix(components, checks, by_key)}</section>')
    ]
    for tab in tabs:
        tab_checks = [c for c in checks if TAB_OF_CHECK[c] == tab]
        tab_results = [r for r in results if r.check in tab_checks]
        status = _tab_status(tab_results)
        badge = _tab_badge_text(tab_results)
        tab_buttons.append(
            f'<button role="tab" id="tab-btn-{tab}" aria-controls="tab-{tab}" data-tab="{tab}" aria-selected="false">'
            f'{_e(TAB_LABELS[tab])}<span class="count count--{_e(status)}">{_e(badge)}</span></button>'
        )
        tab_has_new = bool(delta and any(delta.new_by_check.get(c, 0) > 0 for c in tab_checks))
        sections = "".join(
            _check_section(
                c,
                [r for r in tab_results if r.check == c],
                len(tab_checks) > 1,
                delta=delta,
                banner=_audit_ignore_banner(audit_ignores, audit_ignore_flag) if c == "audit" else "",
            )
            for c in tab_checks
        )
        panels.append(
            f'<section class="tab-panel" id="tab-{tab}" role="tabpanel" aria-labelledby="tab-btn-{tab}" hidden>'
            f'{_toolbar(tab_results, has_new=tab_has_new)}{sections}</section>'
        )

    delta_chip = _header_delta_chip(delta)
    status_row = f'<div class="top__badges">{_status_chip(overall, "ALL PASSED" if overall == "pass" else "ISSUES FOUND")}{delta_chip}</div>'
    return (
        '<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Integration Hub quality report &ndash; {_e(meta["generated"])}</title>'
        f'<style>{CSS}</style></head><body>'
        '<header class="top"><div class="top__inner">'
        '<div><div class="brand">DHCW &middot; Integration Hub</div><h1>Quality report</h1></div>'
        f'<div class="top__meta">{status_row}'
        f'<div>Branch <code>{_e(meta["branch"])}</code> @ <code>{_e(meta["commit"])}</code></div>'
        f'<div>{_e(meta["generated"])} &middot; {_e(meta["components"])} components &middot; '
        f'{_e(meta["duration"])}</div></div></div>'
        f'<nav class="tabs" role="tablist">{"".join(tab_buttons)}</nav></header>'
        f'<main>{"".join(panels)}</main><script>{JS}</script></body></html>'
    )


CSS = """
:root{--nhs-blue:#325083;--dhcw-blue:#12A3C9;--navy:#1B294A;--yellow:#F8CA4D;--bg:#f3f5f9;--card:#fff;
--text:#1d2433;--muted:#5d6b82;--line:#e2e7ef;--pass:#1f8a4c;--fail:#c62828;--error:#b26a00;--skip:#8a94a6}
*{box-sizing:border-box}
body{margin:0;font-family:Rubik,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);
color:var(--text);font-size:14px;line-height:1.45}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}
a{color:var(--nhs-blue)}
.top{background:linear-gradient(120deg,var(--navy),var(--nhs-blue));color:#fff;position:sticky;top:0;z-index:5;
box-shadow:0 2px 12px rgba(27,41,74,.25)}
.top__inner{max-width:1400px;margin:0 auto;padding:18px 24px 10px;display:flex;justify-content:space-between;
gap:24px;align-items:flex-end;flex-wrap:wrap}
.brand{color:var(--yellow);font-size:12px;letter-spacing:.08em;text-transform:uppercase;font-weight:600}
h1{margin:2px 0 0;font-size:26px;font-weight:600}
.top__meta{text-align:right;font-size:12.5px;opacity:.95;display:flex;flex-direction:column;gap:4px;align-items:flex-end}
.top__badges{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
.top__meta code{background:rgba(255,255,255,.14);padding:1px 6px;border-radius:4px;color:#fff}
.tabs{max-width:1400px;margin:0 auto;padding:0 16px;display:flex;gap:4px;overflow-x:auto}
.tabs button{background:none;border:0;color:rgba(255,255,255,.75);font:inherit;font-weight:500;padding:10px 16px;
cursor:pointer;border-bottom:3px solid transparent;display:flex;gap:8px;align-items:center;white-space:nowrap}
.tabs button:hover{color:#fff}
.tabs button:focus-visible{outline:2px solid var(--yellow);outline-offset:-2px}
.tabs button[aria-selected=true]{color:#fff;border-bottom-color:var(--dhcw-blue)}
.count{background:rgba(255,255,255,.18);border-radius:999px;padding:0 8px;font-size:12px}
.count--fail{background:var(--fail)}.count--error{background:var(--yellow);color:var(--navy)}
main{max-width:1400px;margin:0 auto;padding:24px}
.section-title{font-size:16px;color:var(--navy);margin:28px 0 12px;font-weight:600}
.notice{margin:0 0 12px;padding:8px 12px;background:#eef6fb;border-left:3px solid var(--dhcw-blue);
border-radius:6px;color:var(--navy);font-size:12.5px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}
.kpi{display:block;text-decoration:none;color:inherit;background:var(--card);border-radius:12px;padding:16px 18px;
border-top:4px solid var(--skip);box-shadow:0 1px 3px rgba(27,41,74,.08);transition:transform .15s,box-shadow .15s}
.kpi:hover{transform:translateY(-2px);box-shadow:0 6px 16px rgba(27,41,74,.12)}
.kpi--pass{border-top-color:var(--pass)}.kpi--fail{border-top-color:var(--fail)}.kpi--error{border-top-color:var(--yellow)}
.kpi__label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em;font-weight:600}
.kpi__value{font-size:34px;font-weight:600;color:var(--navy);line-height:1.2;margin-top:4px}
.kpi__caption{color:var(--muted)}
.kpi__foot{margin-top:10px;font-size:12.5px;border-top:1px solid var(--line);padding-top:8px}
.err-text{color:var(--error);font-weight:600}
.delta-pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11.5px;font-weight:600}
.delta-pill--same{background:rgba(255,255,255,.16);color:#fff}
.delta-pill--better{background:#e3f4ea;color:var(--pass)}
.delta-pill--worse{background:#fde7e7;color:var(--fail)}
.delta-new{color:var(--fail);font-weight:600}.delta-fixed{color:var(--pass);font-weight:600}
.badge-new{display:inline-block;padding:0 6px;border-radius:4px;font-size:10.5px;font-weight:700;
background:#fde7e7;color:var(--fail);letter-spacing:.04em;vertical-align:1px}
.table-wrap{overflow-x:auto;background:var(--card);border-radius:10px;box-shadow:0 1px 3px rgba(27,41,74,.08)}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}
thead th{background:#f7f9fc;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em;
font-weight:600}
tbody tr:hover{background:#f7fbfe}
.findings th{white-space:nowrap}.findings td{min-width:70px}.findings code{overflow-wrap:anywhere}
.findings td.msg{min-width:280px}.findings td:has(>code){min-width:220px}.findings td>a,.ext a{white-space:nowrap}
.matrix td,.matrix thead th{text-align:center}.matrix thead th:first-child{text-align:left}
.matrix th[scope=row]{font-weight:400}
.cell{display:inline-block;min-width:34px;padding:2px 8px;border-radius:999px;text-decoration:none;font-weight:600;
font-size:12.5px}
.cell--pass{background:#e3f4ea;color:var(--pass)}.cell--fail{background:#fde7e7;color:var(--fail)}
.cell--error{background:#fff3cf;color:var(--error)}.cell--skipped{background:#eef0f4;color:var(--skip)}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11.5px;font-weight:600;letter-spacing:.04em;
color:#fff;background:var(--skip)}
.chip--pass{background:var(--pass)}.chip--fail{background:var(--fail)}.chip--error{background:var(--yellow);color:var(--navy)}
.sev{display:inline-block;padding:1px 8px;border-radius:6px;font-size:11.5px;font-weight:600;white-space:nowrap;
background:#eef0f4;color:var(--muted)}
.sev--high,.sev--error,.sev--fail,.sev--no-fix{background:#fde7e7;color:var(--fail)}
.sev--medium,.sev--warning,.sev--unexpected-success{background:#fff3cf;color:var(--error)}
.sev--low,.sev--fix-available{background:#e1f3f9;color:#0b7493}
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:16px;background:var(--card);
padding:12px;border-radius:10px;box-shadow:0 1px 3px rgba(27,41,74,.08)}
.toolbar input[type=search]{flex:1;min-width:240px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;
font:inherit}
.toolbar select{padding:8px;border:1px solid var(--line);border-radius:8px;font:inherit;background:#fff}
.toolbar input:focus,.toolbar select:focus{outline:2px solid var(--dhcw-blue);outline-offset:1px}
.toggle{display:flex;gap:6px;align-items:center;color:var(--muted)}
.match-count{color:var(--muted);font-size:12.5px;margin-left:auto}
.btn{background:#fff;border:1px solid var(--line);border-radius:8px;padding:7px 12px;font:inherit;cursor:pointer;
color:var(--nhs-blue)}
.btn:hover{border-color:var(--dhcw-blue)}
.comp{background:var(--card);border-radius:10px;margin-bottom:10px;box-shadow:0 1px 3px rgba(27,41,74,.08);
border-left:4px solid var(--skip);scroll-margin-top:140px}
.comp[data-status=pass]{border-left-color:var(--pass)}.comp[data-status=fail]{border-left-color:var(--fail)}
.comp[data-status=error]{border-left-color:var(--yellow)}
.comp>summary{cursor:pointer;padding:12px 16px;display:flex;gap:12px;align-items:center;list-style:none}
.comp>summary::-webkit-details-marker{display:none}
.comp>summary::before{content:"\\25B8";color:var(--muted);transition:transform .15s}
.comp[open]>summary::before{transform:rotate(90deg)}
.comp__name{font-weight:600;color:var(--navy)}.comp__meta{margin-left:auto;color:var(--muted);font-size:12.5px}
.comp__body{padding:0 16px 16px}.comp__body .table-wrap{box-shadow:none;border:1px solid var(--line)}
.detail summary{cursor:pointer}.detail pre,.raw{white-space:pre-wrap;word-break:break-word;background:#0f1a2e;
color:#e6edf7;padding:12px;border-radius:8px;max-height:420px;overflow:auto;margin:8px 0 0}
.ext{display:inline-block;margin:0 6px 2px 0;font-size:12.5px}
.muted{color:var(--muted)}.ok-text{color:var(--pass);margin:4px 0}.tool-error{color:var(--error);font-weight:600}
.tests-summary{margin:4px 0 12px}
.bar{display:flex;height:8px;border-radius:999px;overflow:hidden;background:#eef0f4;margin-bottom:6px}
.bar__passed{background:var(--pass)}.bar__failed{background:var(--fail)}.bar__errored{background:var(--yellow)}
.bar__xfailed{background:var(--dhcw-blue)}.bar__xpassed{background:#d97706}.bar__skipped{background:var(--skip)}
[hidden]{display:none!important}
@media print{.top{position:static}.toolbar,.tabs{display:none}.tab-panel{display:block!important}}
"""

JS = """
(() => {
  const tabs = [...document.querySelectorAll('[role=tab]')];
  const panels = [...document.querySelectorAll('.tab-panel')];
  const activate = (name, focus = false) => {
    tabs.forEach(t => {
      const selected = t.dataset.tab === name;
      t.setAttribute('aria-selected', String(selected));
      t.tabIndex = selected ? 0 : -1;
      if (selected && focus) t.focus();
    });
    panels.forEach(p => { p.hidden = p.id !== 'tab-' + name; });
  };
  tabs.forEach((t, idx) => {
    t.addEventListener('click', () => {
      history.replaceState(null, '', '#' + t.dataset.tab);
      activate(t.dataset.tab);
    });
    t.addEventListener('keydown', (ev) => {
      let next = null;
      if (ev.key === 'ArrowRight') next = tabs[(idx + 1) % tabs.length];
      else if (ev.key === 'ArrowLeft') next = tabs[(idx - 1 + tabs.length) % tabs.length];
      else if (ev.key === 'Home') next = tabs[0];
      else if (ev.key === 'End') next = tabs[tabs.length - 1];
      if (next) {
        ev.preventDefault();
        history.replaceState(null, '', '#' + next.dataset.tab);
        activate(next.dataset.tab, true);
      }
    });
  });

  const applyFilters = (panel) => {
    const filterEl = panel.querySelector('[data-filter]');
    const sevEl = panel.querySelector('[data-severity]');
    const probEl = panel.querySelector('[data-failing-only]');
    const newEl = panel.querySelector('[data-new-only]');
    const q = (filterEl?.value || '').trim().toLowerCase();
    const sev = sevEl?.value || '';
    const problemsOnly = Boolean(probEl?.checked);
    const newOnly = Boolean(newEl?.checked);
    const active = Boolean(q || sev || problemsOnly || newOnly);
    const comps = [...panel.querySelectorAll('.comp')];
    let visibleComps = 0;
    comps.forEach(comp => {
      const nameMatch = !q || comp.dataset.name.includes(q);
      const rawText = (comp.querySelector('.raw')?.textContent || '').toLowerCase();
      const rawMatch = Boolean(q && rawText.includes(q));
      const rows = [...comp.querySelectorAll('tr[data-text]')];
      let visibleRows = 0;
      rows.forEach(tr => {
        const show = (nameMatch || tr.dataset.text.includes(q))
          && (!sev || tr.dataset.sev === sev)
          && (!newOnly || tr.dataset.new === '1');
        tr.hidden = !show;
        if (show) visibleRows++;
      });
      const clean = comp.dataset.status === 'pass' || comp.dataset.status === 'skipped';
      const matches = rows.length
        ? (visibleRows > 0 || (!q && !sev && !newOnly))
        : ((nameMatch || rawMatch) && !sev && !newOnly);
      comp.hidden = (problemsOnly && clean) || !matches;
      if (!comp.hidden) visibleComps++;
    });
    const resetBtn = panel.querySelector('[data-reset]');
    if (resetBtn) resetBtn.hidden = !active;
    const countEl = panel.querySelector('[data-match-count]');
    if (countEl) countEl.textContent = active ? `Showing ${visibleComps} of ${comps.length}` : '';
  };

  const resetFilters = (panel) => {
    const filterEl = panel.querySelector('[data-filter]');
    const sevEl = panel.querySelector('[data-severity]');
    const probEl = panel.querySelector('[data-failing-only]');
    const newEl = panel.querySelector('[data-new-only]');
    if (filterEl) filterEl.value = '';
    if (sevEl) sevEl.value = '';
    if (probEl) probEl.checked = false;
    if (newEl) newEl.checked = false;
    applyFilters(panel);
  };

  const fromHash = () => {
    const target = decodeURIComponent(location.hash.slice(1));
    const el = target && document.getElementById(target);
    if (el && el.classList.contains('comp')) {
      const panel = el.closest('.tab-panel');
      activate(panel.id.slice(4));
      resetFilters(panel);
      el.hidden = false; el.open = true; el.scrollIntoView({block: 'start'});
    } else if (target && document.getElementById('tab-' + target)) {
      activate(target);
    } else {
      activate('overview');
    }
  };
  window.addEventListener('hashchange', fromHash);
  fromHash();

  panels.forEach(panel => {
    panel.querySelectorAll('[data-filter],[data-severity],[data-failing-only],[data-new-only]')
      .forEach(ctrl => {
        ctrl.addEventListener('input', () => applyFilters(panel));
        ctrl.addEventListener('change', () => applyFilters(panel));
      });
    panel.querySelector('[data-reset]')?.addEventListener('click', () => resetFilters(panel));
    panel.querySelectorAll('[data-expand]').forEach(btn => btn.addEventListener('click', () => {
      panel.querySelectorAll('.comp:not([hidden])').forEach(c => { c.open = btn.dataset.expand === 'open'; });
    }));
  });
})();
"""


# --------------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------------

def _git(args: list[str], root: Path) -> str:
    try:
        proc = run_command(["git", *args], root, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _default_jobs() -> int:
    return min(8, os.cpu_count() or 1)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run quality checks for every component and write an HTML report.")
    parser.add_argument("components", nargs="*",
                        help="Component directories relative to the repo root (default: all discovered)")
    parser.add_argument("--checks", default=",".join(DEFAULT_CHECK_GROUPS),
                        help=f"Comma-separated subset of: {', '.join(CHECK_GROUPS)} (default: all)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="HTML report path; a .json sidecar is written next to it")
    parser.add_argument("--changed", nargs="?", const="HEAD", default=None, metavar="REF",
                        help="Only check components changed vs REF (default: HEAD), including downstream dependents")
    parser.add_argument("-j", "--jobs", type=int, default=_default_jobs(),
                        help="Components to check in parallel (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="Per-command timeout in seconds; 0 disables (default: %(default).0f)")
    parser.add_argument("--ignore-advisory", action="append", default=[], metavar="ID",
                        help="Additional advisory ID to ignore in uv audit (repeatable)")
    sync_group = parser.add_mutually_exclusive_group()
    sync_group.add_argument("--reinstall-all", action="store_true",
                            help="Reinstall every package on uv sync (default: local path deps only)")
    sync_group.add_argument("--no-sync", action="store_true",
                            help="Skip uv sync before running unit tests")
    compare_group = parser.add_mutually_exclusive_group()
    compare_group.add_argument("--compare", type=Path, default=None, metavar="JSON",
                               help="Compare findings against an existing JSON report")
    compare_group.add_argument("--no-compare", action="store_true",
                               help="Do not automatically compare against an existing sidecar JSON")
    parser.add_argument("--open", action="store_true",
                        help="Open the generated HTML report in the default browser")
    return parser.parse_args(argv)


def resolve_checks(value: str) -> list[str]:
    requested = [c.strip().lower() for c in value.split(",") if c.strip()]
    unknown = [c for c in requested if c not in CHECK_GROUPS]
    if unknown or not requested:
        raise ValueError(f"Unknown checks {unknown or value!r}; choose from {', '.join(CHECK_GROUPS)}")
    selected = {check for group in requested for check in CHECK_GROUPS[group]}
    return [c for c in CHECKS if c in selected]


def _resolve_output_paths(raw_output: Path) -> tuple[Path, Path]:
    output = raw_output.resolve()
    if output.suffix.lower() == ".json":
        raise ValueError("--output expects an HTML path (the .json sidecar is written automatically alongside it)")
    if not output.suffix:
        output = output.with_suffix(".html")
    return output, output.with_suffix(".json")


def _load_baseline(args: argparse.Namespace, json_output: Path) -> dict[str, Any] | None:
    if args.no_compare:
        return None
    if args.compare is not None:
        path = args.compare.resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path} is not a JSON object")
        return data
    if json_output.is_file():
        try:
            data = json.loads(json_output.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, ValueError) as exc:
            LOG.warning("Skipping comparison against %s: %s", json_output, exc)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    try:
        checks = resolve_checks(args.checks)
        output, json_output = _resolve_output_paths(args.output)
    except ValueError as exc:
        LOG.error("%s", exc)
        return 2

    if args.jobs < 1:
        LOG.error("--jobs must be at least 1")
        return 2
    if args.timeout < 0:
        LOG.error("--timeout must be >= 0")
        return 2
    if args.changed is not None and args.components:
        LOG.error("Cannot combine explicit component arguments with --changed")
        return 2

    try:
        baseline = _load_baseline(args, json_output)
    except (OSError, ValueError) as exc:
        LOG.error("Cannot read baseline report %s: %s", args.compare, exc)
        return 2

    discovered = discover_components(ROOT_DIR)
    source_graph = build_source_graph(ROOT_DIR, discovered)
    if args.changed is not None:
        try:
            components = changed_components(ROOT_DIR, discovered, ref=args.changed, graph=source_graph)
        except ValueError as exc:
            LOG.error("%s", exc)
            return 2
        if not components:
            LOG.info("No components changed relative to %s; nothing to check.", args.changed)
            return 0
        LOG.info("Changed components (+ dependents) vs %s: %s", args.changed, ", ".join(components))
    elif args.components:
        wanted = [c.strip("/") for c in args.components]
        missing = [c for c in wanted if c not in discovered]
        if missing:
            LOG.error("Unknown components: %s", ", ".join(missing))
            return 2
        components = wanted
    else:
        components = discovered

    audit_ignores = tuple(dict.fromkeys([*AUDIT_IGNORES, *args.ignore_advisory]))
    sync_mode = "none" if args.no_sync else ("all" if args.reinstall_all else "targeted")
    cfg = RunConfig(
        timeout=None if args.timeout == 0 else args.timeout,
        tls_flags=uv_tls_flags(ROOT_DIR),
        audit_ignores=audit_ignores,
        audit_ignore_flag=uv_audit_ignore_flag(ROOT_DIR) if "audit" in checks else "--ignore",
        sync_mode=sync_mode,
        source_graph=source_graph,
    )

    runners: dict[str, Callable[[str, Path, RunConfig], CheckResult]] = {
        "ruff": run_ruff, "mypy": run_mypy, "tests": run_tests, "bandit": run_bandit, "audit": run_audit,
    }
    if "audit" in checks and not uv_audit_available(ROOT_DIR):
        LOG.warning("This uv install has no 'audit' subcommand; dependency scanning will be skipped")
        runners["audit"] = lambda component, _root, _cfg: CheckResult(
            "audit", component, "skipped", output="uv audit is not available in this uv install")

    started = time.monotonic()
    total = len(components)
    max_workers = min(args.jobs, max(1, total))

    def _run_component(index: int, component: str) -> list[CheckResult]:
        comp_results: list[CheckResult] = []
        for check in checks:
            result = _safe_run(check, component, runners[check], ROOT_DIR, cfg)
            comp_results.append(result)
            LOG.info("[%d/%d] %-45s %-7s %-8s %s", index, total, component, check,
                     result.status.upper(), _issue_label(result))
        return comp_results

    results_by_index: dict[int, list[CheckResult]] = {}
    try:
        if max_workers == 1:
            for index, component in enumerate(components, start=1):
                results_by_index[index] = _run_component(index, component)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_to_index = {
                    pool.submit(_run_component, index, component): index
                    for index, component in enumerate(components, start=1)
                }
                for future in concurrent.futures.as_completed(future_to_index):
                    results_by_index[future_to_index[future]] = future.result()
    except KeyboardInterrupt:
        LOG.warning("Interrupted by user.")
        return 130

    results = [r for idx in range(1, total + 1) for r in results_by_index[idx]]
    delta = compare_reports(baseline, results) if baseline is not None else None

    elapsed = time.monotonic() - started
    meta: dict[str, Any] = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], ROOT_DIR),
        "commit": _git(["rev-parse", "--short", "HEAD"], ROOT_DIR),
        "components": str(len(components)),
        "duration": f"{int(elapsed // 60)}m {int(elapsed % 60)}s",
        "audit_ignores": list(audit_ignores),
        "audit_ignore_flag": cfg.audit_ignore_flag,
    }
    if delta is not None:
        meta["compared_to"] = delta.baseline_commit or delta.baseline_generated
        meta["delta"] = {"new": delta.new_count, "fixed": delta.fixed_count}

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(results, meta, delta=delta), encoding="utf-8")
    json_output.write_text(
        json.dumps({"meta": meta, "results": [asdict(r) for r in results]}, indent=2), encoding="utf-8")

    failed = sorted({r.component for r in results if r.status in ("fail", "error")})
    LOG.info("")
    LOG.info("Report: %s", output)
    if delta is not None:
        LOG.info("Delta vs %s: +%d new, -%d fixed",
                 delta.baseline_commit or delta.baseline_generated or "previous", delta.new_count, delta.fixed_count)
    LOG.info("ALL PASSED" if not failed else f"FAILED: {' '.join(failed)}")
    if args.open:
        webbrowser.open(output.as_uri())
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
