"""File model contracts tested against real temporary Git repositories."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import docs_model as model


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_git('init', '-q')
        self.run_git('config', 'user.email', 'test@example.invalid')
        self.run_git('config', 'user.name', 'Test')
        for name, text in {'src/api.py': 'SECRET_CONTENT_NOT_MODEL', 'src/nested/job.py': 'pass',
                           'docs/components/api.md': '# API', '.gitignore': 'build/\nignored/\n',
                           'components.yaml': 'components:\n  api:\n    title: API\n    paths: ["src/**"]\n    depends_on: []\n    page: docs/components/api.md\n'}.items():
            self.write(name, text)
        self.run_git('add', '.')
        self.run_git('commit', '-qm', 'Initial')
        self.run_git('remote', 'add', 'origin', 'git@github.com:example/demo.git')

    def run_git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, check=True)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_hierarchy_and_no_source_contents(self):
        result = model.build_model(self.root)
        records = {record['id']: record for record in result['components']['api']}
        self.assertEqual(records['file:src/api.py']['parent'], 'directory:api:src')
        self.assertEqual(records['directory:api:src/nested']['parent'], 'directory:api:src')
        self.assertNotIn('SECRET_CONTENT_NOT_MODEL', json.dumps(result))
        self.assertEqual(model.code_url(self.root, 'src/api.py'), f"https://github.com/example/demo/blob/{result['source']['commit']}/src/api.py")

    def test_globs_are_directory_aware(self):
        for path, glob, expected in [('src/api.py', 'src/**', True), ('src/api.py', 'src/**/*.py', True),
                                     ('src/a/api.py', 'src/*.py', False), ('src/a/api.py', 'src/**/api.py', True),
                                     ('other.py', 'src/**', False)]:
            self.assertEqual(model.matches(path, glob), expected)

    def test_exclusions_and_untracked_targets(self):
        for name in ['.env', 'src/token.pem', 'ignored/file.py', 'build/out.py', 'docs/hidden.py', 'src/new.py']:
            self.write(name, 'contents')
        self.assertEqual(model.list_files(self.root), ['.gitignore', 'components.yaml', 'src/api.py', 'src/nested/job.py', 'src/new.py'])
        self.assertIsNone(model.code_url(self.root, 'src/new.py'))

    def test_changed_includes_deleted_and_untracked(self):
        self.write('src/api.py', 'changed')
        (self.root / 'src/nested/job.py').unlink()
        self.write('src/new.py', 'new')
        result = model.changed(self.root)
        self.assertEqual(result['components'], ['api'])
        self.assertEqual(result['files'], ['src/api.py', 'src/nested/job.py', 'src/new.py'])

    def test_nested_project_paths_and_github_prefix(self):
        self.write('demo/src/a.py', 'pass')
        self.write('demo/docs/component.md', '# Component')
        self.write('demo/components.yaml', 'components:\n  api:\n    title: API\n    paths: ["src/**"]\n    page: docs/component.md\n')
        self.run_git('add', 'demo')
        self.run_git('commit', '-qm', 'Demo')
        project = self.root / 'demo'
        self.assertEqual(model.list_files(project), ['components.yaml', 'src/a.py'])
        self.assertIn('/demo/src/a.py', model.code_url(project, 'src/a.py'))
        self.assertEqual(model.source_metadata(project)['committed_paths'], ['components.yaml', 'src/a.py'])
        self.write('src/api.py', 'outside demo change')
        self.write('demo/src/a.py', 'inside demo change')
        self.write('demo/src/new.py', 'inside demo untracked')
        difference = model.changed(project)
        self.assertEqual(difference['files'], ['src/a.py', 'src/new.py'])
        self.assertEqual(difference['components'], ['api'])

    def test_unborn_repository_can_build_and_report_changed_files(self):
        self.run_git('symbolic-ref', 'HEAD', 'refs/heads/unborn')
        source = model.source_metadata(self.root)
        self.assertIsNone(source['commit'])
        self.assertEqual(source['committed_paths'], [])
        self.assertIsNone(model.code_url(self.root, 'src/api.py', source))
        generated = model.generate(self.root)
        index = json.loads(Path(generated['index']).read_text())
        self.assertIsNone(index['source']['commit'])
        difference = model.changed(self.root)
        self.assertEqual(difference['files'], model.list_files(self.root))
        self.assertEqual(difference['components'], ['api'])

    def test_invalid_registry_and_overlaps_fail(self):
        original = (self.root / 'components.yaml').read_text()
        for content in [original.replace('depends_on: []', 'depends_on: [missing]'),
                        original.replace('docs/components/api.md', '../outside.md'),
                        original.replace('src/**', '../src/**')]:
            self.write('components.yaml', content)
            with self.assertRaises(ValueError):
                model.load_registry(self.root)
        self.write('components.yaml', original + '  other:\n    title: Other\n    paths: ["src/**"]\n    page: docs/components/api.md\n')
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            model.build_model(self.root)

    def test_shards_are_bounded_deterministic_and_cleaned(self):
        for n in range(400):
            self.write(f'src/long-{n:04d}-component-file-name.py', 'unread')
        output = self.root / 'build/model'
        result = model.generate(self.root, output)
        self.assertGreater(len(result['files']), 2)
        before = {name: (output / name).read_bytes() for name in result['files']}
        self.assertTrue(all(len(data) <= model.MAX_BYTES for data in before.values()))
        model.generate(self.root, output)
        self.assertEqual(before, {name: (output / name).read_bytes() for name in result['files']})
        for path in (self.root / 'src').glob('long-*'):
            path.unlink()
        fresh = model.generate(self.root, output)
        self.assertTrue(all(not (output / name).exists() for name in set(before) - set(fresh['files'])))

    def test_output_safety_and_symlink_exclusion(self):
        self.write('build/model/precious.txt', 'preserve')
        with self.assertRaises(ValueError):
            model.generate(self.root)
        self.assertEqual((self.root / 'build/model/precious.txt').read_text(), 'preserve')
        with self.assertRaises(ValueError):
            model.generate(self.root, self.root / 'src')
        (self.root / 'src/link.py').symlink_to(self.root / 'src/api.py')
        self.assertNotIn('src/link.py', model.list_files(self.root))

    def test_cli_queries_and_unknown_id(self):
        command = [sys.executable, str(Path(model.__file__)), '--project-dir', str(self.root)]
        shown = subprocess.run(command + ['show', 'api'], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(shown.stdout)['id'], 'component:api')
        found = subprocess.run(command + ['find', 'nested/job.py'], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(found.stdout)[0]['id'], 'file:src/nested/job.py')
        dependencies = subprocess.run(command + ['deps', 'api'], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(dependencies.stdout), {'id': 'api', 'depends_on': [], 'used_by': []})
        missing = subprocess.run(command + ['show', 'missing'], capture_output=True, text=True)
        self.assertEqual(missing.returncode, 1)
        self.assertIn('Unknown ID', missing.stderr)
        with self.assertRaises(ValueError):
            model.changed(self.root, '--output=unsafe')


if __name__ == '__main__':
    unittest.main()
