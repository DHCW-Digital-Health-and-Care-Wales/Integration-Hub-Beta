import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quality_fix as qf
import quality_report as qr

ROOT = Path("/repo")
COMPONENT_DIR = ROOT / "dashboard"


class TestHelpers(unittest.TestCase):
    def test_safe_url_allows_only_http_schemes(self) -> None:
        self.assertEqual(qr.safe_url("https://example.org/x"), "https://example.org/x")
        self.assertEqual(qr.safe_url("javascript:alert(1)"), "")
        self.assertEqual(qr.safe_url(""), "")

    def test_advisory_url_routes_by_prefix(self) -> None:
        self.assertEqual(qr.advisory_url("GHSA-aaaa-bbbb-cccc"), "https://github.com/advisories/GHSA-aaaa-bbbb-cccc")
        self.assertEqual(qr.advisory_url("CVE-2024-1"), "https://nvd.nist.gov/vuln/detail/CVE-2024-1")
        self.assertEqual(qr.advisory_url("PYSEC-2024-60"), "https://osv.dev/vulnerability/PYSEC-2024-60")
        # Anything that could break out of the URL path is rejected.
        self.assertEqual(qr.advisory_url("../x?y"), "")

    def test_mypy_doc_url_uses_optional_page_for_optional_codes(self) -> None:
        self.assertTrue(qr.mypy_doc_url("attr-defined").endswith("error_code_list.html#code-attr-defined"))
        self.assertTrue(qr.mypy_doc_url("unused-ignore").endswith("error_code_list2.html#code-unused-ignore"))
        self.assertEqual(qr.mypy_doc_url(""), "")

    def test_resolve_checks_supports_groups_and_individual_checks(self) -> None:
        self.assertEqual(qr.resolve_checks("security,ruff"), ["ruff", "bandit", "audit"])
        self.assertEqual(qr.resolve_checks("bandit"), ["bandit"])
        self.assertEqual(qr.resolve_checks("audit,mypy"), ["mypy", "audit"])
        with self.assertRaises(ValueError):
            qr.resolve_checks("lint")
        with self.assertRaises(ValueError):
            qr.resolve_checks("")

    def test_discover_components_skips_virtualenvs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("dashboard", "senders/hl7_sender", "dashboard/.venv", "a/b/c"):
                (root / rel).mkdir(parents=True, exist_ok=True)
                (root / rel / "pyproject.toml").write_text("")
            # a/b/c is three levels deep, beyond the run-all-*.sh `find -maxdepth 3` rule.
            self.assertEqual(qr.discover_components(root), ["dashboard", "senders/hl7_sender"])

    def test_resolve_output_paths_guards_against_json_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            html_p, json_p = qr._resolve_output_paths(base / "report")
            self.assertEqual(html_p.name, "report.html")
            self.assertEqual(json_p.name, "report.json")
            with self.assertRaises(ValueError):
                qr._resolve_output_paths(base / "report.json")

    def test_local_path_packages_includes_transitive_shared_libs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "shared_libs/base_lib").mkdir(parents=True)
            (root / "shared_libs/base_lib/pyproject.toml").write_text('[project]\nname = "base-lib"\n')
            (root / "shared_libs/mid_lib").mkdir(parents=True)
            (root / "shared_libs/mid_lib/pyproject.toml").write_text(
                '[project]\nname = "mid-lib"\n[tool.uv.sources]\nbase-lib = { path = "../base_lib" }\n'
            )
            (root / "svc").mkdir(parents=True)
            (root / "svc/pyproject.toml").write_text(
                '[project]\nname = "svc"\n[tool.uv.sources]\nmid-lib = { path = "../shared_libs/mid_lib" }\n'
            )
            comps = qr.discover_components(root)
            graph = qr.build_source_graph(root, comps)
            self.assertEqual(qr.local_path_packages("svc", root, graph), ["base-lib", "mid-lib"])
            self.assertEqual(qr.local_path_packages("shared_libs/base_lib", root, graph), [])

    def test_changed_components_expands_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, toml in (
                ("shared_libs/lib", '[project]\nname = "lib"\n'),
                ("svc", '[project]\nname = "svc"\n[tool.uv.sources]\nlib = { path = "../shared_libs/lib" }\n'),
                ("other", '[project]\nname = "other"\n'),
            ):
                (root / rel).mkdir(parents=True)
                (root / rel / "pyproject.toml").write_text(toml)
            comps = qr.discover_components(root)
            diff_proc = subprocess.CompletedProcess(["git"], 0, stdout="shared_libs/lib/mod.py\n", stderr="")
            untracked_proc = subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")
            with mock.patch.object(qr, "run_command", side_effect=[diff_proc, untracked_proc]):
                self.assertEqual(qr.changed_components(root, comps, ref="origin/main"), ["shared_libs/lib", "svc"])


