"""Contract tests for the phase 1 build boundary; no network or renderer required."""

from hashlib import sha256
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_site


def files_under(directory):
    """Snapshot authored bytes so staging/failures cannot silently change content."""
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="docs-kit-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.docs = self.project / "docs"
        self.docs.mkdir(parents=True)
        self.markdown = (
            '---\r\nid: example\r\nstatus: implemented\r\n---\r\n'
            '# Пример\r\n<div class="lvl lvl-1" markdown>\r\n'
            '**Описание** и [ссылка](components/example.md).\r\n</div>\r\n'
        ).encode("utf-8")
        (self.docs / "index.md").write_bytes(self.markdown)
        (self.docs / "components").mkdir()
        (self.docs / "components/example.md").write_text("# Компонент\n", encoding="utf-8")
        self.config = self.project / "docs-kit.toml"
        self.write_config()
        self.engine = self.root / "engine"
        (self.engine / "theme/assets").mkdir(parents=True)
        (self.engine / "theme/assets/levels.js").write_text("// engine script\n")
        (self.engine / "theme/assets/levels.css").write_text("/* engine style */\n")
        (self.engine / "theme/overrides").mkdir()
        (self.engine / "theme/overrides/main.html").write_text("<!-- engine template -->\n")
        (self.engine / "VERSION").write_text("0.1.0\n")
        self.asset = self.root / "verified-mermaid.js"
        self.asset.write_bytes(b"verified test asset")
        self.cache = self.root / "cache"

    def write_config(self, text=None):
        self.config.write_text(
            text if text is not None else (
                '[site]\nname = "Тестовый проект"\ndescription = "Описание"\n'
                'nav = [{ "Обзор" = "index.md" }, '
                '{ "Компонент" = "components/example.md" }]\n'
            ), encoding="utf-8",
        )


class ConfigContractTests(ProjectFixture):
    def test_valid_unicode_content_and_navigation_are_accepted(self):
        before = files_under(self.project)
        site = build_site.load_config(self.project)
        self.assertEqual(site["name"], "Тестовый проект")
        self.assertEqual(site["nav"][1], {"Компонент": "components/example.md"})
        self.assertEqual(files_under(self.project), before)

    def test_minimal_config_allows_automatic_navigation(self):
        self.write_config('[site]\nname = "Minimal"\n')
        self.assertEqual(build_site.load_config(self.project), {"name": "Minimal"})

    def test_reading_speed_is_optional_and_accepts_only_bounded_integers(self):
        self.write_config('[site]\nname = "Test"\nreading_words_per_minute = 250\n')
        self.assertEqual(build_site.load_config(self.project)["reading_words_per_minute"], 250)
        for value in ['true', '"200"', '0', '39', '1001', '200.5']:
            with self.subTest(value=value):
                self.write_config(f'[site]\nname = "Test"\nreading_words_per_minute = {value}\n')
                with self.assertRaises(ValueError):
                    build_site.load_config(self.project)

    def test_invalid_config_shapes_and_types_are_rejected(self):
        invalid = [
            '', 'site = "text"\n', '[other]\nname = "Wrong table"\n',
            '[site]\nname = ""\n', '[site]\nname = "   "\n',
            '[site]\nname = 12\n', '[site]\nname = true\n',
            '[site]\nname = "Test"\ndescription = 42\n',
            '[site]\nname = "Test"\nunsupported = "option"\n',
            '[site]\nname = "Test"\nnav = "index.md"\n',
            '[site]\nname = "Test"\nnav = []\n',
            '[site]\nname = "Test"\nnav = ["index.md"]\n',
            '[site]\nname = "Test"\nnav = [{}]\n',
            '[site]\nname = "Test"\nnav = [{a = "index.md", b = "index.md"}]\n',
            '[site]\nname = "Test"\nnav = [{a = 42}]\n',
        ]
        for text in invalid:
            with self.subTest(config=text):
                self.write_config(text)
                with self.assertRaises(ValueError):
                    build_site.load_config(self.project)

    def test_navigation_cannot_escape_docs_or_reference_missing_nonmarkdown_files(self):
        outside = self.project / "private.md"
        outside.write_text("Outside docs")
        (self.docs / "index.txt").write_text("Not a Markdown page")
        for path in ["../private.md", str(outside), "missing.md", "index.txt", "components"]:
            with self.subTest(path=path):
                self.write_config(f'[site]\nname = "Test"\nnav = [{{page = "{path}"}}]\n')
                with self.assertRaises(ValueError):
                    build_site.load_config(self.project)

    def test_missing_home_page_is_rejected_even_with_other_valid_pages(self):
        self.write_config('[site]\nname = "Test"\n')
        (self.docs / "index.md").unlink()
        with self.assertRaises(ValueError):
            build_site.load_config(self.project)

    def test_symlinked_docs_root_is_rejected(self):
        external_docs = self.root / "external-docs"
        self.docs.rename(external_docs)
        self.docs.symlink_to(external_docs, target_is_directory=True)
        with self.assertRaises(ValueError):
            build_site.load_config(self.project)

    def test_symlinks_anywhere_in_docs_are_rejected_even_when_not_in_navigation(self):
        secret = self.root / "outside.txt"
        secret.write_text("must not be published")
        candidates = [secret, self.docs / "index.md", self.root / "missing", self.root]
        for destination in candidates:
            with self.subTest(destination=destination):
                link = self.docs / "unlisted-link"
                link.symlink_to(destination, target_is_directory=destination.is_dir())
                try:
                    with self.assertRaises(ValueError):
                        build_site.load_config(self.project)
                finally:
                    link.unlink()

    def test_engine_asset_namespace_is_reserved_for_files_and_directories(self):
        reserved = self.docs / "_docs_kit"
        for is_directory in (False, True):
            with self.subTest(directory=is_directory):
                if is_directory:
                    reserved.mkdir()
                else:
                    reserved.write_text("authored collision")
                try:
                    with self.assertRaises(ValueError):
                        build_site.load_config(self.project)
                finally:
                    if is_directory:
                        reserved.rmdir()
                    else:
                        reserved.unlink()


