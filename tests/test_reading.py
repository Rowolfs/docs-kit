"""Contracts for counting prose, not source syntax or generated interface labels."""

import unittest

from scripts.reading import annotate_html, block_metrics, count_words


class ReadingTests(unittest.TestCase):
    def test_cyrillic_english_numbers_and_internal_joiners(self):
        self.assertEqual(count_words("Приём API api-ready don't l’esprit 42 foo_bar"), 8)
        self.assertEqual(count_words("na\u0308ive café"), 2)
        self.assertEqual(count_words("--- … + _"), 0)

    def test_visible_prose_includes_headings_links_and_table_cells(self):
        source = '''<nav>Навигация вне блока</nav><div class="lvl lvl-1">
          <h2 id="orders">Приём заказов<a class="headerlink" href="#orders">¶</a></h2>
          <p>Готовый заказ: api-ready, don't, 42.</p>
          <p>Откройте <a href="https://example.test/not-counted">описание API</a>.</p>
          <p>Символы &amp; числа &#50;&#48;&#50;&#54;.</p>
          <p>Текст <strong>сохранён</strong>.</p>
          <table><tr><th>Вход</th><td>Данные</td></tr></table>
        </div><footer>Слова вне блока</footer>'''
        self.assertEqual(block_metrics(source)[0]["words"], 17)

    def test_code_mermaid_controls_and_scripts_are_not_prose(self):
        source = '''<div class="lvl lvl-1"><h2>Два слова</h2>
          <pre><code>ignored code words</code></pre>
          <code>inline ignored code</code><kbd>Ctrl K</kbd>
          <div class="mermaid">flowchart LR A --> B</div>
          <script>const ignored = "words";</script><style>.x { color: red }</style>
          <div class="level-control"><span>Подробность Кратко Полностью</span></div>
          <button>ignored button</button><output>ignored output</output>
          <svg><title>ignored diagram words</title></svg>
          <p>Три<code>ignored</code>четыре</p>
        </div>'''
        self.assertEqual(block_metrics(source)[0]["words"], 4)

    def test_inline_markup_does_not_split_a_word(self):
        self.assertEqual(block_metrics('<div class="lvl">по<strong>дроб</strong>но</div>')[0]["words"], 1)

    def test_each_level_counts_its_own_prose(self):
        source = '<div class="lvl lvl-1">Один</div><div class="lvl lvl-2">Два слова</div><div class="lvl lvl-3">Три простых слова</div>'
        self.assertEqual([item["words"] for item in block_metrics(source)], [1, 2, 3])

    def test_estimates_use_explicit_speed_and_do_not_round_short_text_to_zero_minutes(self):
        for words, speed, minutes, label in [(0, 200, 0, 'менее 1 минуты'), (199, 200, 0, 'менее 1 минуты'),
                                              (200, 200, 1, '≈ 1 минута чтения'), (201, 200, 2, '≈ 2 минуты чтения'),
                                              (120, 40, 3, '≈ 3 минуты чтения')]:
            with self.subTest(words=words, speed=speed):
                source = '<div class="lvl">' + 'слово ' * words + '</div>'
                self.assertEqual(block_metrics(source, speed)[0]["minutes"], minutes)
                self.assertIn(label, annotate_html(source, speed))

    def test_speed_is_a_bounded_integer_not_bool_or_arbitrary_input(self):
        for speed in [True, False, None, "200", 200.5, 0, -1, 39, 1001]:
            with self.subTest(speed=speed), self.assertRaises(ValueError):
                annotate_html('<div class="lvl">Текст</div>', speed)

    def test_badge_follows_heading_without_changing_heading_id_or_markup(self):
        source = '<article><div class="lvl lvl-2"><h2 id="stable">Как <em>работает</em><a href="#stable" class="headerlink">¶</a></h2>\n<p>Текст.</p></div></article>'
        output = annotate_html(source)
        heading = '<h2 id="stable">Как <em>работает</em><a href="#stable" class="headerlink">¶</a></h2>'
        self.assertIn(heading + '<p class="reading-meta"', output)
        self.assertIn('class="lvl lvl-2" data-reading-words="3" data-reading-minutes="0" data-reading-wpm="200"', output)
        self.assertIn('</p>\n<p>Текст.</p>', output)

    def test_headingless_blocks_and_void_elements_get_a_valid_label(self):
        source = '<div class="lvl lvl-1">Первое<br/>второе<img src="ignored words.png" alt="ignored words"><hr>третье</div>'
        output = annotate_html(source)
        self.assertIn('data-reading-words="3"', output)
        self.assertRegex(output, r'<div[^>]+><p class="reading-meta"')

    def test_reprocessing_is_byte_idempotent_and_labels_never_inflate_counts(self):
        source = '<div class="lvl lvl-1"><h2 id="first">Кратко</h2>\n<p>Текст страницы.</p>\n</div>'
        first = annotate_html(source)
        second = annotate_html(first)
        self.assertEqual(first, second)
        self.assertEqual(block_metrics(first)[0]["words"], 3)
        self.assertEqual(second.count('data-docs-kit-reading="true"'), 1)

    def test_changing_speed_replaces_generated_attributes_and_badges(self):
        source = '<div class="lvl lvl-1">' + 'слово ' * 120 + '</div>'
        slow = annotate_html(annotate_html(source, 200), 40)
        self.assertEqual(slow.count('data-reading-wpm="40"'), 1)
        self.assertNotIn('data-reading-wpm="200"', slow)
        self.assertIn('data-reading-minutes="3"', slow)
        self.assertEqual(block_metrics(slow)[0]["words"], 120)

    def test_pages_without_depth_blocks_are_unchanged(self):
        source = '<!doctype html><html><h1>Справка</h1><p>Обычная страница.</p></html>'
        self.assertEqual(annotate_html(source), source)


if __name__ == "__main__":
    unittest.main()
