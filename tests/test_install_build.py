"""Exercise the actual installer -> model -> strict site build boundary offline."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from scripts.install import install
from scripts import build_site


class InstallBuildTests(unittest.TestCase):
    def test_fresh_scaffolding_builds_without_rewriting_authored_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            def git(*args):
                return subprocess.run(['git', '-C', str(project), *args], check=True, capture_output=True, text=True).stdout.strip()
            git('init', '-b', 'main')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            git('remote', 'add', 'origin', 'https://github.com/example/project.git')
            (project / 'src').mkdir()
            (project / 'src/app.py').write_text('print("example")\n')
            git('add', '.')
            git('commit', '-m', 'Initial source')
            install(project)
            (project / 'build/model/private.txt').write_text('Unowned sidecar must never be published')
            authored = {str(p.relative_to(project)): p.read_bytes() for p in (project / 'docs').rglob('*.md')}
            fake_mermaid = project / 'local-mermaid.js'
            fake_mermaid.write_text('// Offline browser asset; this test exercises HTML generation only.')
            vendor_assets = []
            for name in build_site.CYTOSCAPE_FILES:
                path = project / name
                path.write_text('// Offline vendor fixture')
                vendor_assets.append(path)
            with patch.object(build_site, 'mermaid_asset', return_value=fake_mermaid), \
                    patch.object(build_site, 'cytoscape_assets', return_value=vendor_assets):
                build_site.build(project, project / 'build/site', 'https://example.github.io/project/', project / '.cache')
            html = (project / 'build/site/_generated/code-map/index.html').read_text()
            self.assertIn('/blob/' + git('rev-parse', 'HEAD') + '/src/app.py', html)
            self.assertTrue((project / 'build/site/_docs_kit/model/index.json').is_file())
            self.assertIn('data-project-map', html)
            self.assertLess(html.index('data-project-map'), html.index('class="lvl lvl-1"'))
            self.assertIn('_docs_kit/cytoscape-3.35.0.min.js', html)
            self.assertIn('_docs_kit/project-map.js?v=', html)
            self.assertIn('_docs_kit/project-map.css?v=', html)
            self.assertEqual((project / 'build/site/_docs_kit/cytoscape-3.35.0.LICENSE.txt').read_text(), '// Offline vendor fixture')
            self.assertFalse((project / 'build/site/_docs_kit/model/private.txt').exists())
            self.assertTrue((project / 'build/model/private.txt').exists())
            self.assertEqual(authored, {str(p.relative_to(project)): p.read_bytes() for p in (project / 'docs').rglob('*.md')})