class TestParseRuff(unittest.TestCase):
    def test_parses_findings_relative_to_repo_root(self) -> None:
        stdout = json.dumps([{
            "code": "F401", "filename": "/repo/dashboard/dashboard/app.py", "location": {"row": 3, "column": 1},
            "message": "`os` imported but unused", "name": "unused-import",
            "url": "https://docs.astral.sh/ruff/rules/unused-import", "fix": {"applicability": "safe"},
        }])
        [finding] = qr.parse_ruff(stdout, COMPONENT_DIR, ROOT)
        self.assertEqual(finding.location, "dashboard/dashboard/app.py:3:1")
        self.assertEqual(finding.code, "F401")
        self.assertEqual(finding.meta["fix"], "safe")
        self.assertTrue(finding.url.startswith("https://docs.astral.sh/"))

    def test_syntax_errors_and_missing_filename_are_handled(self) -> None:
        stdout = json.dumps([
            {"code": None, "filename": "x.py", "location": {"row": 1, "column": 1},
             "message": "SyntaxError", "fix": None, "url": None},
            {"code": "E999", "location": {"row": 2, "column": 3}, "message": "No file"},
        ])
        first, second = qr.parse_ruff(stdout, COMPONENT_DIR, ROOT)
        self.assertEqual(first.code, "syntax-error")
        self.assertEqual(first.location, "dashboard/x.py:1:1")
        self.assertEqual(second.location, ":2:3")

    def test_empty_output_means_no_findings(self) -> None:
        self.assertEqual(qr.parse_ruff("", COMPONENT_DIR, ROOT), [])


class TestParseMypy(unittest.TestCase):
    def test_notes_are_folded_and_leading_notes_or_bad_lines_skipped(self) -> None:
        lines = [
            json.dumps({"file": "dashboard/app.py", "line": 1, "column": 1, "message": "Leading note",
                        "hint": None, "code": None, "severity": "note"}),
            "{not actually json",
            json.dumps({"file": "dashboard/app.py", "line": 6, "column": 11, "message": "Incompatible return value",
                        "hint": None, "code": "return-value", "severity": "error"}),
            json.dumps({"file": "dashboard/app.py", "line": 6, "column": 11, "message": "See docs", "hint": None,
                        "code": None, "severity": "note"}),
            "not json",
        ]
        [finding] = qr.parse_mypy("\n".join(lines), COMPONENT_DIR, ROOT)
        self.assertEqual(finding.location, "dashboard/dashboard/app.py:6:11")
        self.assertEqual(finding.detail, "See docs")
        self.assertIn("#code-return-value", finding.url)


UNITTEST_FAILED = """\
test_ok (tests.test_app.TestApp.test_ok) ... ok
test_bad (tests.test_app.TestApp.test_bad) ... FAIL
test_boom (tests.test_app.TestApp.test_boom)
Explodes loudly. ... ERROR
test_skip (tests.test_app.TestApp.test_skip) ... skipped 'later'

======================================================================
ERROR: test_boom (tests.test_app.TestApp.test_boom)
Explodes loudly.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/repo/dashboard/tests/test_app.py", line 20, in test_boom
    raise RuntimeError("boom")
RuntimeError: boom

======================================================================
FAIL: test_bad (tests.test_app.TestApp.test_bad)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/usr/lib/python3.13/unittest/case.py", line 58, in testPartExecutor
  File "/repo-other/sibling/x.py", line 9, in helper
  File "/repo/dashboard/tests/test_app.py", line 12, in test_bad
    self.assertEqual(1, 2)
AssertionError: 1 != 2

----------------------------------------------------------------------
Ran 4 tests in 0.012s

FAILED (failures=1, errors=1, skipped=1)
"""


