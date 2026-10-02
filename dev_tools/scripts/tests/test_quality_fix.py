import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quality_fix as qf  # noqa: E402


def _finding(check: str, component: str, location: str, code: str, message: str = "", **extra: Any) -> Dict[str, Any]:
    return {"location": location, "code": code, "message": message, "severity": extra.pop("severity", "error"),
            "url": "", "detail": extra.pop("detail", ""), "links": [], "meta": extra.pop("meta", {})}


def _write_report(path: Path, results: List[Dict[str, Any]]) -> Path:
    path.write_text(json.dumps({"meta": {"commit": "abc1234"}, "results": results}), encoding="utf-8")
    return path


class TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def read(self, rel: str) -> str:
        return (self.root / rel).read_bytes().decode("utf-8")


class TestVersions(unittest.TestCase):
    def test_release_key_ignores_trailing_zeros(self) -> None:
        self.assertEqual(qf.release_key("1.2.0"), qf.release_key("1.2"))
        self.assertLess(qf.release_key("1.9.5") or (), qf.release_key("1.10") or ())
        self.assertIsNone(qf.release_key("abc"))

    def test_choose_fix_prefers_installed_major(self) -> None:
        self.assertEqual(qf.choose_fix_version("2.31.0", ["3.0.1", "2.32.4"], False), ("2.32.4", ""))

    def test_choose_fix_needs_allow_major_to_cross_major(self) -> None:
        version, reason = qf.choose_fix_version("1.4.0", ["2.0.1"], False)
        self.assertIsNone(version)
        self.assertIn("--allow-major", reason)
        self.assertEqual(qf.choose_fix_version("1.4.0", ["2.0.1"], True), ("2.0.1", ""))

    def test_choose_fix_skips_prereleases_and_older_versions(self) -> None:
        self.assertEqual(qf.choose_fix_version("1.4.0", ["1.3.9", "1.5.0rc1", "1.5.1"], False), ("1.5.1", ""))
        # Edge case: report lists no usable fixed version.
        self.assertEqual(qf.choose_fix_version("1.4.0", ["—"], False)[0], None)

    def test_clause_allows(self) -> None:
        self.assertTrue(qf.clause_allows(">=", "1.0", "1.0.1"))
        self.assertFalse(qf.clause_allows("<", "1.0.1", "1.0.1"))
        self.assertTrue(qf.clause_allows("==", "1.*", "1.4.2"))
        self.assertFalse(qf.clause_allows("!=", "1.*", "1.4.2"))
        self.assertTrue(qf.clause_allows("~=", "2.32.0", "2.32.4"))
        self.assertFalse(qf.clause_allows("~=", "2.32.0", "2.33.0"))


class TestUpdateRequirement(unittest.TestCase):
    def check(self, requirement: str, target: str, status: str, value: str = "") -> qf.ReqUpdate:
        update = qf.update_requirement(requirement, target)
        self.assertEqual(update.status, status, update)
        if value:
            self.assertEqual(update.value, value)
        return update

    def test_exact_pin_is_moved_to_target(self) -> None:
        update = self.check("azure-servicebus==7.14.3", "7.14.5", "changed", "azure-servicebus==7.14.5")
        self.assertFalse(update.allows)

    def test_floor_is_raised_and_upper_bound_kept(self) -> None:
        update = self.check("azure-core>=1.38.0,<2", "1.38.2", "changed", "azure-core>=1.38.2,<2")
        self.assertTrue(update.allows)

    def test_bare_requirement_gets_a_floor(self) -> None:
        self.check("requests", "2.32.4", "changed", "requests>=2.32.4")

    def test_extras_markers_and_separator_are_preserved(self) -> None:
        self.check("uvicorn[standard]>=0.30, <1; python_version >= '3.13'", "0.37.1", "changed",
                   "uvicorn[standard]>=0.37.1, <1; python_version >= '3.13'")

    def test_compatible_release(self) -> None:
        self.check("pkg~=2.32.0", "2.32.4", "changed", "pkg~=2.32.4")
        # Fewer components: keep the original upper bound and add a floor rather than narrowing it.
        self.check("pkg~=2.30", "2.32.4", "changed", "pkg~=2.30,>=2.32.4")
        self.check("pkg~=2.32.0", "2.33.0", "blocked")

    def test_upper_bound_below_target_is_blocked(self) -> None:
        update = self.check("pkg>=1,<1.0.2", "1.0.2", "blocked")
        self.assertIn("<1.0.2", update.value)

    def test_already_fixed_is_unchanged(self) -> None:
        self.check("pkg>=2.0", "1.9.9", "unchanged")
        self.check("pkg==1.0.2", "1.0.2", "unchanged")

    def test_url_requirement_is_blocked(self) -> None:
        self.check("pkg @ https://example.org/pkg.whl", "1.0", "blocked")

    def test_requirement_entries_cover_uv_sections(self) -> None:
        data = {
            "project": {"dependencies": ["a==1"], "optional-dependencies": {"x": ["b>=1"]}},
            "dependency-groups": {"dev": ["c==1", {"include-group": "x"}]},
            "tool": {"uv": {"override-dependencies": ["d>=1"], "constraint-dependencies": ["e<2"]}},
        }
        self.assertEqual([r for _, r in qf.requirement_entries(data)], ["a==1", "b>=1", "c==1", "d>=1", "e<2"])


