"""Generated maps and code links preserve authored content and commit identity."""
import unittest
from scripts.model_site import render_map, resolve_links


class ModelSiteTests(unittest.TestCase):
    def setUp(self):
        self.context = {'repository': 'https://github.com/example/project', 'commit': 'a' * 40,
                        'prefix': 'demo/', 'committed_paths': ['src/заказ.py']}
        self.paths = {'src/заказ.py', 'new.py'}

    def test_links_use_encoded_paths_and_exact_commit_in_nested_project(self):
        source = '<a class="code" href="file:src/заказ.py">Заказ</a><code>file:new.py</code>'
        result = resolve_links(source, self.paths, self.context)
        self.assertIn('/blob/' + 'a' * 40 + '/demo/src/%D0%B7%D0%B0%D0%BA%D0%B0%D0%B7.py', result)
        self.assertIn('<code>file:new.py</code>', result)
        self.assertIn('class="code"', result)
        self.assertIn('href="file:', source)

    def test_missing_uncommitted_and_deferred_symbol_links_fail(self):
        for href in ['file:missing.py', 'file:new.py', 'sym:orders.api.create']:
            with self.subTest(href=href), self.assertRaises(ValueError):
                resolve_links(f'<a href="{href}">Code</a>', self.paths, self.context)

    def test_rendered_code_samples_are_not_rewritten(self):
        source = '<pre><code>&lt;a href="file:missing.py"&gt;</code></pre>'
        self.assertEqual(resolve_links(source, self.paths, self.context), source)

    def test_href_rewrite_leaves_data_attributes_and_supports_unquoted_values(self):
        source = '<a data-href="keep" href=file:src/%D0%B7%D0%B0%D0%BA%D0%B0%D0%B7.py>Code</a>'
        result = resolve_links(source, self.paths, self.context)
        self.assertIn('data-href="keep"', result)
        self.assertNotIn('href=file:', result)
        self.assertIn(' href="https://github.com/', result)

    def test_mermaid_index_pages_use_directory_routes(self):
        for page, expected in [('docs/index.md', '../../'), ('docs/foo/index.md', '../../foo/')]:
            registry = {'one': {'title': 'One', 'paths': ['src/**'], 'page': page}}
            self.assertIn('href "' + expected + '"', render_map(registry, [], self.context))

    def test_map_escapes_labels_uses_relative_docs_and_no_uncommitted_link(self):
        registry = {'orders': {'title': '<script>test</script>', 'paths': ['src/**'],
                               'depends_on': [], 'page': 'docs/components/orders.md'}}
        records = [{'kind': 'file', 'code': {'path': 'src/заказ.py'}},
                   {'kind': 'file', 'code': {'path': 'new.py'}}]
        result = render_map(registry, records, self.context)
        self.assertNotIn('<script>', result)
        self.assertIn('../components/orders.md', result)
        self.assertIn('../../components/orders/', result)
        self.assertIn('<code>new.py</code>', result)
        self.assertNotIn('/blob/' + 'a' * 40 + '/demo/new.py', result)
