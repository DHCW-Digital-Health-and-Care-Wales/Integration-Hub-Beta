#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Run ruff, mypy, unit tests and security checks for every component and write one HTML report.

Mirrors the commands in dev_tools/scripts/run-all-{ruff,mypy,tests,security}.sh but asks each tool for
machine-readable output, then renders a self-contained HTML file (no CDN assets) plus a JSON sidecar.
Tests run with pytest where the component's check.sh does (as CI's usePytest does), otherwise unittest.
Standard library only, so it runs anywhere `uv` does.

Usage:
    dev_tools/scripts/quality_report.py                      # all checks, all components
    dev_tools/scripts/quality_report.py --checks ruff,security dashboard senders/hl7_sender
    dev_tools/scripts/quality_report.py --output /tmp/report.html
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import subprocess  # nosec B404
import sys
import tempfile
import time
import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

LOG = logging.getLogger("quality_report")

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT_DIR / "dev_tools" / "reports" / "quality-report.html"

CHECKS: Tuple[str, ...] = ("ruff", "mypy", "tests", "bandit", "audit")
CHECK_GROUPS: Dict[str, Tuple[str, ...]] = {
    "ruff": ("ruff",),
    "mypy": ("mypy",),
    "tests": ("tests",),
    "security": ("bandit", "audit"),
}
CHECK_LABELS: Dict[str, str] = {
    "ruff": "Ruff",
    "mypy": "Mypy",
    "tests": "Tests",
    "bandit": "Bandit",
    "audit": "Dependencies",
}
TAB_OF_CHECK: Dict[str, str] = {
    "ruff": "ruff", "mypy": "mypy", "tests": "tests", "bandit": "security", "audit": "security",
}
TAB_LABELS: Dict[str, str] = {"ruff": "Ruff", "mypy": "Mypy", "tests": "Tests", "security": "Security"}

# Known no-fix advisory for a transitive Pygments dependency; keep in sync with run-all-security.sh.
AUDIT_IGNORES: Tuple[str, ...] = ("GHSA-5239-wwwm-4pmq",)

# Codes documented on mypy's "optional checks" page rather than the default error-code page.
MYPY_OPTIONAL_CODES = frozenset({
    "type-arg", "no-untyped-def", "redundant-cast", "redundant-self", "comparison-overlap", "no-untyped-call",
    "no-any-return", "no-any-unimported", "unreachable", "deprecated", "redundant-expr", "possibly-undefined",
    "truthy-bool", "truthy-iterable", "ignore-without-code", "unused-awaitable", "unused-ignore",
    "explicit-override", "mutable-override", "unimported-reveal", "explicit-any", "exhaustive-match",
    "untyped-decorator",
})

STATUS_ORDER = {"error": 0, "fail": 1, "pass": 2, "skipped": 3}


@dataclass
class Finding:
    location: str
    code: str
    message: str
    severity: str
    url: str = ""
    detail: str = ""
    links: List[Tuple[str, str]] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)


@dataclass
class CheckResult:
    check: str
    component: str
    status: str  # pass | fail | error | skipped
    findings: List[Finding] = field(default_factory=list)
    summary: Dict[str, float] = field(default_factory=dict)
    output: str = ""
    duration: float = 0.0
    runner: str = ""


# --------------------------------------------------------------------------------------------------
# Helpers
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


def discover_components(root: Path) -> List[str]:
    """Same discovery rule as the run-all-*.sh scripts: any pyproject.toml up to two directories deep."""
    found = set()
    for pattern in ("*/pyproject.toml", "*/*/pyproject.toml"):
        for pyproject in root.glob(pattern):
            rel = pyproject.parent.relative_to(root)
            if not {".venv", "node_modules"} & set(rel.parts):
                found.add(rel.as_posix())
    return sorted(found)


# --------------------------------------------------------------------------------------------------
# Parsers (pure functions over tool output)
# --------------------------------------------------------------------------------------------------

