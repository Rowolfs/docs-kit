"""Browser acceptance checks for the phase 0 probe; requires a running static server."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


# Preserve the real closed ShadowRoot without changing its mode or rendering.
INSTRUMENT = """
window.__probeRoots = [];
const attach = Element.prototype.attachShadow;
Element.prototype.attachShadow = function(options) {
  const root = attach.call(this, options);
  window.__probeRoots.push(root);
  return root;
};
window.__probeWrites = 0;
const set = Storage.prototype.setItem;
Storage.prototype.setItem = function(key, value) {
  if (key === 'docs-kit:phase0:level') window.__probeWrites++;
  return set.call(this, key, value);
};
"""


def visible(page):
    return page.locator(".lvl").evaluate_all("nodes => nodes.map(n => !n.hidden)")


def choose(page, level):
    page.locator(f'button[data-level="{level}"]').click()
    assert visible(page) == [n <= level for n in (1, 2, 3)]
    assert page.locator('button[aria-pressed="true"]').count() == 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765/docs-kit/")
    parser.add_argument("--browser", default="/usr/bin/chromium-browser")
    args = parser.parse_args()
    output = Path("build/phase0")
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, external = [], [], []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=args.browser, headless=True, args=["--no-sandbox"]
        )
        context = browser.new_context()

        def local_only(route):
            if route.request.url.startswith(args.base_url):
                route.continue_()
            else:
                external.append(route.request.url)
                route.abort()

        context.route("**/*", local_only)
        context.add_init_script(INSTRUMENT)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: errors.append(f"HTTP {response.status} {response.url}")
                if response.status >= 400 else None)
        page.goto(args.base_url)
        page.wait_for_function("document.querySelector('.level-control')?.hidden === false")
        assert page.locator(".lvl-1 strong").inner_text().startswith("Markdown")
        assert page.locator(".lvl-1 li").count() == 2
        assert [text.strip() for text in page.locator(".lvl-3 code").all_text_contents()] == [
            'markdown="block"', 'print("phase 0")'
        ]
        assert visible(page) == [True, False, False]
        checks.append("Markdown inside bare markdown, markdown=1, markdown=block")

        for level in (2, 3, 1, 3):
            choose(page, level)
        page.reload()
        page.wait_for_function("document.querySelector('[data-level=\"3\"]')?.getAttribute('aria-pressed') === 'true'")
        assert visible(page) == [True, True, True]
        checks.append("Cumulative levels 1/2/3; selection survives reload")

        page.evaluate("window.__instantSentinel = 'preserved'")
        for _ in range(2):
            page.locator(".lvl-1 a:not(.headerlink)").click()
            page.wait_for_url(args.base_url + "components/probe/")
            expect(page.locator("article h1")).to_contain_text("Компонент эксперимента")
            expect(page.locator('[data-level="3"]')).to_have_attribute("aria-pressed", "true")
            assert visible(page) == [True, True, True]
            page.locator(".lvl-1 a:not(.headerlink)").click()
            page.wait_for_url(args.base_url)
            expect(page.locator("article h1")).to_contain_text("Эксперимент фазы 0")
            assert page.evaluate("window.__instantSentinel") == "preserved"
        writes = page.evaluate("window.__probeWrites")
        choose(page, 2)
        assert page.evaluate("window.__probeWrites") == writes + 1
        checks.append("Instant navigation preserves selection and window; no duplicate click handlers")

        page.wait_for_function("window.__probeRoots.some(root => root.host.isConnected && root.querySelector('a .node'))")
        assert page.evaluate("window.mermaid.mermaidAPI.getConfig().securityLevel") == "strict"
        point = page.evaluate("""() => {
          const node = window.__probeRoots.filter(r => r.host.isConnected)
            .flatMap(r => [...r.querySelectorAll('a .node')])[0];
          node.scrollIntoView();
          const rect = node.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) throw Error('Diagram has no visible size');
          return {x: rect.x + rect.width / 2, y: rect.y + rect.height / 2};
        }""")
        page.screenshot(path=str(output / "desktop-light.png"), full_page=True)
        page.mouse.click(**point)
        page.wait_for_url(args.base_url + "components/probe/")
        expect(page.locator("article h1")).to_contain_text("Компонент эксперимента")
        expect(page.locator('[data-level="2"]')).to_have_attribute("aria-pressed", "true")
        assert visible(page) == [True, True, False]
        checks.append("Mermaid SVG, actual mouse click under /docs-kit/, strict security level")

        page.locator(".lvl-1 a:not(.headerlink)").click()
        page.wait_for_url(args.base_url)
        expect(page.locator("article h1")).to_contain_text("Эксперимент фазы 0")
        page.locator('[data-level="3"]').focus()
        page.keyboard.press("Enter")
        assert visible(page) == [True, True, True]
        checks.append("Level button keyboard activation")

        page.locator('label[for="__palette_1"]').click()
        page.wait_for_function("document.body.dataset.mdColorScheme === 'slate'")
        page.screenshot(path=str(output / "desktop-dark.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.mouse.move(0, 0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.wait_for_timeout(400)  # Let the theme's hover popover fade before the screenshot.
        page.screenshot(path=str(output / "mobile-dark.png"), full_page=True)
        checks.append("Light/dark palette toggle; 390px viewport has no page overflow")

        page.goto(args.base_url + "report/")
        expect(page.locator("article h1")).to_contain_text("Фаза 0")
        choose(page, 3)
        assert page.locator("article table").count() == 1
        assert "Фаза 0 завершена" in page.locator(".lvl-1").inner_text()
        checks.append("Phase report builds as a navigable page with three levels and a table")

        no_storage = browser.new_context()
        no_storage.add_init_script("""
          for (const name of ['getItem', 'setItem']) {
            const original = Storage.prototype[name];
            Storage.prototype[name] = function(key, ...values) {
              if (key === 'docs-kit:phase0:level') throw new DOMException('Disabled', 'SecurityError');
              return original.call(this, key, ...values);
            };
          }
        """)
        limited = no_storage.new_page()
        limited.on("pageerror", lambda error: errors.append(str(error)))
        limited.goto(args.base_url)
        limited.wait_for_function("document.querySelector('.level-control')?.hidden === false")
        assert visible(limited) == [True, False, False]
        choose(limited, 3)
        checks.append("Level storage denied: controls still work")
        no_storage.close()

        no_js = browser.new_context(java_script_enabled=False)
        plain = no_js.new_page()
        plain.goto(args.base_url)
        assert visible(plain) == [True, True, True]
        assert plain.locator(".level-control").is_hidden()
        assert "flowchart LR" in plain.locator("pre.mermaid").inner_text()
        checks.append("JavaScript disabled: all text and Mermaid source remain readable")
        no_js.close()
        assert not errors, errors
        assert not external, external
        checks.append("Main browser context: no page errors, HTTP errors or external requests")
        result = {"browser": browser.version, "base_url": args.base_url, "checks": checks,
                  "errors": errors, "external_requests": external}
        (output / "browser-results.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
