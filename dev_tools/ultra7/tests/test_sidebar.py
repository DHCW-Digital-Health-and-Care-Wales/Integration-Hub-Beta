import gc
import tkinter as tk
import unittest

from ultra7.ui.sidebar import Sidebar
from ultra7.ui.themes import get_theme


def _tk_available() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class TestSidebarTheming(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.sidebar = Sidebar(
            self.root,
            on_select=lambda _n: None,
            on_new=lambda: None,
            on_remove=lambda _n: None,
            on_run_selected=lambda _ns: None,
        )

    def tearDown(self) -> None:
        self.root.destroy()
        gc.collect()

    def test_set_projects_uses_active_theme_colors(self) -> None:
        dark = get_theme("Dark")
        self.sidebar.apply_theme(dark)
        self.sidebar.set_projects(["Alpha", "Beta"], select="Alpha")

        alpha, beta = self.sidebar._project_items
        self.assertEqual(alpha.cget("bg"), dark.select_bg)
        self.assertEqual(alpha.label.cget("fg"), dark.select_fg)
        self.assertEqual(beta.cget("bg"), dark.pane_bg)
        self.assertEqual(beta.label.cget("fg"), dark.pane_fg)

    def test_apply_theme_updates_existing_rows(self) -> None:
        self.sidebar.set_projects(["Alpha", "Beta"], select="Alpha")
        dracula = get_theme("Dracula")
        self.sidebar.apply_theme(dracula)

        alpha, beta = self.sidebar._project_items
        self.assertEqual(alpha.cget("bg"), dracula.select_bg)
        self.assertEqual(alpha.label.cget("fg"), dracula.select_fg)
        self.assertEqual(beta.cget("bg"), dracula.pane_bg)
        self.assertEqual(beta.label.cget("fg"), dracula.pane_fg)


if __name__ == "__main__":
    unittest.main()