def parse_ruff(stdout: str, cwd: Path, root: Path) -> List[Finding]:
    findings = []
    for item in json.loads(stdout or "[]"):
        location = item.get("location") or {}
        fix = item.get("fix") or {}
        findings.append(Finding(
            location=f"{relative_path(item['filename'], cwd, root)}:{location.get('row', 0)}:"
                     f"{location.get('column', 0)}",
            code=item.get("code") or "syntax-error",
            message=item.get("message", ""),
            severity="error",
            url=safe_url(item.get("url") or ""),
            meta={"rule": item.get("name") or "", "fix": fix.get("applicability", "") if fix else ""},
        ))
    return findings


def parse_mypy(stdout: str, cwd: Path, root: Path) -> List[Finding]:
    """Parse `mypy -O json` (one object per line); notes are folded into the preceding error."""
    findings: List[Finding] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        item = json.loads(line)
        message = item.get("message", "")
        severity = item.get("severity") or "error"
        if severity == "note" and findings:
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


def _unittest_failure_blocks(output: str) -> List[Tuple[str, str, str, str]]:
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


def _last_project_frame(traceback: str, root: Path) -> str:
    root_str = str(root.resolve())
    location = ""
    for path, line in _FRAME_RE.findall(traceback):
        if path.startswith(root_str) and "/.venv/" not in path:
            location = f"{relative_path(path, root, root)}:{line}"
    return location


def parse_unittest(output: str, root: Path) -> Tuple[Optional[Dict[str, float]], List[Finding]]:
    """Parse `python -m unittest -v` output. Returns (None, []) if no run summary was printed."""
    ran_matches = list(_RAN_RE.finditer(output))
    if not ran_matches:
        return None, []
    ran = ran_matches[-1]
    summary: Dict[str, float] = {
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


def parse_junit(xml_text: str, cwd: Path, root: Path) -> Tuple[Dict[str, float], List[Finding]]:
    """Parse a pytest `--junitxml` report (root is <testsuites> or a single <testsuite>)."""
    # The XML is written by pytest on this machine during the run, not taken from an untrusted source.
    document = ET.fromstring(xml_text)  # nosec B314
    suites = list(document.iter("testsuite"))
    summary: Dict[str, float] = {
        "ran": sum(int(s.get("tests", 0)) for s in suites),
        "failures": sum(int(s.get("failures", 0)) for s in suites),
        "errors": sum(int(s.get("errors", 0)) for s in suites),
        "skipped": sum(int(s.get("skipped", 0)) for s in suites),
        "duration": sum(float(s.get("time", 0)) for s in suites),
    }
    summary["passed"] = max(0, summary["ran"] - summary["failures"] - summary["errors"] - summary["skipped"])

    findings = []
    for case in document.iter("testcase"):
        for outcome in case:
            if outcome.tag not in ("failure", "error"):
                continue
            traceback = (outcome.text or "").strip()
            frames = _PYTEST_FRAME_RE.findall(traceback)
            location = _last_project_frame(traceback, root)
            if not location and frames:
                path, line = frames[-1]
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


def parse_bandit(stdout: str, cwd: Path, root: Path) -> List[Finding]:
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
            meta={"confidence": (item.get("issue_confidence") or "").upper(), "test": item.get("test_name") or ""},
        ))
    for error in data.get("errors", []):
        findings.append(Finding(
            location=relative_path(error.get("filename", ""), cwd, root),
            code="scan-error",
            message=error.get("reason", ""),
            severity="ERROR",
        ))
    return findings


def parse_uv_audit(stdout: str) -> Tuple[Dict[str, float], List[Finding]]:
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
# Runners
# --------------------------------------------------------------------------------------------------

def _tool_env() -> Dict[str, str]:
    # Drop VIRTUAL_ENV (this script's own env) so `uv run` uses each component's .venv without warnings.
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    env["NO_COLOR"] = "1"
    return env


