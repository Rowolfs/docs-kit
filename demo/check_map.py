"""Exercise the generated Cytoscape map with real mouse and keyboard input."""

import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlencode, urljoin, urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = '[data-project-map]'


def ready(page, node=None):
    root = page.locator(ROOT)
    expect(root).to_have_count(1)
    expect(root).to_have_attribute('data-map-state', 'ready', timeout=15000)
    if node:
        expect(root).to_have_attribute('data-current-node', node)
    return root


def click_node(page, node):
    """Click the real canvas at Cytoscape's rendered node position."""
    root = ready(page)
    canvas = root.locator('.project-map__canvas')
    canvas.scroll_into_view_if_needed()
    point = root.evaluate('''(root, id) => {
      const cy = root.__quokkiMap.cy;
      const node = cy.getElementById(id);
      if (node.length !== 1 || !node.isNode()) throw Error('Missing graph node: ' + id);
      const position = node.renderedPosition();
      const bounds = cy.container().getBoundingClientRect();
      if (position.x < 0 || position.x > bounds.width || position.y < 0 || position.y > bounds.height)
        throw Error('Graph node outside canvas: ' + id);
      return {x: bounds.x + position.x, y: bounds.y + position.y};
    }''', node)
    page.mouse.click(**point)
    ready(page, node)


def load_records(request, model_url, path):
    records, seen = [], set()
    while path:
        url = urljoin(model_url, path)
        assert url.startswith(model_url) and url not in seen, url
        seen.add(url)
        response = request.get(url)
        assert response.ok, f'{response.status}: {url}'
        assert len(response.body()) <= 30 * 1024, url
        data = response.json()
        records.extend(data['records'])
        path = data.get('next')
    return records