class TestParseUnittest(unittest.TestCase):
    def test_parses_summary_and_failure_blocks(self) -> None:
        summary, findings = qr.parse_unittest(UNITTEST_FAILED, ROOT)
        assert summary is not None
        self.assertEqual(summary["ran"], 4)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual([f.severity for f in findings], ["ERROR", "FAIL"])
        error, failure = findings
        self.assertEqual(error.code, "test_boom (tests.test_app.TestApp.test_boom)")
        self.assertEqual(error.message, "RuntimeError: boom")
        self.assertTrue(error.detail.startswith("Explodes loudly."))
        self.assertEqual(failure.message, "AssertionError: 1 != 2")
        # The stdlib and sibling-repo frames are ignored; the last frame inside the repo is reported.
        self.assertEqual(failure.location, "dashboard/tests/test_app.py:12")

    def test_sibling_prefix_path_is_not_treated_as_project_frame(self) -> None:
        tb = '  File "/repo-other/tests/test_x.py", line 10, in f\n'
        self.assertEqual(qr._last_project_frame(tb, ROOT), "")

    def test_ok_run_has_no_findings(self) -> None:
        summary, findings = qr.parse_unittest("test_a (t.T.test_a) ... ok\n\n" + "-" * 70 +
                                              "\nRan 1 test in 0.001s\n\nOK\n", ROOT)
        assert summary is not None
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(findings, [])

    def test_no_tests_ran_is_reported(self) -> None:
        summary, findings = qr.parse_unittest("\nRan 0 tests in 0.000s\n\nNO TESTS RAN\n", ROOT)
        assert summary is not None
        self.assertEqual(summary["ran"], 0)
        self.assertEqual([f.code for f in findings], ["no-tests"])

    def test_missing_summary_returns_none(self) -> None:
        # e.g. an import crash before unittest printed anything.
        self.assertEqual(qr.parse_unittest("Traceback...\nModuleNotFoundError", ROOT), (None, []))


JUNIT_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="1" failures="1" skipped="1" tests="4" time="0.50">
<testcase classname="tests.test_app.TestApp" name="test_ok" time="0.01"/>
<testcase classname="tests.test_app.TestApp" name="test_bad" time="0.01">
<failure message="assert 1 == 2&#10;  +1&#10;  -2">def test_bad():
&gt;       assert 1 == 2
E       assert 1 == 2

