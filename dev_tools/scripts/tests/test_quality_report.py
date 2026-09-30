import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quality_report as qr  # noqa: E402

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

    def test_resolve_checks_expands_security_group(self) -> None:
        self.assertEqual(qr.resolve_checks("security,ruff"), ["ruff", "bandit", "audit"])
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

    def test_syntax_errors_without_code_get_placeholder(self) -> None:
        stdout = json.dumps([{"code": None, "filename": "x.py", "location": {"row": 1, "column": 1},
                              "message": "SyntaxError", "fix": None, "url": None}])
        [finding] = qr.parse_ruff(stdout, COMPONENT_DIR, ROOT)
        self.assertEqual(finding.code, "syntax-error")
        self.assertEqual(finding.location, "dashboard/x.py:1:1")

    def test_empty_output_means_no_findings(self) -> None:
        self.assertEqual(qr.parse_ruff("", COMPONENT_DIR, ROOT), [])


class TestParseMypy(unittest.TestCase):
    def test_notes_are_folded_into_preceding_error(self) -> None:
        lines = [
            {"file": "dashboard/app.py", "line": 6, "column": 11, "message": "Incompatible return value",
             "hint": None, "code": "return-value", "severity": "error"},
            {"file": "dashboard/app.py", "line": 6, "column": 11, "message": "See docs", "hint": None,
             "code": None, "severity": "note"},
        ]
        stdout = "\n".join(json.dumps(line) for line in lines) + "\nnot json\n"
        [finding] = qr.parse_mypy(stdout, COMPONENT_DIR, ROOT)
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
        # The stdlib frame is ignored; the last frame inside the repo is reported.
        self.assertEqual(failure.location, "dashboard/tests/test_app.py:12")

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

tests/test_app.py:12: AssertionError</failure></testcase>
<testcase classname="tests.test_broken" name="tests.test_broken" time="0.00">
<error message="collection failure">ImportError while importing test module</error></testcase>
<testcase classname="tests.test_app.TestApp" name="test_skip" time="0.00"><skipped message="later"/></testcase>
</testsuite></testsuites>
"""


class TestParseJunit(unittest.TestCase):
    def test_parses_counts_failures_and_collection_errors(self) -> None:
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
        # pytest frames are relative to the component directory.
        self.assertEqual(failure.location, "dashboard/tests/test_app.py:12")
        self.assertEqual(error.severity, "ERROR")
        self.assertEqual(error.message, "collection failure")

    def test_single_testsuite_root_and_no_tests(self) -> None:
        xml = '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" time="0.01"></testsuite>'
        summary, findings = qr.parse_junit(xml, COMPONENT_DIR, ROOT)
        self.assertEqual(summary["ran"], 0)
        self.assertEqual([f.code for f in findings], ["no-tests"])


class TestUsesPytest(unittest.TestCase):
    def _check(self, content: Optional[str]) -> bool:
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
                "issue_confidence": "HIGH", "issue_cwe": {"id": 78, "link": "https://cwe.mitre.org/data/definitions/78.html"},
                "issue_severity": "HIGH", "issue_text": "shell=True", "line_number": 5,
                "more_info": "https://bandit.readthedocs.io/en/latest/plugins/b602.html", "test_id": "B602",
                "test_name": "subprocess_popen_with_shell_equals_true",
            }],
            "errors": [{"filename": "dashboard/broken.py", "reason": "syntax error while parsing AST from file"}],
        })
        issue, error = qr.parse_bandit(stdout, COMPONENT_DIR, ROOT)
        self.assertEqual(issue.location, "dashboard/dashboard/app.py:5")
        self.assertEqual(issue.severity, "HIGH")
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


class TestRenderHtml(unittest.TestCase):
    META = {"generated": "2026-09-30 10:00 UTC", "branch": "main", "commit": "abc123", "components": "2",
            "duration": "0m 5s"}

    def test_escapes_tool_output_and_drops_unsafe_links(self) -> None:
        hostile = qr.Finding(location="<img src=x onerror=alert(1)>", code="X1", message="<script>bad()</script>",
                             severity="error", url="javascript:alert(1)", links=[("evil", "javascript:alert(2)")])
        results = [
            qr.CheckResult("ruff", "dashboard", "fail", findings=[hostile]),
            qr.CheckResult("bandit", "dashboard", "pass"),
            qr.CheckResult("audit", "senders/hl7_sender", "error", output="<b>crash</b>"),
        ]
        page = qr.render_html(results, self.META)
        self.assertNotIn("<script>bad()", page)
        self.assertNotIn("<img src=x", page)
        self.assertNotIn('href="javascript:', page)
        self.assertIn("&lt;b&gt;crash&lt;/b&gt;", page)
        self.assertIn('id="ruff--dashboard"', page)
        self.assertIn('id="audit--senders-hl7-sender"', page)
        self.assertIn('data-tab="security"', page)
        self.assertNotIn('data-tab="mypy"', page)
        self.assertIn("ISSUES FOUND", page)

    def test_all_passing_report(self) -> None:
        page = qr.render_html([qr.CheckResult("mypy", "dashboard", "pass")], self.META)
        self.assertIn("ALL PASSED", page)
        self.assertIn("No issues found.", page)


if __name__ == "__main__":
    unittest.main()