def choose_path(request, base_url):
    """Select actual modeled files; never assume a particular project language."""
    model_url = urljoin(base_url, '_docs_kit/model/')
    index = load_records(request, model_url, 'index.json')
    components = [item for item in index if item['kind'] == 'component']
    for component in components:
        pointers = [item for item in index if item['kind'] == 'model-file' and item['parent'] == component['id']]
        records = []
        for pointer in pointers:
            records.extend(load_records(request, model_url, pointer['model_file']))
        for folder in records:
            if folder['kind'] != 'directory' or folder['parent'] != component['id']:
                continue
            files = [item for item in records if item['kind'] == 'file' and item['parent'] == folder['id']]
            if files:
                return index, component, folder, next((item for item in files if item['code'].get('url')), files[0])
    raise AssertionError('Demo must have a component with a real folder and file to test drilldown')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', '--url', dest='base_url', default='http://127.0.0.1:8766/docs-kit/')
    parser.add_argument('--browser', help="Chromium executable; omit for Playwright's browser")
    parser.add_argument('--output', default='build/phase2/map')
    args = parser.parse_args()
    base_url = args.base_url.rstrip('/') + '/'
    map_url = urljoin(base_url, '_generated/code-map/')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    result = {'url': map_url, 'checks': [], 'errors': [], 'limitations': [
        'No screen-reader session or physical touch device was tested.',
        'Large repository performance is not measured by this browser smoke test.',
    ]}

    with sync_playwright() as playwright:
        options = {'headless': True}
        if args.browser:
            options['executable_path'] = args.browser
        browser = playwright.chromium.launch(**options)
        result['browser'] = browser.version
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, color_scheme='light')
        index, component, folder, file = choose_path(context.request, base_url)
        page = context.new_page()
        page.on('pageerror', lambda error: result['errors'].append(str(error)))
        page.on('requestfailed', lambda request: result['errors'].append(f'Request failed: {request.url}: {request.failure}'))
        page.on('console', lambda message: result['errors'].append(message.text) if message.type == 'error' else None)
        context.on('request', lambda request: result['errors'].append('External asset: ' + request.url)
                   if urlsplit(request.url)[:2] != urlsplit(base_url)[:2] else None)
        page.on('response', lambda response: result['errors'].append(f'HTTP {response.status}: {response.url}')
                if response.status >= 400 else None)
        try:
            page.goto(map_url, wait_until='networkidle')
            root = ready(page, 'project')
            assert page.evaluate('cytoscape.version') == '3.35.0'
            expect(page.locator('script[src*="cytoscape-3.35.0.min.js"]')).to_have_count(1)
            assert root.evaluate('root => !root.closest(".lvl")'), 'Map must remain usable at every reading depth'
            expected_edges = sum(len(item.get('depends_on', [])) for item in index if item['kind'] == 'component')
            assert root.evaluate('root => root.__quokkiMap.cy.edges().length') == expected_edges
            assert not page.evaluate("performance.getEntriesByType('resource').some(item => item.name.includes('/model/components/'))"), 'Component shards must be lazy-loaded'
            page.screenshot(path=str(output / 'root-light.png'), full_page=True)
            click_node(page, component['id'])
            expect(root.locator('.project-map__detail a')).not_to_have_count(0)
            assert page.evaluate("performance.getEntriesByType('resource').some(item => item.name.includes('/model/components/'))"), 'Opening component must load its model shard'
            click_node(page, folder['id'])
            folder_url = page.url
            click_node(page, file['id'])
            expect(root.locator('.project-map__path')).to_have_text(file['code']['path'])
            expect(root.locator('.project-map__links a', has_text='Документация')).to_have_count(1)
            source_url = file['code'].get('url')
            code_link = root.get_by_role('link', name='Открыть код на GitHub')
            if source_url:
                assert re.match(r'^https://github\.com/[^/]+/[^/]+/blob/[0-9a-f]{40}/.+', source_url), source_url
                expect(code_link).to_have_attribute('href', source_url)
            else:
                expect(code_link).to_have_count(0)
            deep_url = page.url
            assert 'map=' in urlsplit(deep_url).fragment and 'component=' in urlsplit(deep_url).fragment
            result['checks'].append('Real canvas clicks traverse component → folder → file; file and component links match generated model')

            page.reload(wait_until='networkidle')
            ready(page, file['id'])
            page.go_back()
            ready(page, folder['id'])
            assert page.url == folder_url
            page.go_forward()
            ready(page, file['id'])
            root.get_by_role('button', name='← Назад', exact=True).click()
            ready(page, folder['id'])
            root.locator('.project-map__breadcrumbs').get_by_role('button', name='Проект', exact=True).click()
            ready(page, 'project')
            result['checks'].append('Deep URL reload, browser Back/Forward, map Back and breadcrumbs preserve hierarchy')

            # Equivalent native controls must support keyboard-only navigation.
            component_button = root.locator('.project-map__list').get_by_role('button', name=component.get('title', component['id']), exact=False)
            component_button.focus()
            component_button.press('Enter')
            ready(page, component['id'])
            current_crumb = root.locator('.project-map__breadcrumbs [aria-current="location"]')
            expect(current_crumb).to_have_count(1)
            expect(current_crumb).to_be_focused()
            result['checks'].append('Native accessible list supports keyboard activation and current breadcrumb semantics')

            root.get_by_role('button', name='Увеличить карту', exact=True).click()
            zoom = root.evaluate('root => root.__quokkiMap.cy.zoom()')
            root.get_by_role('button', name='Уменьшить карту', exact=True).click()
            assert root.evaluate('root => root.__quokkiMap.cy.zoom()') < zoom
            root.get_by_role('button', name='Вместить', exact=True).click()
            light_color = root.evaluate('root => root.__quokkiMap.cy.nodes()[0].style("color")')
            page.locator('label[for="__palette_1"]').click()
            page.wait_for_function("document.body.dataset.mdColorScheme === 'slate'")
            page.wait_for_function('''light => document.querySelector('[data-project-map]').__quokkiMap.cy.nodes()[0].style('color') !== light''', arg=light_color)
            ready(page, component['id'])
            page.screenshot(path=str(output / 'component-dark.png'), full_page=True)
            for width in (390, 320):
                page.set_viewport_size({'width': width, 'height': 844})
                ready(page, component['id'])
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Page overflow at {width}px'
                page.wait_for_function('''() => {
                  const cy = document.querySelector('[data-project-map]').__quokkiMap.cy;
                  const bounds = cy.elements().renderedBoundingBox();
                  const canvas = cy.container().getBoundingClientRect();
                  return bounds.x1 >= -1 && bounds.y1 >= -1 && bounds.x2 <= canvas.width + 1 && bounds.y2 <= canvas.height + 1;
                }''')
                assert root.evaluate('''root => {
                  const cy = root.__quokkiMap.cy;
                  return cy.nodes().length > 4 || cy.nodes().every(node => node.numericStyle('font-size') * cy.zoom() >= 8);
                }'''), f'Small map labels become unreadable at {width}px'
                page.screenshot(path=str(output / f'mobile-{width}.png'), full_page=True)
            mobile_context = browser.new_context(viewport={'width': 320, 'height': 844}, color_scheme='dark')
            mobile = mobile_context.new_page()
            mobile.on('pageerror', lambda error: result['errors'].append(str(error)))
            mobile.goto(map_url + '#' + urlencode({'map': component['id']}), wait_until='networkidle')
            mobile_root = ready(mobile, component['id'])
            assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert mobile_root.evaluate('''root => {
              const cy = root.__quokkiMap.cy;
              return cy.nodes().length > 4 || cy.nodes().every(node => node.renderedWidth() > 70 && node.numericStyle('font-size') * cy.zoom() >= 8);
            }'''), 'Small map must be readable when initially opened on a 320px screen'
            mobile.screenshot(path=str(output / 'mobile-first-320.png'), full_page=True)
            mobile_context.close()
            page.set_viewport_size({'width': 1440, 'height': 1000})
            result['checks'].append('Zoom, fit, theme change and 320/390px layout preserve usable map state')

            # Click a real documentation link to exercise instant navigation teardown/remount.
            page.evaluate("window.__mapNavigationSentinel = 'same-document'")
            root.locator('.project-map__links').get_by_role('link', name='Документация компонента', exact=True).click()
            expect(page.locator(ROOT)).to_have_count(0)
            expect(page.locator('article h1')).to_be_visible()
            assert page.evaluate('window.__mapNavigationSentinel') == 'same-document'
            page.go_back()
            ready(page, component['id'])
            assert page.evaluate('window.__mapNavigationSentinel') == 'same-document'
            assert page.locator('.project-map__toolbar').count() == 1
            result['checks'].append('Instant navigation destroys and remounts one map without reloading the document')

            page.emulate_media(media='print')
            expect(root).to_be_hidden()
            assert page.locator('article .lvl').evaluate_all('nodes => nodes.every(node => getComputedStyle(node).display !== "none")')
            page.emulate_media(media='screen')
            result['checks'].append('Print hides interactive canvas and retains the complete static map')

            no_js = browser.new_context(java_script_enabled=False)
            fallback = no_js.new_page()
            fallback.goto(map_url, wait_until='networkidle')
            assert fallback.locator('article table').count() >= 2
            assert fallback.locator('article .lvl').evaluate_all('nodes => nodes.every(node => getComputedStyle(node).display !== "none")')
            assert fallback.locator('article a[href*="/blob/"]').count() > 0
            no_js.close()
            result['checks'].append('Without JavaScript static component and file tables remain available')
            broken_context = browser.new_context()
            broken_context.route('**/_docs_kit/model/index.json', lambda route: route.fulfill(
                status=200, content_type='application/json', body='{"schema_version":1,"records":"invalid"}'))
            broken = broken_context.new_page()
            broken.on('pageerror', lambda error: result['errors'].append(str(error)))
            broken.goto(map_url, wait_until='networkidle')
            expect(broken.locator(ROOT)).to_have_attribute('data-map-state', 'error')
            expect(broken.locator(ROOT).get_by_role('status')).to_contain_text('формат')
            expect(broken.locator('article .lvl-1')).to_be_visible()
            broken_context.close()
            result['checks'].append('Malformed JSON model shows an accessible error and leaves static documentation readable')

            missing_context = browser.new_context()
            missing_context.route('**/cytoscape-3.35.0.min.js', lambda route: route.fulfill(
                status=200, content_type='application/javascript', body='/* unavailable vendor */'))
            missing = missing_context.new_page()
            missing.on('pageerror', lambda error: result['errors'].append(str(error)))
            missing.goto(map_url, wait_until='networkidle')
            missing_root = missing.locator(ROOT)
            expect(missing_root).to_have_attribute('data-map-state', 'error')
            missing_root.locator('.project-map__list').get_by_role('button', name=component.get('title', component['id']), exact=False).click()
            expect(missing_root).to_have_attribute('data-current-node', component['id'])
            expect(missing_root.get_by_role('status')).to_contain_text('навигация списком доступна')
            expect(missing.locator('article .lvl-1')).to_be_visible()
            missing_context.close()
            result['checks'].append('Missing graphical library preserves native component navigation and static fallback')

            page.goto(map_url + '#map=component%3Anot-a-real-component', wait_until='networkidle')
            expect(page.locator(ROOT)).to_have_attribute('data-map-state', 'error')
            expect(page.locator(ROOT)).to_have_attribute('data-current-node', 'project')
            expect(page.locator(ROOT).get_by_role('status')).to_contain_text('не найден')
            expect(page.locator('article .lvl-1')).to_be_visible()
            result['checks'].append('Unknown deep link reports an accessible error and restores root navigation with static fallback')
            assert not result['errors'], result['errors']
            result['status'] = 'passed'
        except Exception as error:
            result['status'] = 'failed'
            result['failure'] = str(error)
            page.screenshot(path=str(output / 'failure.png'), full_page=True)
            raise
        finally:
            (output / 'browser-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False, indent=2))
            browser.close()


if __name__ == '__main__':
    main()