tests/test_app.py:12: AssertionError
.venv/lib/python3.13/site-packages/pluggy/_callers.py:99: in _multicall</failure></testcase>
<testcase classname="tests.test_broken" name="tests.test_broken" time="0.00">
<error message="collection failure">ImportError while importing test module</error></testcase>
<testcase classname="tests.test_app.TestApp" name="test_skip" time="0.00"><skipped message="later"/></testcase>
</testsuite></testsuites>
"""


class TestParseJunit(unittest.TestCase):
    def test_parses_counts_failures_and_ignores_venv_frames(self) -> None:
        summary, findings = qr.parse_junit(JUNIT_XML, COMPONENT_DIR, ROOT)
        self.assertEqual(summary["ran"], 4)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["skipped"], 1)
        failure, error = findings
        self.assertEqual(failure.severity, "FAIL")
        self.assertEqual(failure.code, "tests.test_app.TestApp::test_bad")
        self.assertEqual(failure.message, "assert 1 == 2")
        # pytest frames inside .venv are ignored; project frame is reported.
        self.assertEqual(failure.location, "dashboard/tests/test_app.py:12")
        self.assertEqual(error.severity, "ERROR")
        self.assertEqual(error.message, "collection failure")

    def test_single_testsuite_root_and_no_tests(self) -> None:
        xml = '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" time="0.01"></testsuite>'
        summary, findings = qr.parse_junit(xml, COMPONENT_DIR, ROOT)
        self.assertEqual(summary["ran"], 0)
        self.assertEqual([f.code for f in findings], ["no-tests"])


class TestUsesPytest(unittest.TestCase):
    def _check(self, content: str | None) -> bool:
        with tempfile.TemporaryDirectory() as tmp:
            if content is not None:
                (Path(tmp) / "check.sh").write_text(content)
            return qr.uses_pytest(Path(tmp))

    def test_follows_check_sh(self) -> None:
        self.assertTrue(self._check("#!/bin/bash\nset -e\nuv run ruff check\nuv run pytest\n"))
        self.assertFalse(self._check("uv run python -m unittest discover tests\n"))
        # A commented-out pytest line does not count, nor does a missing check.sh.
        self.assertFalse(self._check("# uv run pytest\nuv run python -m unittest discover tests\n"))
        self.assertFalse(self._check(None))


class TestParseBandit(unittest.TestCase):
    def test_parses_results_links_and_errors(self) -> None:
        stdout = json.dumps({
            "results": [{
                "code": "5 subprocess.call(cmd, shell=True)\n", "filename": "dashboard/app.py",
                "issue_confidence": "HIGH",
                "issue_cwe": {"id": 78, "link": "https://cwe.mitre.org/data/definitions/78.html"},
                "issue_severity": "HIGH", "issue_text": "shell=True", "line_number": 5, "col_offset": 4,
                "more_info": "https://bandit.readthedocs.io/en/latest/plugins/b602.html", "test_id": "B602",
                "test_name": "subprocess_popen_with_shell_equals_true",
            }],
            "errors": [{"filename": "dashboard/broken.py", "reason": "syntax error while parsing AST from file"}],
        })
        issue, error = qr.parse_bandit(stdout, COMPONENT_DIR, ROOT)
        self.assertEqual(issue.location, "dashboard/dashboard/app.py:5")
        self.assertEqual(issue.severity, "HIGH")
        self.assertEqual(issue.meta["col"], "4")
        self.assertEqual([label for label, _ in issue.links], ["Bandit docs", "CWE-78"])
        self.assertEqual(error.code, "scan-error")


class TestParseUvAudit(unittest.TestCase):
    def test_parses_vulnerabilities_and_fix_status(self) -> None:
        stdout = json.dumps({
            "summary": {"audited_packages": 7, "vulnerabilities": 2, "adverse_statuses": 0},
            "vulnerabilities": [
                {"dependency": {"name": "idna", "version": "2.7"}, "id": "GHSA-jjg7-2v4v-x38h",
                 "display_id": "GHSA-jjg7-2v4v-x38h", "aliases": ["CVE-2024-3651"], "summary": "DoS",
                 "description": "Long text", "link": "https://github.com/advisories/GHSA-jjg7-2v4v-x38h",
                 "fix_versions": ["3.7"], "published": "2024-04-26T00:00:00Z"},
                {"dependency": {"name": "pygments", "version": "2.19"}, "id": "PYSEC-1", "display_id": "PYSEC-1",
                 "aliases": [], "summary": "ReDoS", "link": None, "fix_versions": []},
            ],
            "adverse_statuses": [],
        })
        summary, findings = qr.parse_uv_audit(stdout)
        self.assertEqual(summary["audited_packages"], 7)
        fixable, unfixable = findings
        self.assertEqual(fixable.severity, "FIX AVAILABLE")
        self.assertEqual(fixable.meta["fixed_in"], "3.7")
        self.assertEqual(fixable.meta["published"], "2024-04-26")
        self.assertEqual([label for label, _ in fixable.links], ["GHSA-jjg7-2v4v-x38h", "CVE-2024-3651"])
        self.assertEqual(unfixable.severity, "NO FIX")
        self.assertEqual(unfixable.url, "https://osv.dev/vulnerability/PYSEC-1")


class TestCompareReports(unittest.TestCase):
    def test_scopes_diff_to_current_pairs_and_marks_new_findings(self) -> None:
        previous = {
            "meta": {"commit": "old123", "generated": "2026-10-01 10:00 UTC"},
            "results": [
                {"check": "ruff", "component": "dashboard", "status": "fail", "findings": [
                    {"location": "dashboard/a.py:1:1", "code": "F401", "message": "unused os", "severity": "error"},
                    {"location": "dashboard/a.py:2:1", "code": "F401", "message": "unused sys", "severity": "error"},
                ]},
                # Unrelated component not in current run must not inflate fixed_count.
                {"check": "ruff", "component": "other", "status": "fail", "findings": [
                    {"location": "other/x.py:1:1", "code": "E501", "message": "line too long", "severity": "error"},
                ]},
            ],
        }
        current = [
            qr.CheckResult("ruff", "dashboard", "fail", findings=[
                qr.Finding("dashboard/a.py:9:1", "F401", "unused os", "error"),  # moved line, same finding
                qr.Finding("dashboard/b.py:3:1", "E501", "line too long", "error"),  # new finding
            ]),
        ]
        delta = qr.compare_reports(previous, current)
        self.assertEqual(delta.baseline_commit, "old123")
        self.assertEqual(delta.new_count, 1)
        self.assertEqual(delta.fixed_count, 1)
        self.assertEqual(delta.new_by_check, {"ruff": 1})
        self.assertEqual(delta.fixed_by_check, {"ruff": 1})
        self.assertEqual(delta.new_finding_indices, {("ruff", "dashboard"): {1}})


class TestRunners(unittest.TestCase):
    def test_result_marks_zero_exit_with_findings_as_fail(self) -> None:
        finding = qr.Finding("tests/", "no-tests", "none", "ERROR")
        res = qr._result("tests", "dashboard", 0, [finding], 0.0, "")
        self.assertEqual(res.status, "fail")

    def test_safe_run_captures_timeout_with_bytes_output(self) -> None:
        def slow(_comp: str, _root: Path, _cfg: qr.RunConfig) -> qr.CheckResult:
            raise subprocess.TimeoutExpired(["pytest"], 10, output=b"running test_hang", stderr=b"stuck")

        res = qr._safe_run("tests", "dashboard", slow, ROOT, qr.RunConfig(timeout=10))
        self.assertEqual(res.status, "error")
        self.assertIn("Timed out after 10s", res.output)
        self.assertIn("running test_hang", res.output)

    def test_run_tests_keeps_error_status_when_nonzero_without_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "svc/tests").mkdir(parents=True)
            (root / "svc/pyproject.toml").write_text('[project]\nname = "svc"\n')
            sync_ok = subprocess.CompletedProcess(["uv"], 0, stdout="", stderr="")
            test_fail = subprocess.CompletedProcess(
                ["uv"], 1, stdout="Ran 1 test in 0.01s\n\nOK\n", stderr="fatal teardown crash\n"
            )
            with mock.patch.object(qr, "run_command", side_effect=[sync_ok, test_fail]):
                res = qr.run_tests("svc", root, qr.RunConfig(sync_mode="targeted", source_graph={"svc": []}))
            self.assertEqual(res.status, "error")
            self.assertIn("fatal teardown crash", res.output)

    def test_run_bandit_uses_pyproject_config_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "svc/svc").mkdir(parents=True)
            (root / "svc/pyproject.toml").write_text('[tool.bandit.assert_used]\nskips = ["*/test_*.py"]\n')
            ok = subprocess.CompletedProcess(["uv"], 0, stdout='{"results": [], "errors": []}', stderr="")
            with mock.patch.object(qr, "run_command", return_value=ok) as run_mock:
                qr.run_bandit("svc", root, qr.RunConfig(tls_flags=("--system-certs",)))
            cmd = run_mock.call_args[0][0]
            self.assertIn("--system-certs", cmd)
            self.assertIn("-c", cmd)
            self.assertIn("pyproject.toml", cmd)

    def test_run_audit_uses_configured_ignore_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "svc").mkdir()
            ok = subprocess.CompletedProcess(["uv"], 0, stdout='{"vulnerabilities": [], "summary": {}}', stderr="")
            cfg = qr.RunConfig(
                tls_flags=("--system-certs",),
                audit_ignores=("GHSA-1111",),
                audit_ignore_flag="--ignore-until-fixed",
            )
            with mock.patch.object(qr, "run_command", return_value=ok) as run_mock:
                qr.run_audit("svc", root, cfg)
            cmd = run_mock.call_args[0][0]
            self.assertIn("--system-certs", cmd)
            self.assertIn("--ignore-until-fixed", cmd)
            self.assertIn("GHSA-1111", cmd)


class TestRenderHtml(unittest.TestCase):
    META: ClassVar[dict[str, object]] = {
        "generated": "2026-09-30 10:00 UTC", "branch": "main", "commit": "abc123",
        "components": "2", "duration": "0m 5s",
        "audit_ignores": ["GHSA-5239-wwwm-4pmq"], "audit_ignore_flag": "--ignore-until-fixed",
    }

    def test_escapes_tool_output_and_drops_unsafe_links(self) -> None:
        hostile = qr.Finding(location="<img src=x onerror=alert(1)>", code="X1", message="<script>bad()</script>",
                             severity="error", url="javascript:alert(1)", links=[("evil", "javascript:alert(2)")])
        results = [
            qr.CheckResult("ruff", "dashboard", "fail", findings=[hostile]),
            qr.CheckResult("bandit", "dashboard", "pass"),
            qr.CheckResult("audit", "senders/hl7_sender", "error", output="<b>crash</b>"),
        ]
        delta = qr.ReportDelta(
            baseline_commit="prev99", new_count=1, fixed_count=2,
            new_by_check={"ruff": 1}, fixed_by_check={"ruff": 2},
            new_by_pair={("ruff", "dashboard"): 1}, fixed_by_pair={("ruff", "dashboard"): 2},
            new_finding_indices={("ruff", "dashboard"): {0}},
        )
        page = qr.render_html(results, self.META, delta=delta)
        self.assertNotIn("<script>bad()", page)
        self.assertNotIn("<img src=x", page)
        self.assertNotIn('href="javascript:', page)
        self.assertIn("&lt;b&gt;crash&lt;/b&gt;", page)
        self.assertIn('id="ruff--dashboard"', page)
        self.assertIn('id="audit--senders-hl7-sender"', page)
        self.assertIn('data-tab="security"', page)
        self.assertIn('aria-controls="tab-security"', page)
        self.assertIn('aria-labelledby="tab-btn-security"', page)
        # Tool error badge shows "1!" instead of "0".
        self.assertIn('<span class="count count--error">1!</span>', page)
        self.assertIn("badge-new", page)
        self.assertIn("data-new-only", page)
        self.assertIn("GHSA-5239-wwwm-4pmq", page)
        self.assertNotIn('data-tab="mypy"', page)
        self.assertIn("ISSUES FOUND", page)

    def test_all_passing_report_and_extended_tests_bar(self) -> None:
        results = [
            qr.CheckResult("mypy", "dashboard", "pass"),
            qr.CheckResult("tests", "dashboard", "pass", runner="unittest", summary={
                "ran": 4, "passed": 2, "failures": 0, "errors": 0, "skipped": 0,
                "expected_failures": 1, "unexpected_successes": 1, "duration": 0.25,
            }),
        ]
        page = qr.render_html(results, self.META)
        self.assertIn("ALL PASSED", page)
        self.assertIn("No issues found.", page)
        self.assertIn("bar__xfailed", page)
        self.assertIn("bar__xpassed", page)

    def test_fail_without_findings_renders_raw_output(self) -> None:
        res = qr.CheckResult("tests", "dashboard", "fail", output="Assertion failed in plugin")
        page = qr.render_html([res], self.META)
        self.assertIn("Assertion failed in plugin", page)
        self.assertNotIn("No issues found.", page)


class TestMainCli(unittest.TestCase):
    def test_parallel_run_writes_deterministic_report_compatible_with_quality_fix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for comp in ("alpha", "beta"):
                (root / comp).mkdir()
                (root / comp / "pyproject.toml").write_text(f'[project]\nname = "{comp}"\n')
            out = root / "reports" / "quality.html"

            def fake_ruff(component: str, _root: Path, _cfg: qr.RunConfig) -> qr.CheckResult:
                if component == "beta":
                    return qr.CheckResult("ruff", component, "fail", findings=[
                        qr.Finding("beta/a.py:1:1", "F401", "unused", "error", meta={"fix": "safe"})
                    ])
                return qr.CheckResult("ruff", component, "pass")

            with (
                mock.patch.object(qr, "ROOT_DIR", root),
                mock.patch.object(qr, "run_ruff", side_effect=fake_ruff),
                mock.patch.object(qr, "uv_tls_flags", return_value=("--system-certs",)),
                mock.patch.object(qr, "_git", return_value="main"),
            ):
                rc = qr.main(["--checks", "ruff", "--jobs", "2", "--output", str(out)])
            self.assertEqual(rc, 1)
            self.assertTrue(out.is_file())
            json_path = out.with_suffix(".json")
            self.assertTrue(json_path.is_file())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual([r["component"] for r in data["results"]], ["alpha", "beta"])
            # Verify sidecar remains directly consumable by quality_fix.load_report.
            loaded = qf.load_report(json_path, {"alpha", "beta"})
            self.assertEqual(len(loaded.findings), 1)
            self.assertEqual(loaded.findings[0].code, "F401")

    def test_rejects_invalid_cli_combinations(self) -> None:
        self.assertEqual(qr.main(["--output", str(ROOT / "report.json")]), 2)
        self.assertEqual(qr.main(["--jobs", "0"]), 2)
        self.assertEqual(qr.main(["--timeout", "-1"]), 2)
        self.assertEqual(qr.main(["--changed", "HEAD", "dashboard"]), 2)


if __name__ == "__main__":
    unittest.main()
