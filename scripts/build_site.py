"""Build a thin project's documentation using this checkout of docs-kit."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import urlparse
from urllib.request import urlopen

try:
    from .reading import DEFAULT_WORDS_PER_MINUTE, annotate_html, validate_speed
except ImportError:  # Direct invocation: python scripts/build_site.py
    from reading import DEFAULT_WORDS_PER_MINUTE, annotate_html, validate_speed

ENGINE = Path(__file__).resolve().parents[1]
MERMAID_URL = "https://unpkg.com/mermaid@12.3.0/dist/mermaid.min.js"
MERMAID_SHA256 = "336df803d87a38b70a01e736e666c8f7601d2ce42f5e47c8fafe5d721074b9a3"
MANIFEST = "_docs_kit/build.json"


def load_config(project):
    with (project / "docs-kit.toml").open("rb") as handle:
        config = tomllib.load(handle)
    if set(config) != {"site"} or not isinstance(config["site"], dict):
        raise ValueError("docs-kit.toml must contain a [site] table")
    site = config["site"]
    if set(site) - {"name", "description", "nav", "reading_words_per_minute"}:
        raise ValueError("Unknown site option; supported: name, description, nav, reading_words_per_minute")
    if not isinstance(site.get("name"), str) or not site["name"].strip():
        raise ValueError("site.name must be a nonempty string")
    if "description" in site and not isinstance(site["description"], str):
        raise ValueError("site.description must be a string")
    validate_speed(site.get("reading_words_per_minute", DEFAULT_WORDS_PER_MINUTE))
    nav = site.get("nav")
    if nav is not None:
        if not isinstance(nav, list) or not nav:
            raise ValueError("site.nav must be a nonempty list")
        for item in nav:
            if not isinstance(item, dict) or len(item) != 1:
                raise ValueError("Each nav entry must map one title to one Markdown path")
            title, path = next(iter(item.items()))
            if not isinstance(title, str) or not isinstance(path, str):
                raise ValueError("Navigation titles and paths must be strings")
            target = (project / "docs" / path).resolve()
            if not target.is_relative_to((project / "docs").resolve()) or target.suffix != ".md":
                raise ValueError("Navigation must point to Markdown within docs/")
            if not target.is_file():
                raise ValueError(f"Navigation file does not exist: {path}")
    docs = project / "docs"
    if not (docs / "index.md").is_file():
        raise ValueError("Project must contain docs/index.md")
    if docs.is_symlink() or any(path.is_symlink() for path in docs.rglob("*")):
        raise ValueError("Symlinks in docs/ are not supported")
    if (docs / "_docs_kit").exists():
        raise ValueError("docs/_docs_kit is reserved for generated engine assets")
    return site


def mermaid_asset(cache):
    target = cache / "mermaid-12.3.0.min.js"
    if target.exists():
        data = target.read_bytes()
        if sha256(data).hexdigest() == MERMAID_SHA256:
            return target
    with urlopen(MERMAID_URL, timeout=60) as response:
        data = response.read()
    if sha256(data).hexdigest() != MERMAID_SHA256:
        raise ValueError("Mermaid checksum mismatch")
    cache.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def revision(directory):
    result = subprocess.run(
        ["git", "-C", str(directory), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def stage_project(project, stage, site, site_url, asset):
    shutil.copytree(project / "docs", stage / "docs")
    shutil.copytree(ENGINE / "theme/assets", stage / "docs/_docs_kit")
    shutil.copy2(asset, stage / "docs/_docs_kit/mermaid-12.3.0.min.js")
    shutil.copytree(ENGINE / "theme/overrides", stage / "overrides")
    # Only the renderer boundary uses Zensical's configuration format.
    import yaml

    config = {
        "site_name": site["name"], "site_description": site.get("description", ""),
        "site_url": site_url, "docs_dir": "docs", "site_dir": "site",
        "theme": {
            "name": "material", "custom_dir": "overrides", "language": "ru", "font": False,
            "features": ["navigation.instant", "search.highlight"],
            "palette": [
                {"scheme": "default", "media": "(prefers-color-scheme: light)",
                 "toggle": {"icon": "lucide/moon", "name": "Тёмная тема"}},
                {"scheme": "slate", "media": "(prefers-color-scheme: dark)",
                 "toggle": {"icon": "lucide/sun", "name": "Светлая тема"}},
            ],
        },
        "extra_css": ["_docs_kit/levels.css", "_docs_kit/site.css"],
        "extra_javascript": ["_docs_kit/levels.js"],
        "markdown_extensions": [
            "md_in_html", "attr_list", "tables", {"toc": {"permalink": True}},
            {"pymdownx.superfences": {"custom_fences": [{
                "name": "mermaid", "class": "mermaid",
                "format": "!!python/name:pymdownx.superfences.fence_code_format",
            }]}},
        ],
    }
    if "nav" in site:
        config["nav"] = site["nav"]
    # Zensical's mkdocs-compatible YAML expects a callable tag, not a quoted string.
    encoded = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    encoded = encoded.replace("'!!python/name:pymdownx.superfences.fence_code_format'",
                              "!!python/name:pymdownx.superfences.fence_code_format")
    (stage / "mkdocs.yml").write_text(encoded, encoding="utf-8")


def build(project, output, site_url, cache):
    project, output = project.resolve(), output.resolve()
    site = load_config(project)
    url = urlparse(site_url)
    if url.scheme not in {"http", "https"} or not url.netloc or not site_url.endswith("/"):
        raise ValueError("site-url must be an absolute HTTP(S) URL ending with /")
    if url.username or url.password or url.query or url.fragment:
        raise ValueError("site-url must not contain credentials, a query or a fragment")
    docs = (project / "docs").resolve()
    if (output == project or output in project.parents or output == ENGINE
            or output in ENGINE.parents or output.is_relative_to(docs)):
        raise ValueError("Output must not overwrite the project, engine or authored documentation")
    if output.exists() and not (output / MANIFEST).is_file():
        raise ValueError("Refusing to replace an output directory not created by docs-kit")
    asset = mermaid_asset(cache)
    with tempfile.TemporaryDirectory(prefix="docs-kit-") as temp:
        stage = Path(temp)
        stage_project(project, stage, site, site_url, asset)
        subprocess.run(
            [sys.executable, "-m", "zensical", "build", "--strict", "-f", str(stage / "mkdocs.yml")],
            cwd=stage, check=True,
        )
        generated = stage / "site"
        speed = site.get("reading_words_per_minute", DEFAULT_WORDS_PER_MINUTE)
        for page in generated.rglob("*.html"):
            page.write_text(annotate_html(page.read_text(encoding="utf-8"), speed), encoding="utf-8")
        (generated / ".nojekyll").touch()
        provenance = {
            "engine_version": (ENGINE / "VERSION").read_text().strip(),
            "engine_revision": revision(ENGINE), "source_revision": revision(project),
            "site_url": site_url,
        }
        (generated / MANIFEST).write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if output.exists():
            shutil.rmtree(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(generated, output)
    print(f"Built {site['name']}: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--site-url", required=True)
    parser.add_argument("--cache-dir", type=Path, default=ENGINE / ".cache/docs-kit")
    args = parser.parse_args()
    try:
        build(args.project_dir, args.output_dir, args.site_url, args.cache_dir)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"docs-kit: {error}\n")


if __name__ == "__main__":
    main()
