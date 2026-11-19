"""Installer contracts: preserve author work and prepare a reproducible thin project."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts.install import END, START, install


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "sample-project"
        self.root.mkdir()
        self.git("init", "--quiet")
        (self.root / "src").mkdir()
        (self.root / "src/api.py").write_text("# fixture, not a purpose description\n")
        (self.root / "main.py").write_text("print('fixture')\n")
        (self.root / ".gitignore").write_text("node_modules/\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "--quiet", "-m", "Fixture")

    def git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.root), *arguments], check=True, capture_output=True).stdout

    def test_install_creates_structure_and_model_without_changing_git_head(self):
        head = self.git("rev-parse", "HEAD")
        (self.root / ".env").write_text("DO_NOT_DOCUMENT=example\n")
        (self.root / "private.pem").write_text("not a real key\n")
        install(self.root)
        registry = yaml.safe_load((self.root / "components.yaml").read_text())["components"]
        self.assertEqual(set(registry), {"root-files", "src"})
        self.assertEqual(registry["root-files"]["paths"], ["main.py"])
        self.assertEqual(registry["src"]["depends_on"], [])
        page = (self.root / registry["src"]["page"]).read_text()
        self.assertIn("status: planned", page)
        self.assertIn("Описание пока не написано", page)
        self.assertIn('class="lvl lvl-3"', page)
        self.assertTrue((self.root / "build/model/index.json").is_file())
        self.assertIn("build.yml@v0.3.0-alpha.1", (self.root / ".github/workflows/docs.yml").read_text())
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertNotIn(b"build/model/", self.git("ls-files", "--others", "--exclude-standard"))

    def test_rerun_preserves_written_pages_config_and_existing_agent_instructions(self):
        agents = self.root / "AGENTS.md"
        agents.write_text("# Existing rules\nKeep this exact text.\n")
        install(self.root)
        page = self.root / "docs/components/src.md"
        page.write_text(page.read_text() + "\nAn explanation written by the agent.\n")
        snapshots = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*")
                     if path.is_file() and ".git" not in path.parts and "build" not in path.parts}
        self.assertEqual(install(self.root), [])
        for name, content in snapshots.items():
            self.assertEqual((self.root / name).read_bytes(), content, name)
        self.assertTrue(agents.read_text().startswith("# Existing rules\nKeep this exact text.\n"))
        self.assertEqual(agents.read_text().count(START), 1)
        self.assertEqual(agents.read_text().count(END), 1)

    def test_directory_names_always_produce_distinct_valid_component_ids(self):
        names = ["123", "_internal", "a" * 90, "заказы", "заявки", "foo-bar", "foo_bar", "root-files"]
        for name in names:
            directory = self.root / name
            directory.mkdir()
            (directory / "example.py").write_text("# fixture\n")
        install(self.root)
        registry = yaml.safe_load((self.root / "components.yaml").read_text())["components"]
        self.assertEqual(len(registry), len(names) + 2)
        self.assertEqual({entry["title"] for entry in registry.values()}, set(names) | {"src", "Файлы корня"})
        for identifier, entry in registry.items():
            self.assertRegex(identifier, r"^[a-z][a-z0-9_-]{0,63}$")
            self.assertTrue((self.root / entry["page"]).is_file())
        initial = (self.root / "components.yaml").read_bytes()
        install(self.root)
        self.assertEqual((self.root / "components.yaml").read_bytes(), initial)

    def test_existing_page_conflict_refuses_before_any_changes(self):
        (self.root / "docs").mkdir()
        (self.root / "docs/index.md").write_text("# Existing docs\n")
        (self.root / "AGENTS.md").write_text("Existing instructions\n")
        with self.assertRaisesRegex(ValueError, "Existing file"):
            install(self.root)
        self.assertFalse((self.root / "components.yaml").exists())
        self.assertFalse((self.root / ".github").exists())
        self.assertEqual((self.root / "AGENTS.md").read_text(), "Existing instructions\n")

    def test_symlinked_output_parent_is_rejected_without_writes_outside_repo(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / ".github").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            install(self.root)
        self.assertFalse((self.root / "components.yaml").exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_model_failure_rolls_back_authored_outputs(self):
        (self.root / "AGENTS.md").write_text("Existing instructions\n")
        previous_ignore = (self.root / ".gitignore").read_bytes()
        with patch("scripts.docs_model.generate", side_effect=ValueError("Model failure")):
            with self.assertRaisesRegex(ValueError, "Model failure"):
                install(self.root)
        self.assertFalse((self.root / "components.yaml").exists())
        self.assertFalse((self.root / "docs").exists())
        self.assertEqual((self.root / "AGENTS.md").read_text(), "Existing instructions\n")
        self.assertEqual((self.root / ".gitignore").read_bytes(), previous_ignore)

    def test_broken_markers_and_nested_invocation_fail(self):
        (self.root / "AGENTS.md").write_text(END + "\n" + START)
        with self.assertRaisesRegex(ValueError, "Malformed"):
            install(self.root)
        with self.assertRaisesRegex(ValueError, "repository root"):
            install(self.root / "src")

    def test_shell_help_needs_no_network_or_repository(self):
        script = Path(__file__).resolve().parents[1] / "install.sh"
        result = subprocess.run(["bash", str(script), "--help"], cwd=self.temp.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--model", result.stdout)


if __name__ == "__main__":
    unittest.main()
