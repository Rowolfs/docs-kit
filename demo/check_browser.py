"""Smoke-test a built or published docs-kit site with a Markdown component link."""

import argparse
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import expect, sync_playwright


# Keep references to genuine closed roots without changing rendering or mode.
# This instrumentation is test-only; it is never copied into the site.
INSTRUMENT = """
window.__docsKitRoots = [];
const attach = Element.prototype.attachShadow;
Element.prototype.attachShadow = function(options) {
  const root = attach.call(this, options);
  window.__docsKitRoots.push(root);
  return root;
};
"""


def visible_levels(page):
    return page.locator("article .lvl").evaluate_all(
        "nodes => nodes.map(node => !node.hidden && getComputedStyle(node).display !== 'none')"
    )


def choose(page, level):
    button = page.locator(f'button[data-level="{level}"]')
    expect(button).to_be_visible()
    button.click()
    expect(button).to_have_attribute("aria-pressed", "true")
    assert visible_levels(page) == [depth <= level for depth in (1, 2, 3)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8766/docs-kit/")
    parser.add_argument("--browser", help="Chromium executable; omit for Playwright's browser")
    parser.add_argument("--output", default="build/phase1")
    args = parser.parse_args()
    base_url = args.url.rstrip("/") + "/"
    origin = urlsplit(base_url)[:2]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "url": base_url,
        "checks": [],
        "page_errors": [],
        "console_errors": [],
        "http_errors": [],
        "failed_requests": [],
        "external_requests": [],
    }

    with sync_playwright() as playwright:
        options = {"headless": True}
        if args.browser:
            options["executable_path"] = args.browser
        browser = playwright.chromium.launch(**options)
        result["browser"] = browser.version
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        context.add_init_script(INSTRUMENT)

        def watch_request(request):
            if urlsplit(request.url)[:2] != origin:
                result["external_requests"].append(request.url)

        context.on("request", watch_request)
        page = context.new_page()
        page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
        page.on("console", lambda message: result["console_errors"].append(message.text)
                if message.type == "error" else None)
        page.on("response", lambda response: result["http_errors"].append(
            f"HTTP {response.status} {response.url}") if response.status >= 400 else None)
        page.on("requestfailed", lambda request: result["failed_requests"].append(
            {"url": request.url, "failure": request.failure}))

        try:
            page.goto(base_url, wait_until="networkidle")
            expect(page.locator("article h1")).to_be_visible()
            home_title = page.locator("article h1").inner_text()
            expect(page.locator('button[data-level="1"]')).to_be_visible()
            assert visible_levels(page) == [True, False, False]
            result["checks"].append("Page and local assets load; default level is overview")

            for level in (2, 3, 1, 3):
                choose(page, level)
            page.reload(wait_until="networkidle")
            expect(page.locator('[data-level="3"]')).to_have_attribute("aria-pressed", "true")
            assert visible_levels(page) == [True, True, True]
            result["checks"].append("Levels are cumulative and survive reload")

            link = page.locator("article .lvl-1 a[href*='components/build/']")
            expect(link).to_have_count(1)
            component_url = link.get_attribute("href")
            component_url = urljoin(base_url, component_url)
            page.evaluate("window.__docsKitNavigation = 'preserved'")
            link.click()
            page.wait_for_url(component_url)
            expect(page.locator("article h1")).not_to_have_text(home_title)
            component_title = page.locator("article h1").inner_text()
            expect(page.locator('[data-level="3"]')).to_have_attribute("aria-pressed", "true")
            assert visible_levels(page) == [True, True, True]
            page.locator("article .lvl-1 a:not(.headerlink)").click()
            page.wait_for_url(base_url)
            expect(page.locator("article h1")).to_have_text(home_title)
            expect(page.locator('[data-level="3"]')).to_have_attribute("aria-pressed", "true")
            assert page.evaluate("window.__docsKitNavigation") == "preserved"
            result["checks"].append("Component navigation preserves level without a full reload")

            choose(page, 2)
            page.wait_for_function("""() => window.__docsKitRoots.some(root =>
              root.host.isConnected && root.querySelector('a .node'))""")
            point = page.evaluate("""() => {
              const node = window.__docsKitRoots.filter(root => root.host.isConnected)
                .flatMap(root => [...root.querySelectorAll('a .node')])[0];
              node.scrollIntoView();
              const rect = node.getBoundingClientRect();
              if (rect.width <= 0 || rect.height <= 0) throw Error('Mermaid node is not visible');
              return {x: rect.x + rect.width / 2, y: rect.y + rect.height / 2};
            }""")
            page.screenshot(path=str(output / "desktop-light.png"), full_page=True)
            page.mouse.click(**point)
            page.wait_for_url(component_url)
            expect(page.locator("article h1")).to_have_text(component_title)
            expect(page.locator('[data-level="2"]')).to_have_attribute("aria-pressed", "true")
            assert visible_levels(page) == [True, True, False]
            result["checks"].append("Mermaid renders SVG; actual mouse click opens component under site prefix")

            page.locator("article .lvl-1 a:not(.headerlink)").click()
            page.wait_for_url(base_url)
            expect(page.locator("article h1")).to_have_text(home_title)
            choose(page, 3)
            page.locator('label[for="__palette_1"]').click()
            page.wait_for_function("document.body.dataset.mdColorScheme === 'slate'")
            page.screenshot(path=str(output / "desktop-dark.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.mouse.move(0, 0)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.wait_for_timeout(400)  # Allow the theme's popover transition to finish.
            page.screenshot(path=str(output / "mobile-dark.png"), full_page=True)
            result["checks"].append("Dark theme and 390px viewport work without horizontal page overflow")

            for key in ("page_errors", "console_errors", "http_errors", "failed_requests", "external_requests"):
                assert not result[key], f"{key}: {result[key]}"
            result["checks"].append("No page/console/network errors, missing assets or external asset requests")
            result["status"] = "passed"
        except Exception as error:
            result["status"] = "failed"
            result["failure"] = str(error)
            page.screenshot(path=str(output / "failure.png"), full_page=True)
            raise
        finally:
            (output / "browser-results.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            browser.close()


if __name__ == "__main__":
    main()