def run_command(cmd: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    # Fixed argv built in this module; never a shell.
    return subprocess.run(  # nosec B603
        list(cmd), cwd=cwd, capture_output=True, text=True, env=_tool_env(), check=False,
    )


def _result(check: str, component: str, returncode: int, findings: List[Finding], started: float,
            raw_output: str, summary: Optional[Dict[str, float]] = None) -> CheckResult:
    if returncode == 0:
        status = "pass"
    else:
        status = "fail" if findings else "error"
    return CheckResult(
        check=check, component=component, status=status, findings=findings, summary=summary or {},
        output=tail(raw_output) if status == "error" else "", duration=time.monotonic() - started,
    )


def _package_dir(cwd: Path) -> Optional[str]:
    return cwd.name if (cwd / cwd.name).is_dir() else None


def run_ruff(component: str, root: Path) -> CheckResult:
    cwd, started = root / component, time.monotonic()
    proc = run_command(["uv", "run", "ruff", "check", ".", "--output-format", "json"], cwd)
    try:
        findings = parse_ruff(proc.stdout, cwd, root)
    except (ValueError, KeyError):
        findings = []
    return _result("ruff", component, proc.returncode, findings, started, proc.stdout + proc.stderr)


def run_mypy(component: str, root: Path) -> CheckResult:
    cwd, started = root / component, time.monotonic()
    targets = [_package_dir(cwd) or "."] + (["tests"] if (cwd / "tests").is_dir() else [])
    # Same pinning as run-all-mypy.sh: Python 3.13 target, OS trust store for corporate TLS proxies.
    proc = run_command(["uv", "tool", "run", "--native-tls", "--python", "3.13", "mypy", *targets,
                        "--ignore-missing-imports", "-O", "json"], cwd)
    try:
        findings = parse_mypy(proc.stdout, cwd, root)
    except ValueError:
        findings = []
    return _result("mypy", component, proc.returncode, findings, started, proc.stdout + proc.stderr)


def run_tests(component: str, root: Path) -> CheckResult:
    cwd, started = root / component, time.monotonic()
    if not (cwd / "tests").is_dir():
        return CheckResult("tests", component, "skipped", output="No tests/ directory")
    # --reinstall bypasses uv's cache, which can serve stale wheels for changed shared_libs path deps.
    sync = run_command(["uv", "sync", "--locked", "--all-groups", "--reinstall"], cwd)
    if sync.returncode != 0:
        return CheckResult("tests", component, "error", output=tail(sync.stdout + sync.stderr),
                           duration=time.monotonic() - started)
    runner = "pytest" if uses_pytest(cwd) else "unittest"
    summary: Optional[Dict[str, float]]
    if runner == "pytest":
        with tempfile.TemporaryDirectory() as tmp:
            junit = Path(tmp) / "junit.xml"
            proc = run_command(["uv", "run", "pytest", "tests", "-q", "-p", "no:cacheprovider",
                                f"--junitxml={junit}"], cwd)
            try:
                summary, findings = parse_junit(junit.read_text(encoding="utf-8"), cwd, root)
            except (OSError, ET.ParseError):
                summary, findings = None, []
    else:
        proc = run_command(["uv", "run", "python", "-m", "unittest", "discover", "tests", "-v"], cwd)
        summary, findings = parse_unittest(proc.stdout + proc.stderr, root)
    output = proc.stdout + proc.stderr
    if summary is None:
        return CheckResult("tests", component, "error", output=tail(output), duration=time.monotonic() - started,
                           runner=runner)
    result = _result("tests", component, proc.returncode, findings, started, output, summary)
    result.runner = runner
    if result.status == "error":
        result.status = "fail"
    return result


def run_bandit(component: str, root: Path) -> CheckResult:
    cwd, started = root / component, time.monotonic()
    package = _package_dir(cwd)
    if package:
        targets = [package] + (["tests"] if (cwd / "tests").is_dir() else [])
    else:
        targets = [".", "-x", "./.venv"]
    proc = run_command(["uv", "tool", "run", "bandit", "-r", *targets, "--severity-level", "medium",
                        "-f", "json", "-q"], cwd)
    try:
        findings = parse_bandit(proc.stdout, cwd, root)
    except ValueError:
        findings = []
    return _result("bandit", component, proc.returncode, findings, started, proc.stdout + proc.stderr)


def run_audit(component: str, root: Path) -> CheckResult:
    cwd, started = root / component, time.monotonic()
    ignores = [arg for advisory in AUDIT_IGNORES for arg in ("--ignore", advisory)]
    proc = run_command(["uv", "audit", "--locked", "--output-format", "json", *ignores], cwd)
    try:
        summary, findings = parse_uv_audit(proc.stdout)
    except ValueError:
        summary, findings = {}, []
    return _result("audit", component, proc.returncode, findings, started, proc.stdout + proc.stderr, summary)


def uv_audit_available(root: Path) -> bool:
    return run_command(["uv", "audit", "--help"], root).returncode == 0


# --------------------------------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------------------------------

def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def anchor_id(check: str, component: str) -> str:
    return f"{check}--{_slug(component)}"


def _status_chip(status: str, text: Optional[str] = None) -> str:
    return f'<span class="chip chip--{_e(status)}">{_e(text or status.upper())}</span>'


def _severity_chip(severity: str) -> str:
    return f'<span class="sev sev--{_slug(severity)}">{_e(severity)}</span>'


def _link(url: str, text: str) -> str:
    url = safe_url(url)
    if not url:
        return _e(text)
    return f'<a href="{_e(url)}" target="_blank" rel="noopener noreferrer">{_e(text)}</a>'


def _message_cell(finding: Finding) -> str:
    if not finding.detail:
        return _e(finding.message)
    return (f'<details class="detail"><summary>{_e(finding.message)}</summary>'
            f'<pre>{_e(finding.detail)}</pre></details>')


def _links_cell(finding: Finding) -> str:
    return " ".join(f'<span class="ext">{_link(url, label)}</span>' for label, url in finding.links)


Column = Tuple[str, Callable[[Finding], str]]

COLUMNS: Dict[str, List[Column]] = {
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


def _findings_table(check: str, findings: List[Finding]) -> str:
    columns = COLUMNS[check]
    head = "".join(f"<th>{_e(name)}</th>" for name, _ in columns)
    rows = []
    for finding in findings:
        cells = "".join(f'<td class="msg">{render(finding)}</td>' if render is _message_cell
                        else f"<td>{render(finding)}</td>" for _, render in columns)
        rows.append(f'<tr data-sev="{_e(finding.severity)}" data-text="{_e(_search_text(finding))}">{cells}</tr>')
    return f'<div class="table-wrap"><table class="findings"><thead><tr>{head}</tr></thead>' \
           f'<tbody>{"".join(rows)}</tbody></table></div>'


def _tests_bar(summary: Dict[str, float], runner: str) -> str:
    ran = summary.get("ran", 0) or 0
    if not ran:
        return ""
    segments = [("passed", summary.get("passed", 0)), ("failed", summary.get("failures", 0)),
                ("errored", summary.get("errors", 0)), ("skipped", summary.get("skipped", 0))]
    bar = "".join(f'<span class="bar__{name}" style="width:{100 * count / ran:.2f}%"></span>'
                  for name, count in segments if count)
    legend = " &middot; ".join(f"{int(count)} {name}" for name, count in segments if count)
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


def _component_card(result: CheckResult) -> str:
    if result.status == "error":
        body = ('<p class="tool-error">The tool did not complete. Last output:</p>'
                f'<pre class="raw">{_e(result.output)}</pre>')
    elif result.status == "skipped":
        body = f'<p class="muted">Skipped{": " + _e(result.output) if result.output else ""}.</p>'
    elif result.findings:
        body = _findings_table(result.check, result.findings)
    else:
        body = '<p class="ok-text">No issues found.</p>'
    if result.check == "tests":
        body = _tests_bar(result.summary, result.runner) + body
    open_attr = " open" if result.status in ("fail", "error") else ""
    return (
        f'<details class="comp" id="{anchor_id(result.check, result.component)}" data-status="{_e(result.status)}" '
        f'data-name="{_e(result.component.lower())}"{open_attr}>'
        f'<summary>{_status_chip(result.status)}<span class="comp__name">{_e(result.component)}</span>'
        f'<span class="comp__meta">{_e(_issue_label(result))} &middot; {result.duration:.1f}s</span></summary>'
        f'<div class="comp__body">{body}</div></details>'
    )


def _toolbar(results: List[CheckResult]) -> str:
    severities = sorted({f.severity for r in results for f in r.findings})
    options = "".join(f'<option value="{_e(s)}">{_e(s)}</option>' for s in severities)
    severity_select = (f'<select data-severity aria-label="Severity"><option value="">All severities</option>'
                       f'{options}</select>') if len(severities) > 1 else ""
    return (
        '<div class="toolbar">'
        '<input type="search" data-filter placeholder="Filter by component, file, code or message\u2026" '
        'aria-label="Filter">'
        f'{severity_select}'
        '<label class="toggle"><input type="checkbox" data-failing-only> Problems only</label>'
        '<button type="button" class="btn" data-expand="open">Expand all</button>'
        '<button type="button" class="btn" data-expand="close">Collapse all</button>'
        '</div>'
    )


def _sorted_results(results: Iterable[CheckResult]) -> List[CheckResult]:
    return sorted(results, key=lambda r: (STATUS_ORDER.get(r.status, 9), r.component))


def _check_section(check: str, results: List[CheckResult], heading: bool) -> str:
    cards = "".join(_component_card(r) for r in _sorted_results(results))
    title = f'<h2 class="section-title">{_e(CHECK_LABELS[check])}</h2>' if heading else ""
    return f'<section class="check-section">{title}{cards}</section>'


def _tab_status(results: List[CheckResult]) -> str:
    statuses = {r.status for r in results}
    for status in ("error", "fail"):
        if status in statuses:
            return status
    return "pass" if "pass" in statuses else "skipped"


def _kpi_card(check: str, results: List[CheckResult]) -> str:
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
    return (
        f'<a class="kpi kpi--{_e(status)}" href="#{TAB_OF_CHECK[check]}">'
        f'<div class="kpi__label">{_e(CHECK_LABELS[check])}</div>'
        f'<div class="kpi__value">{value}</div><div class="kpi__caption">{caption}</div>'
        f'<div class="kpi__foot">{passing}/{len(ran)} components clean{error_note}</div></a>'
    )


def _matrix(components: List[str], checks: List[str], by_key: Dict[Tuple[str, str], CheckResult]) -> str:
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


def render_html(results: List[CheckResult], meta: Dict[str, str]) -> str:
    checks = [c for c in CHECKS if any(r.check == c for r in results)]
    components = sorted({r.component for r in results})
    by_key = {(r.check, r.component): r for r in results}
    tabs = [t for t in TAB_LABELS if any(TAB_OF_CHECK[c] == t for c in checks)]
    overall = "pass" if all(r.status in ("pass", "skipped") for r in results) else "fail"

    tab_buttons = ['<button role="tab" data-tab="overview" aria-selected="true">Overview</button>']
    panels = [
        '<section class="tab-panel" id="tab-overview" role="tabpanel">'
        f'<div class="kpis">{"".join(_kpi_card(c, [r for r in results if r.check == c]) for c in checks)}</div>'
        '<h2 class="section-title">Components</h2>'
        f'{_matrix(components, checks, by_key)}</section>'
    ]
    for tab in tabs:
        tab_checks = [c for c in checks if TAB_OF_CHECK[c] == tab]
        tab_results = [r for r in results if r.check in tab_checks]
        issues = sum(len(r.findings) for r in tab_results)
        status = _tab_status(tab_results)
        tab_buttons.append(f'<button role="tab" data-tab="{tab}" aria-selected="false">{_e(TAB_LABELS[tab])}'
                           f'<span class="count count--{_e(status)}">{issues}</span></button>')
        sections = "".join(_check_section(c, [r for r in tab_results if r.check == c], len(tab_checks) > 1)
                           for c in tab_checks)
        panels.append(f'<section class="tab-panel" id="tab-{tab}" role="tabpanel" hidden>'
                      f'{_toolbar(tab_results)}{sections}</section>')

    return (
        '<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Integration Hub quality report &ndash; {_e(meta["generated"])}</title>'
        f'<style>{CSS}</style></head><body>'
        '<header class="top"><div class="top__inner">'
        '<div><div class="brand">DHCW &middot; Integration Hub</div><h1>Quality report</h1></div>'
        f'<div class="top__meta">{_status_chip(overall, "ALL PASSED" if overall == "pass" else "ISSUES FOUND")}'
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
.top__meta code{background:rgba(255,255,255,.14);padding:1px 6px;border-radius:4px;color:#fff}
.tabs{max-width:1400px;margin:0 auto;padding:0 16px;display:flex;gap:4px;overflow-x:auto}
.tabs button{background:none;border:0;color:rgba(255,255,255,.75);font:inherit;font-weight:500;padding:10px 16px;
cursor:pointer;border-bottom:3px solid transparent;display:flex;gap:8px;align-items:center;white-space:nowrap}
.tabs button:hover{color:#fff}
.tabs button[aria-selected=true]{color:#fff;border-bottom-color:var(--dhcw-blue)}
.count{background:rgba(255,255,255,.18);border-radius:999px;padding:0 8px;font-size:12px}
.count--fail{background:var(--fail)}.count--error{background:var(--yellow);color:var(--navy)}
main{max-width:1400px;margin:0 auto;padding:24px}
.section-title{font-size:16px;color:var(--navy);margin:28px 0 12px;font-weight:600}
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
.table-wrap{overflow-x:auto;background:var(--card);border-radius:10px;box-shadow:0 1px 3px rgba(27,41,74,.08)}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}
thead th{background:#f7f9fc;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em;
font-weight:600;position:sticky;top:0}
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
.bar__skipped{background:var(--skip)}
[hidden]{display:none!important}
@media print{.top{position:static}.toolbar,.tabs{display:none}.tab-panel{display:block!important}}
"""

JS = """
(() => {
  const tabs = [...document.querySelectorAll('[role=tab]')];
  const panels = [...document.querySelectorAll('.tab-panel')];
  const activate = (name) => {
    tabs.forEach(t => t.setAttribute('aria-selected', String(t.dataset.tab === name)));
    panels.forEach(p => { p.hidden = p.id !== 'tab-' + name; });
  };
  tabs.forEach(t => t.addEventListener('click', () => { history.replaceState(null, '', '#' + t.dataset.tab);
    activate(t.dataset.tab); }));
  const fromHash = () => {
    const target = decodeURIComponent(location.hash.slice(1));
    const el = target && document.getElementById(target);
    if (el && el.classList.contains('comp')) {
      activate(el.closest('.tab-panel').id.slice(4));
      el.hidden = false; el.open = true; el.scrollIntoView({block: 'start'});
    } else if (target && document.getElementById('tab-' + target)) {
      activate(target);
    } else {
      activate('overview');
    }
  };
  window.addEventListener('hashchange', fromHash);
  fromHash();

  const applyFilters = (panel) => {
    const q = (panel.querySelector('[data-filter]')?.value || '').trim().toLowerCase();
    const sev = panel.querySelector('[data-severity]')?.value || '';
    const problemsOnly = panel.querySelector('[data-failing-only]')?.checked;
    panel.querySelectorAll('.comp').forEach(comp => {
      const nameMatch = !q || comp.dataset.name.includes(q);
      const rows = [...comp.querySelectorAll('tr[data-text]')];
      let visible = 0;
      rows.forEach(tr => {
        const show = (nameMatch || tr.dataset.text.includes(q)) && (!sev || tr.dataset.sev === sev);
        tr.hidden = !show;
        if (show) visible++;
      });
      const clean = comp.dataset.status === 'pass' || comp.dataset.status === 'skipped';
      const matches = rows.length ? (visible > 0 || (!q && !sev)) : (nameMatch && !sev);
      comp.hidden = (problemsOnly && clean) || !matches;
    });
  };
  panels.forEach(panel => {
    panel.querySelectorAll('[data-filter],[data-severity],[data-failing-only]')
      .forEach(ctrl => ctrl.addEventListener('input', () => applyFilters(panel)));
    panel.querySelectorAll('[data-expand]').forEach(btn => btn.addEventListener('click', () => {
      panel.querySelectorAll('.comp').forEach(c => { c.open = btn.dataset.expand === 'open'; });
    }));
  });
})();
"""


# --------------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------------

def _git(args: List[str], root: Path) -> str:
    proc = run_command(["git", *args], root)
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run quality checks for every component and write an HTML report.")
    parser.add_argument("components", nargs="*",
                        help="Component directories relative to the repo root (default: all discovered)")
    parser.add_argument("--checks", default=",".join(CHECK_GROUPS),
                        help=f"Comma-separated subset of: {', '.join(CHECK_GROUPS)} (default: all)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="HTML report path; a .json sidecar is written next to it")
    return parser.parse_args(argv)


def resolve_checks(value: str) -> List[str]:
    requested = [c.strip().lower() for c in value.split(",") if c.strip()]
    unknown = [c for c in requested if c not in CHECK_GROUPS]
    if unknown or not requested:
        raise ValueError(f"Unknown checks {unknown or value!r}; choose from {', '.join(CHECK_GROUPS)}")
    selected = {check for group in requested for check in CHECK_GROUPS[group]}
    return [c for c in CHECKS if c in selected]


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    try:
        checks = resolve_checks(args.checks)
    except ValueError as exc:
        LOG.error("%s", exc)
        return 2

    components = discover_components(ROOT_DIR)
    if args.components:
        wanted = [c.strip("/") for c in args.components]
        missing = [c for c in wanted if c not in components]
        if missing:
            LOG.error("Unknown components: %s", ", ".join(missing))
            return 2
        components = wanted

    runners: Dict[str, Callable[[str, Path], CheckResult]] = {
        "ruff": run_ruff, "mypy": run_mypy, "tests": run_tests, "bandit": run_bandit, "audit": run_audit,
    }
    if "audit" in checks and not uv_audit_available(ROOT_DIR):
        LOG.warning("This uv install has no 'audit' subcommand; dependency scanning will be skipped")
        runners["audit"] = lambda component, _root: CheckResult(
            "audit", component, "skipped", output="uv audit is not available in this uv install")

    started = time.monotonic()
    results: List[CheckResult] = []
    for index, component in enumerate(components, start=1):
        for check in checks:
            result = runners[check](component, ROOT_DIR)
            results.append(result)
            LOG.info("[%d/%d] %-45s %-7s %-8s %s", index, len(components), component, check,
                     result.status.upper(), _issue_label(result))

    elapsed = time.monotonic() - started
    meta = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], ROOT_DIR),
        "commit": _git(["rev-parse", "--short", "HEAD"], ROOT_DIR),
        "components": str(len(components)),
        "duration": f"{int(elapsed // 60)}m {int(elapsed % 60)}s",
    }
    output: Path = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(results, meta), encoding="utf-8")
    output.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "results": [asdict(r) for r in results]}, indent=2), encoding="utf-8")

    failed = sorted({r.component for r in results if r.status in ("fail", "error")})
    LOG.info("")
    LOG.info("Report: %s", output)
    LOG.info("ALL PASSED" if not failed else f"FAILED: {' '.join(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