class TestUnusedIgnore(TempDirTestCase):
    def test_removes_whole_comment(self) -> None:
        path = self.write("m.py", "x = 1  # type: ignore[assignment]\n")
        qf.remove_unused_ignore(path, 1, 'Unused "type: ignore" comment')
        self.assertEqual(self.read("m.py"), "x = 1\n")

    def test_removes_only_unused_codes_and_keeps_other_comments(self) -> None:
        path = self.write("m.py", "x = 1  # type: ignore[assignment, misc]  # noqa: E501\n")
        qf.remove_unused_ignore(path, 1, 'Unused "type: ignore[misc]" comment')
        self.assertEqual(self.read("m.py"), "x = 1  # type: ignore[assignment]  # noqa: E501\n")

    def test_stale_line_raises(self) -> None:
        path = self.write("m.py", "x = 1\n")
        with self.assertRaises(qf.FixError):
            qf.remove_unused_ignore(path, 1, 'Unused "type: ignore" comment')
        with self.assertRaises(qf.FixError):
            qf.remove_unused_ignore(path, 5, 'Unused "type: ignore" comment')

    def test_crlf_line_endings_are_preserved(self) -> None:
        path = self.write("m.py", "a = 1\r\nx = 1  # type: ignore\r\n")
        qf.remove_unused_ignore(path, 2, 'Unused "type: ignore" comment')
        self.assertEqual(self.read("m.py"), "a = 1\r\nx = 1\r\n")


class TestSuppressions(TempDirTestCase):
    def test_adds_type_ignore_and_nosec(self) -> None:
        path = self.write("m.py", "x = f()\n")
        qf.add_suppressions(path, 1, ["arg-type"], ["B310"])
        self.assertEqual(self.read("m.py"), "x = f()  # type: ignore[arg-type]  # nosec B310\n")

    def test_merges_existing_codes_and_puts_type_ignore_first(self) -> None:
        path = self.write("m.py", "x = f()  # noqa: E501  # type: ignore[misc]  # nosec B101\n")
        qf.add_suppressions(path, 1, ["arg-type"], ["B310"])
        self.assertEqual(self.read("m.py"),
                         "x = f()  # type: ignore[misc, arg-type]  # noqa: E501  # nosec B101, B310\n")

    def test_bare_ignore_already_covers_everything(self) -> None:
        path = self.write("m.py", "x = f()  # type: ignore\n")
        self.assertEqual(qf.add_suppressions(path, 1, ["misc"], []), "already suppressed")

    def test_hash_inside_string_is_not_treated_as_comment(self) -> None:
        path = self.write("m.py", "x = '#'\n")
        qf.add_suppressions(path, 1, ["misc"], [])
        self.assertEqual(self.read("m.py"), "x = '#'  # type: ignore[misc]\n")

    def test_refuses_lines_inside_multiline_strings(self) -> None:
        path = self.write("m.py", 'x = """a\nb\n"""\n')
        with self.assertRaises(qf.FixError):
            qf.add_suppressions(path, 1, ["misc"], [])


