import tempfile
import unittest
from pathlib import Path

from ultra7.models import Project
from ultra7.storage import ProjectStore, project_filename


class TestProjectFilename(unittest.TestCase):
    def test_sanitizes_unsafe_characters(self) -> None:
        self.assertEqual(project_filename("My Project"), "My Project.json")
        self.assertEqual(project_filename("a/b\\c"), "a_b_c.json")

    def test_rejects_empty_name(self) -> None:
        with self.assertRaises(ValueError):
            project_filename("   ")


class TestProjectStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = ProjectStore(Path(self._tmpdir.name) / "projects")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_save_and_load_round_trip(self) -> None:
        project = Project(name="Demo")
        self.store.save(project)
        loaded = self.store.load("Demo")
        self.assertEqual(loaded.name, "Demo")

    def test_list_projects_sorted(self) -> None:
        self.store.save(Project(name="Zeta"))
        self.store.save(Project(name="Alpha"))
        self.assertEqual(self.store.list_projects(), ["Alpha", "Zeta"])

    def test_delete_removes_file(self) -> None:
        self.store.save(Project(name="Demo"))
        self.assertTrue(self.store.exists("Demo"))
        self.store.delete("Demo")
        self.assertFalse(self.store.exists("Demo"))

    def test_delete_missing_project_is_noop(self) -> None:
        self.store.delete("does-not-exist")  # should not raise


if __name__ == "__main__":
    unittest.main()
