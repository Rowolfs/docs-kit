"""Check the phase 2 reader against a built or published docs-kit demo."""

import argparse
import json
import math
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import expect, sync_playwright


# Observe genuine closed Mermaid roots without changing their rendering or mode.
# This test-only instrumentation is never copied into the site.
INSTRUMENT = """
window.__docsKitRoots = [];
const attach = Element.prototype.attachShadow;
Element.prototype.attachShadow = function(options) {
  const root = attach.call(this, options);
  window.__docsKitRoots.push(root);
  return root;
};
"""
LABELS = ['Кратко', 'Подробно', 'Полностью']


def slider(page):
    return page.get_by_role('slider', name='Подробность', exact=True)


def visible_levels(page):
    return page.locator('article .lvl').evaluate_all(
        'nodes => nodes.map(node => !node.hidden && getComputedStyle(node).display !== "none")'
    )


def assert_metrics(page):
    blocks = page.locator('article .lvl').evaluate_all('''nodes => nodes.map(node => ({
      words: Number(node.dataset.readingWords), minutes: Number(node.dataset.readingMinutes),
      wpm: Number(node.dataset.readingWpm), visible: !node.hidden,
      badges: node.querySelectorAll('.reading-meta').length
    }))''')
    assert len(blocks) == 3, blocks
    for block in blocks:
        assert block['words'] > 0 and block['wpm'] > 0, block
        assert block['badges'] == 1, block
        expected = 0 if block['words'] < block['wpm'] else math.ceil(block['words'] / block['wpm'])
        assert block['minutes'] == expected, block
    words = sum(block['words'] for block in blocks if block['visible'])
    wpm = blocks[0]['wpm']
    minutes = 0 if words < wpm else math.ceil(words / wpm)
    summary = page.locator('.reading-summary')
    expect(summary).to_have_attribute('data-visible-words', str(words))
    expect(summary).to_have_attribute('data-visible-minutes', str(minutes))


def assert_level(page, level):
    expect(slider(page)).to_have_value(str(level))
    expect(slider(page)).to_have_attribute('aria-valuetext', LABELS[level - 1])
    expect(page.locator('.level-control output')).to_have_text(LABELS[level - 1])
    assert visible_levels(page) == [depth <= level for depth in (1, 2, 3)]
    assert_metrics(page)


def choose(page, level):
    control = slider(page)
    expect(control).to_be_visible()
    control.press('Home')
    for _ in range(level - 1):
        control.press('ArrowRight')
    assert_level(page, level)


def preference(page):
    return page.evaluate('''() => Object.fromEntries(Object.entries(localStorage)
      .filter(([key]) => key.startsWith('docs-kit:level:')))''')


def wait_home(page, base_url, title):
    page.wait_for_url(base_url)
    expect(page.locator('article h1')).to_have_text(title)


def check_search(page, base_url, query, keyboard):
    page.goto(base_url, wait_until='networkidle')
    choose(page, 1)
    stored = preference(page)
    page.locator('.md-search__button').click()
    search = page.get_by_role('combobox')
    expect(search).to_be_visible()
    search.fill(query)
    result = page.locator('dialog[open] a[role="option"][href*="#reader-details"]').first
    expect(result).to_be_visible(timeout=15000)
    if keyboard:
        # Native anchor activation checks the result's keyboard path without assuming ranking.
        result.focus()
        result.press('Enter')
    else:
        result.click()
    page.wait_for_url(lambda url: urlsplit(url).fragment == 'reader-details')
    expect(page.locator('#reader-details')).to_be_visible()
    assert_level(page, 3)
    assert preference(page) == stored, 'Search navigation must not replace the explicit preference'