class TestAnnotateNone(TempDirTestCase):
    def test_adds_none_to_multiline_signature(self) -> None:
        path = self.write("m.py", "class A:\n    def f(\n        self,\n    ):\n        print(1)\n")
        qf.add_none_return(path, 2)
        self.assertEqual(self.read("m.py"), "class A:\n    def f(\n        self,\n    ) -> None:\n        print(1)\n")

    def test_handles_dict_default_and_explicit_return_none(self) -> None:
        path = self.write("m.py", "def f(a={'k': 1}):\n    return None\n")
        qf.add_none_return(path, 1)
        self.assertEqual(self.read("m.py"), "def f(a={'k': 1}) -> None:\n    return None\n")

    def test_refuses_functions_that_return_values(self) -> None:
        path = self.write("m.py", "def f():\n    def g():\n        pass\n    return 1\n")
        with self.assertRaises(qf.FixError):
            qf.add_none_return(path, 1)

    def test_nested_return_value_does_not_block_outer_function(self) -> None:
        path = self.write("m.py", "def f():\n    def g():\n        return 1\n    g()\n")
        qf.add_none_return(path, 1)
        self.assertTrue(self.read("m.py").startswith("def f() -> None:"))


class TestRequestTimeout(TempDirTestCase):
    def test_appends_after_last_argument(self) -> None:
        path = self.write("m.py", "import requests\nr = requests.get(url, headers=h)\n")
        qf.add_request_timeout(path, 2, 30)
        self.assertIn("requests.get(url, headers=h, timeout=30)", self.read("m.py"))

    def test_call_without_arguments(self) -> None:
        path = self.write("m.py", "import requests\nr = requests.get()\n")
        qf.add_request_timeout(path, 2, 10)
        self.assertIn("requests.get(timeout=10)", self.read("m.py"))

    def test_multiline_call_with_trailing_comma(self) -> None:
        path = self.write("m.py", "import requests\nr = requests.post(\n    url,\n    json=body,\n)\n")
        qf.add_request_timeout(path, 2, 30)
        self.assertEqual(self.read("m.py"),
                         "import requests\nr = requests.post(\n    url,\n    json=body, timeout=30,\n)\n")

    def test_refuses_kwargs_splat(self) -> None:
        path = self.write("m.py", "import requests\nr = requests.get(url, **opts)\n")
        with self.assertRaises(qf.FixError):
            qf.add_request_timeout(path, 2, 30)


class TestManifestEdits(TempDirTestCase):
    def test_replace_requirement_keeps_formatting(self) -> None:
        path = self.write("pyproject.toml", '[project]\nname = "x"\ndependencies = [\n  "a==1.0",  # pinned\n]\n')
        qf.replace_requirement(path, "a==1.0", "a==1.0.1")
        self.assertEqual(self.read("pyproject.toml"),
                         '[project]\nname = "x"\ndependencies = [\n  "a==1.0.1",  # pinned\n]\n')

    def test_replace_requirement_missing_literal_raises(self) -> None:
        path = self.write("pyproject.toml", '[project]\nname = "x"\ndependencies = ["a==1.0"]\n')
        with self.assertRaises(qf.FixError):
            qf.replace_requirement(path, "b==1.0", "b==1.1")

    def test_add_override_to_existing_list(self) -> None:
        path = self.write("pyproject.toml", '[project]\nname = "x"\n\n[tool.uv]\noverride-dependencies = ["a>=1"]\n')
        qf.add_override(path, "b>=2")
        self.assertIn('override-dependencies = ["b>=2", "a>=1"]', self.read("pyproject.toml"))

    def test_add_override_under_existing_tool_uv(self) -> None:
        path = self.write("pyproject.toml", '[project]\nname = "x"\n\n[tool.uv]\npackage = false\n')
        qf.add_override(path, "b>=2")
        self.assertIn('[tool.uv]\noverride-dependencies = ["b>=2"]\npackage = false', self.read("pyproject.toml"))

    def test_add_override_creates_section(self) -> None:
        path = self.write("pyproject.toml", '[project]\nname = "x"\n')
        qf.add_override(path, "b>=2")
        self.assertTrue(self.read("pyproject.toml").endswith('\n\n[tool.uv]\noverride-dependencies = ["b>=2"]\n'))