class StagingAndOutputTests(ProjectFixture):
    def test_staging_preserves_authored_bytes_and_only_copies_documentation_and_theme(self):
        (self.project / "src").mkdir()
        (self.project / "src/private.py").write_text("# source is not a site asset\n")
        (self.project / ".env").write_text("LOCAL_ONLY=not_for_publication\n")
        (self.docs / "images").mkdir()
        (self.docs / "images/example.png").write_bytes(b"example image")
        before_project = files_under(self.project)
        before_engine = files_under(self.engine)
        stage = self.root / "stage"
        stage.mkdir()
        with patch.object(build_site, "ENGINE", self.engine):
            build_site.stage_project(
                self.project, stage, build_site.load_config(self.project),
                "https://example.test/project/", self.asset,
            )
        self.assertEqual((stage / "docs/index.md").read_bytes(), self.markdown)
        self.assertEqual((stage / "docs/images/example.png").read_bytes(), b"example image")
        self.assertEqual((stage / "docs/_docs_kit/mermaid-12.3.0.min.js").read_bytes(), self.asset.read_bytes())
        self.assertEqual((stage / "docs/_docs_kit/levels.js").read_bytes(),
                         (self.engine / "theme/assets/levels.js").read_bytes())
        self.assertTrue((stage / "overrides/main.html").is_file())
        self.assertTrue((stage / "mkdocs.yml").is_file())
        self.assertFalse((stage / "src").exists())
        self.assertFalse((stage / ".env").exists())
        self.assertEqual(files_under(self.project), before_project)
        self.assertEqual(files_under(self.engine), before_engine)

    def test_output_collisions_fail_before_network_or_renderer_without_mutation(self):
        outputs = [self.project, self.root, self.docs, self.docs / "generated", self.engine]
        for output in outputs:
            with self.subTest(output=output):
                before = files_under(self.root)
                with patch.object(build_site, "ENGINE", self.engine), \
                        patch.object(build_site, "mermaid_asset") as download, \
                        patch.object(build_site.subprocess, "run") as renderer:
                    with self.assertRaises(ValueError):
                        build_site.build(self.project, output, "https://example.test/project/", self.cache)
                    download.assert_not_called()
                    renderer.assert_not_called()
                self.assertEqual(files_under(self.root), before)

    def test_unowned_existing_output_is_never_replaced(self):
        output = self.root / "unrelated-output"
        output.mkdir()
        (output / "keep.txt").write_bytes(b"do not erase")
        before = files_under(self.root)
        with patch.object(build_site, "mermaid_asset") as download:
            with self.assertRaises(ValueError):
                build_site.build(self.project, output, "https://example.test/project/", self.cache)
            download.assert_not_called()
        self.assertEqual(files_under(self.root), before)

    def test_invalid_site_urls_are_rejected_before_network(self):
        for site_url in [
            "/relative/", "file:///tmp/site/", "https://example.test/no-trailing-slash",
            "https://user:password@example.test/", "https://example.test/?query=x/",
            "https://example.test/#fragment/",
        ]:
            with self.subTest(site_url=site_url):
                with patch.object(build_site, "mermaid_asset") as download:
                    with self.assertRaises(ValueError):
                        build_site.build(self.project, self.root / "site", site_url, self.cache)
                    download.assert_not_called()
                self.assertFalse((self.root / "site").exists())

    def test_failed_renderer_keeps_the_previous_generated_site_intact(self):
        output = self.root / "previous-site"
        (output / Path(build_site.MANIFEST).parent).mkdir(parents=True)
        (output / build_site.MANIFEST).write_text('{"engine_version": "previous"}\n')
        (output / "index.html").write_bytes(b"last known good site")
        previous = files_under(output)
        with patch.object(build_site, "ENGINE", self.engine), \
                patch.object(build_site, "mermaid_asset", return_value=self.asset), \
                patch.object(build_site.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "zensical")):
            with self.assertRaises(subprocess.CalledProcessError):
                build_site.build(self.project, output, "https://example.test/project/", self.cache)
        self.assertEqual(files_under(output), previous)
        self.assertEqual((self.docs / "index.md").read_bytes(), self.markdown)


class MermaidIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="docs-kit-asset-")
        self.addCleanup(self.temporary.cleanup)
        self.cache = Path(self.temporary.name) / "cache"
        self.target = self.cache / "mermaid-12.3.0.min.js"
        self.valid_bytes = b"known browser asset fixture"
        self.digest = sha256(self.valid_bytes).hexdigest()

    def test_verified_cached_asset_does_not_need_network(self):
        self.cache.mkdir()
        self.target.write_bytes(self.valid_bytes)
        with patch.object(build_site, "MERMAID_SHA256", self.digest), \
                patch.object(build_site, "urlopen") as network:
            self.assertEqual(build_site.mermaid_asset(self.cache), self.target)
            network.assert_not_called()

    def test_download_is_verified_before_it_can_become_a_browser_asset(self):
        with patch.object(build_site, "MERMAID_SHA256", self.digest), \
                patch.object(build_site, "urlopen", return_value=io.BytesIO(self.valid_bytes)) as network:
            result = build_site.mermaid_asset(self.cache)
            self.assertEqual(result.read_bytes(), self.valid_bytes)
            network.assert_called_once_with(build_site.MERMAID_URL, timeout=60)

    def test_checksum_mismatch_does_not_write_or_replace_an_asset(self):
        for previous in (None, b"old corrupt cache"):
            with self.subTest(previous_cache=previous):
                if previous is not None:
                    self.cache.mkdir(exist_ok=True)
                    self.target.write_bytes(previous)
                with patch.object(build_site, "MERMAID_SHA256", self.digest), \
                        patch.object(build_site, "urlopen", return_value=io.BytesIO(b"unexpected download")):
                    with self.assertRaises(ValueError):
                        build_site.mermaid_asset(self.cache)
                if previous is None:
                    self.assertFalse(self.target.exists())
                else:
                    self.assertEqual(self.target.read_bytes(), previous)

    def test_corrupt_cached_asset_is_replaced_only_by_verified_download(self):
        self.cache.mkdir()
        self.target.write_bytes(b"bad cached asset")
        with patch.object(build_site, "MERMAID_SHA256", self.digest), \
                patch.object(build_site, "urlopen", return_value=io.BytesIO(self.valid_bytes)):
            self.assertEqual(build_site.mermaid_asset(self.cache).read_bytes(), self.valid_bytes)


if __name__ == "__main__":
    unittest.main()