def check_fallbacks(browser, base_url, result):
    no_js = browser.new_context(java_script_enabled=False)
    page = no_js.new_page()
    page.goto(base_url, wait_until='networkidle')
    assert visible_levels(page) == [True, True, True]
    assert page.get_by_role('slider').count() == 0
    assert page.locator('article .reading-meta').count() == 3
    for badge in page.locator('article .reading-meta').all():
        expect(badge).to_be_visible()
    assert 'flowchart' in page.locator('pre.mermaid').inner_text()
    no_js.close()
    result['checks'].append('Without JavaScript all blocks, static reading metrics and diagram source remain readable')

    no_storage = browser.new_context()
    no_storage.add_init_script('''
      for (const name of ['getItem', 'setItem']) {
        const original = Storage.prototype[name];
        Storage.prototype[name] = function(key, ...args) {
          if (key.startsWith('docs-kit:level:')) throw new DOMException('Disabled', 'SecurityError');
          return original.call(this, key, ...args);
        };
      }
    ''')
    page = no_storage.new_page()
    page.on('pageerror', lambda error: result['page_errors'].append(str(error)))
    page.goto(base_url, wait_until='networkidle')
    assert_level(page, 1)
    choose(page, 3)
    page.reload(wait_until='networkidle')
    assert_level(page, 1)
    no_storage.close()
    result['checks'].append('Denied reading-preference storage preserves working controls and defaults on reload')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8766/docs-kit/')
    parser.add_argument('--browser', help="Chromium executable; omit for Playwright's browser")
    parser.add_argument('--output', default='build/phase2')
    args = parser.parse_args()
    base_url = args.url.rstrip('/') + '/'
    origin = urlsplit(base_url)[:2]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    result = {'url': base_url, 'checks': [], 'limitations': [], 'page_errors': [],
              'console_errors': [], 'http_errors': [], 'failed_requests': [], 'external_requests': []}

    with sync_playwright() as playwright:
        options = {'headless': True}
        if args.browser:
            options['executable_path'] = args.browser
        browser = playwright.chromium.launch(**options)
        result['browser'] = browser.version
        context = browser.new_context(viewport={'width': 1280, 'height': 900}, color_scheme='light')
        context.add_init_script(INSTRUMENT)
        context.on('request', lambda request: result['external_requests'].append(request.url)
                   if urlsplit(request.url)[:2] != origin else None)
        page = context.new_page()
        page.on('pageerror', lambda error: result['page_errors'].append(str(error)))
        page.on('console', lambda message: result['console_errors'].append(message.text)
                if message.type == 'error' else None)
        page.on('response', lambda response: result['http_errors'].append(f'HTTP {response.status} {response.url}')
                if response.status >= 400 else None)
        page.on('requestfailed', lambda request: result['failed_requests'].append(
            {'url': request.url, 'failure': request.failure}))

        try:
            page.goto(base_url, wait_until='networkidle')
            expect(page.locator('article h1')).to_be_visible()
            expect(page.locator('.md-header__topic').first).to_contain_text('Quokki')
            home_title = page.locator('article h1').inner_text()
            expect(slider(page)).to_be_visible()
            for attribute, value in [('min', '1'), ('max', '3'), ('step', '1')]:
                expect(slider(page)).to_have_attribute(attribute, value)
            expect(page.locator('.level-control__scale span')).to_have_text(LABELS)
            assert page.locator('.level-control button').count() == 0
            assert_level(page, 1)
            detail_toc = page.locator('.md-sidebar--secondary a[href$="#reader-details"]').first
            expect(detail_toc).to_have_count(1)
            expect(detail_toc).to_be_hidden()
            result['checks'].append('Brief/Detailed/Full slider, static block metrics and visible-content totals agree')

            control = slider(page)
            control.press('End')
            assert_level(page, 3)
            expect(detail_toc).to_be_visible()
            control.press('ArrowRight')
            assert_level(page, 3)
            control.press('Home')
            control.press('ArrowLeft')
            assert_level(page, 1)
            control.scroll_into_view_if_needed()
            box = control.bounding_box()
            page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            assert_level(page, 2)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] - 2, box['y'] + box['height'] / 2, steps=8)
            page.mouse.up()
            assert_level(page, 3)
            result['checks'].append('Pointer/drag, arrows and Home/End change three cumulative levels; TOC follows visibility')

            for level in (2, 3, 1, 3):
                choose(page, level)
            page.reload(wait_until='networkidle')
            assert_level(page, 3)
            link = page.locator("article .lvl-1 a[href*='components/build/']")
            expect(link).to_have_count(1)
            component_url = urljoin(base_url, link.get_attribute('href'))
            page.evaluate("window.__docsKitNavigation = 'preserved'")
            link.click()
            page.wait_for_url(component_url)
            expect(page.locator('article h1')).not_to_have_text(home_title)
            component_title = page.locator('article h1').inner_text()
            assert_level(page, 3)
            expect(page.locator('.page-status')).to_have_attribute('data-status', 'implemented')
            page.locator('article .lvl-1 a:not(.headerlink)').click()
            wait_home(page, base_url, home_title)
            assert_level(page, 3)
            assert page.evaluate('window.__docsKitNavigation') == 'preserved'
            result['checks'].append('Reload and instant navigation preserve depth; component status is available')

            choose(page, 1)
            stored = preference(page)
            page.goto(base_url + '#reader-details', wait_until='networkidle')
            expect(page.locator('#reader-details')).to_be_visible()
            assert_level(page, 3)
            assert preference(page) == stored
            page.locator("article .lvl-1 a[href*='components/build/']").click()
            page.wait_for_url(component_url)
            expect(page.locator('article h1')).to_have_text(component_title)
            assert_level(page, 1)
            page.go_back()
            page.wait_for_url(base_url + '#reader-details')
            expect(page.locator('#reader-details')).to_be_visible()
            assert_level(page, 3)
            page.go_forward()
            page.wait_for_url(component_url)
            expect(page.locator('article h1')).to_have_text(component_title)
            assert_level(page, 1)
            page.goto(component_url + '#_4', wait_until='networkidle')
            expect(page.locator('#component-details')).to_be_visible()
            assert_level(page, 3)
            result['checks'].append('Direct links and Back/Forward reveal targets without overwriting preference; old anchors still work')

            page.goto(base_url, wait_until='networkidle')
            choose(page, 1)
            page.evaluate("location.hash = 'reader-details'")
            expect(page.locator('#reader-details')).to_be_visible()
            assert_level(page, 3)
            page.go_back()
            page.wait_for_url(base_url)
            assert_level(page, 1)
            if page.evaluate("'onbeforematch' in document.documentElement"):
                page.locator('.lvl-3').dispatch_event('beforematch', {'bubbles': True})
                assert_level(page, 3)
                result['checks'].append('Hash changes and the browser beforematch event reveal hidden levels')
                result['limitations'].append('beforematch dispatched directly; browser Find UI was not automated')
            else:
                result['limitations'].append('beforematch is unsupported by this browser; native Find was not verified')

            check_search(page, base_url, 'Контент остаётся доступным', keyboard=True)
            check_search(page, base_url, 'JavaScript', keyboard=False)
            result['checks'].append('Russian and English site search open hidden details via keyboard and pointer')

            page.goto(base_url, wait_until='networkidle')
            choose(page, 2)
            page.wait_for_function('''() => window.__docsKitRoots.some(root =>
              root.host.isConnected && root.querySelector('a .node'))''')
            point = page.evaluate('''() => {
              const node = window.__docsKitRoots.filter(root => root.host.isConnected)
                .flatMap(root => [...root.querySelectorAll('a .node')])[0];
              node.scrollIntoView();
              const rect = node.getBoundingClientRect();
              if (rect.width <= 0 || rect.height <= 0) throw Error('Mermaid node is not visible');
              return {x: rect.x + rect.width / 2, y: rect.y + rect.height / 2};
            }''')
            page.screenshot(path=str(output / 'desktop-light.png'), full_page=True)
            page.mouse.click(**point)
            page.wait_for_url(component_url)
            expect(page.locator('article h1')).to_have_text(component_title)
            assert_level(page, 2)
            result['checks'].append('Mermaid SVG has a real working mouse link under the project URL prefix')

            page.goto(base_url, wait_until='networkidle')
            choose(page, 1)
            page.emulate_media(media='print')
            assert page.locator('.lvl').evaluate_all('''nodes => nodes.every(node => {
              const style = getComputedStyle(node);
              return style.display !== 'none' && style.visibility !== 'hidden' && style.contentVisibility !== 'hidden';
            })''')
            expect(page.locator('.level-control')).to_be_hidden()
            assert page.locator('article .reading-meta').count() == 3
            page.emulate_media(media='screen')
            assert_level(page, 1)
            result['checks'].append('Print includes all levels and static metrics while hiding interactive controls')

            system_dark = browser.new_context(color_scheme='dark')
            dark_page = system_dark.new_page()
            dark_page.goto(base_url, wait_until='networkidle')
            dark_page.wait_for_function("document.body.dataset.mdColorScheme === 'slate'")
            system_dark.close()
            page.emulate_media(color_scheme='light')
            page.reload(wait_until='networkidle')
            page.wait_for_function("document.body.dataset.mdColorScheme === 'default'")
            page.locator('label[for="__palette_1"]').click()
            page.wait_for_function("document.body.dataset.mdColorScheme === 'slate'")
            page.reload(wait_until='networkidle')
            page.wait_for_function("document.body.dataset.mdColorScheme === 'slate'")
            choose(page, 3)
            page.screenshot(path=str(output / 'desktop-dark.png'), full_page=True)
            for width in (390, 320):
                page.set_viewport_size({'width': width, 'height': 844})
                page.mouse.move(0, 0)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                slider(page).press('End')
                assert slider(page).evaluate('node => getComputedStyle(node).outlineStyle !== "none"')
                page.screenshot(path=str(output / f'mobile-{width}-dark.png'), full_page=True)
            result['checks'].append('System light/dark themes, explicit theme persistence, visible slider focus and 320/390px layout work')

            check_fallbacks(browser, base_url, result)
            for key in ('page_errors', 'console_errors', 'http_errors', 'failed_requests', 'external_requests'):
                assert not result[key], f'{key}: {result[key]}'
            result['checks'].append('No page, console, HTTP or network errors, missing assets or external asset requests')
            result['limitations'].append('No screen-reader session, real phone or human comprehension test was performed')
            result['status'] = 'passed'
        except Exception as error:
            result['status'] = 'failed'
            result['failure'] = str(error)
            page.screenshot(path=str(output / 'failure.png'), full_page=True)
            raise
        finally:
            (output / 'browser-results.json').write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            browser.close()


if __name__ == '__main__':
    main()