class TestPlanning(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("shared_libs/lib/pyproject.toml",
                   '[project]\nname = "lib"\nversion = "0.1.0"\ndependencies = ["pkg==1.0.0"]\n')
        self.write("shared_libs/lib/uv.lock", 'version = 1\n\n[[package]]\nname = "pkg"\nversion = "1.0.0"\n')
        self.write("svc/pyproject.toml",
                   '[project]\nname = "svc"\nversion = "0.1.0"\ndependencies = ["lib"]\n\n'
                   '[tool.uv.sources]\nlib = { path = "../shared_libs/lib" }\n')
        self.write("svc/uv.lock", 'version = 1\n\n[[package]]\nname = "pkg"\nversion = "1.0.0"\n'
                                  '\n[[package]]\nname = "transitive-pkg"\nversion = "3.1.0"\n')
        self.write("svc/svc/app.py", "x = 1  # type: ignore\n")
        self.components = ["shared_libs/lib", "svc"]

    def report(self, results: List[Dict[str, Any]]) -> qf.Report:
        return qf.load_report(_write_report(self.root / "report.json", results))

    def audit_result(self, package: str, installed: str, fixed: str) -> Dict[str, Any]:
        meta = {"package": package, "installed": installed, "fixed_in": fixed, "published": ""}
        return {"check": "audit", "component": "svc", "status": "fail",
                "findings": [_finding("audit", "svc", f"{package}=={installed}", "GHSA-x", meta=meta)]}

    def test_dependency_graph(self) -> None:
        graph = qf.build_source_graph(self.root, self.components)
        self.assertEqual(graph, {"shared_libs/lib": [], "svc": ["shared_libs/lib"]})
        self.assertEqual(qf.dependents_of({"shared_libs/lib"}, graph), {"shared_libs/lib", "svc"})

    def test_pin_in_shared_lib_blocks_lock_only_audit(self) -> None:
        report = self.report([self.audit_result("pkg", "1.0.0", "1.0.1")])
        plan = qf.plan_audit(report, qf.Options(audit=True), self.root, self.components)
        self.assertEqual(plan.actions, [])
        [(_, reason)] = plan.skipped
        self.assertIn("--audit-pin", reason)

    def test_audit_pin_edits_shared_lib_and_relocks_dependents(self) -> None:
        report = self.report([self.audit_result("pkg", "1.0.0", "1.0.1")])
        plan = qf.plan_audit(report, qf.Options(audit=True, audit_pin=True), self.root, self.components)
        descriptions = [(a.phase, a.component, a.description) for a in plan.actions]
        self.assertEqual(descriptions, [
            (qf.PHASE_MANIFEST, "shared_libs/lib", "shared_libs/lib/pyproject.toml: 'pkg==1.0.0' -> 'pkg==1.0.1'"),
            (qf.PHASE_LOCK, "shared_libs/lib", "`uv --native-tls lock --upgrade-package pkg==1.0.1`"),
            (qf.PHASE_LOCK, "svc", "`uv --native-tls lock --upgrade-package pkg==1.0.1`"),
        ])
        self.assertEqual(len(plan.claimed), 1)
        plan.actions[0].run()
        self.assertIn('"pkg==1.0.1"', self.read("shared_libs/lib/pyproject.toml"))

    def test_undeclared_package_is_lock_only_by_default(self) -> None:
        report = self.report([self.audit_result("transitive_pkg", "3.1.0", "3.1.2, 4.0.0")])
        plan = qf.plan_audit(report, qf.Options(audit=True), self.root, self.components)
        self.assertEqual([a.description for a in plan.actions],
                         ["`uv --native-tls lock --upgrade-package transitive-pkg==3.1.2`"])

    def test_transitive_and_override_add_a_requirement(self) -> None:
        report = self.report([self.audit_result("transitive-pkg", "3.1.0", "3.1.2")])
        plan = qf.plan_audit(report, qf.Options(audit=True, audit_transitive=True), self.root, self.components)
        self.assertIn("`uv add --frozen transitive-pkg>=3.1.2` (direct minimum version)",
                      [a.description for a in plan.actions])
        plan = qf.plan_audit(report, qf.Options(audit=True, audit_override=True), self.root, self.components)
        override = next(a for a in plan.actions if a.fixer == "audit-override")
        override.run()
        self.assertIn('override-dependencies = ["transitive-pkg>=3.1.2"]', self.read("svc/pyproject.toml"))

    def test_invalid_package_name_is_never_passed_to_uv(self) -> None:
        report = self.report([self.audit_result("--index-url=evil", "1.0", "1.1")])
        plan = qf.plan_audit(report, qf.Options(audit=True), self.root, self.components)
        self.assertEqual(plan.actions, [])
        self.assertIn("invalid package name", plan.skipped[0][1])

    def test_ruff_plan_only_counts_fixable_findings(self) -> None:
        report = self.report([{"check": "ruff", "component": "svc", "status": "fail", "findings": [
            _finding("ruff", "svc", "svc/svc/app.py:1:1", "F401", meta={"fix": "safe"}),
            _finding("ruff", "svc", "svc/svc/app.py:2:1", "E711", meta={"fix": "unsafe"}),
            _finding("ruff", "svc", "svc/svc/app.py:3:1", "A001", meta={"fix": ""}),
        ]}])
        self.assertEqual(len(qf.plan_ruff(report, False, self.root).claimed), 1)
        self.assertEqual(len(qf.plan_ruff(report, True, self.root).claimed), 2)

    def test_line_fix_rejects_paths_outside_the_repo(self) -> None:
        report = self.report([{"check": "mypy", "component": "svc", "status": "fail", "findings": [
            _finding("mypy", "svc", "../outside.py:1:1", "unused-ignore", 'Unused "type: ignore" comment'),
        ]}])
        plan = qf.plan_line_fixes(report, qf.Options(unused_ignores=True), self.root)
        self.assertEqual(plan.actions, [])
        self.assertEqual(len(plan.skipped), 1)

    def test_baseline_skips_findings_claimed_by_other_fixers_and_triage_lists_the_rest(self) -> None:
        report = self.report([
            {"check": "mypy", "component": "svc", "status": "fail", "findings": [
                _finding("mypy", "svc", "svc/svc/app.py:1:1", "unused-ignore", 'Unused "type: ignore" comment'),
                _finding("mypy", "svc", "svc/svc/app.py:1:5", "misc", "Cannot infer type of lambda"),
            ]},
            {"check": "tests", "component": "svc", "status": "error", "findings": [], "output": "boom"},
        ])
        plan = qf.build_plan(report, qf.Options(unused_ignores=True), self.root, self.components)
        rows = qf.triage_rows(report, plan)
        self.assertEqual([r["code"] for r in rows], ["misc", "check-error"])

        plan = qf.build_plan(report, qf.Options(unused_ignores=True, baseline=True), self.root, self.components)
        self.assertEqual([a.fixer for a in plan.actions], ["unused-ignores", "baseline"])
        for action in plan.actions:
            action.run()
        self.assertEqual(self.read("svc/svc/app.py"), "x = 1  # type: ignore[misc]\n")

    def test_write_triage_markdown_escapes_pipes(self) -> None:
        report = self.report([{"check": "mypy", "component": "svc", "status": "fail", "findings": [
            _finding("mypy", "svc", "svc/svc/app.py:1:1", "arg-type", "expected str | None"),
        ]}])
        out = self.root / "triage.md"
        rows = qf.write_triage(out, report, qf.Plan(), qf.Options())
        self.assertEqual(len(rows), 1)
        self.assertIn("expected str \\| None", out.read_text(encoding="utf-8"))

    def test_triage_flags_findings_an_unselected_fixer_could_fix(self) -> None:
        report = self.report([{"check": "ruff", "component": "svc", "status": "fail", "findings": [
            _finding("ruff", "svc", "svc/svc/app.py:1:1", "I001", meta={"fix": "safe"}),
            _finding("ruff", "svc", "svc/svc/app.py:2:1", "A001", meta={"fix": ""}),
        ]}])
        rows = qf.triage_rows(report, qf.Plan())
        self.assertEqual([r["note"] for r in rows], ["auto-fixable with --ruff", ""])
        self.assertEqual(qf.triage_summary(rows), "ruff 2; 1 auto-fixable with: --ruff")
        # Once --ruff is selected the fixable finding is claimed and drops out of triage.
        rows = qf.triage_rows(report, qf.build_plan(report, qf.Options(ruff=True), self.root, self.components))
        self.assertEqual([r["code"] for r in rows], ["A001"])


class TestCli(unittest.TestCase):
    def test_options_shortcuts(self) -> None:
        opts = qf.options_from_args(qf.parse_args(["--safe"]))
        self.assertEqual(opts.selected(), ["ruff", "audit", "audit-pin", "unused-ignores"])
        opts = qf.options_from_args(qf.parse_args(["--audit-override", "--ruff-unsafe"]))
        self.assertTrue(opts.audit and opts.ruff and opts.ruff_unsafe)

    def test_transitive_and_override_are_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            qf.parse_args(["--audit-transitive", "--audit-override"])

    def test_requires_a_fixer_or_triage(self) -> None:
        with self.assertLogs("quality_fix", level="ERROR"):
            self.assertEqual(qf.main([]), 2)


if __name__ == "__main__":
    unittest.main()
