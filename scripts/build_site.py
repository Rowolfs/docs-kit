"""Build a thin project's documentation using this checkout of docs-kit."""

import argparse
import base64
from hashlib import sha256, sha512
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tarfile
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
CYTOSCAPE_VERSION = "3.35.0"
CYTOSCAPE_URL = "https://registry.npmjs.org/cytoscape/-/cytoscape-3.35.0.tgz"
CYTOSCAPE_INTEGRITY = "sMvBIXiGMnhkCaWz2R06FwF/27MNlS+Tqvi17foO9UhnUg3XGZccKjxsvEqQFAQYMSSZmN5SxYzUYlQ0DOJJ3g=="
# Published npm dist.integrity and independently pinned extracted browser assets.
CYTOSCAPE_FILES = {
    "cytoscape-3.35.0.min.js": ("package/dist/cytoscape.min.js", "71fa9ebec21a7ca2c40cff6aacc30d1f6464e363662ad4b2c197e1adc770cd94"),
    "cytoscape-3.35.0.LICENSE.txt": ("package/LICENSE", "eb319c6e6f233607f71e8e2f450391751883cfc0eeb3ca7ef574c13d1d9c2203"),
}
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


def cytoscape_assets(cache):
    """Verify the pinned npm archive; publish only its JS and required MIT notice."""
    targets = {name: cache / name for name in CYTOSCAPE_FILES}
    if all(path.is_file() and sha256(path.read_bytes()).hexdigest() == CYTOSCAPE_FILES[name][1]
           for name, path in targets.items()):
        return list(targets.values())
    with urlopen(CYTOSCAPE_URL, timeout=60) as response:
        archive = response.read()
    if base64.b64encode(sha512(archive).digest()).decode('ascii') != CYTOSCAPE_INTEGRITY:
        raise ValueError("Cytoscape archive checksum mismatch")
    verified = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as package:
            for name, (member_name, digest) in CYTOSCAPE_FILES.items():
                member = package.getmember(member_name)
                if not member.isfile():
                    raise ValueError("Cytoscape asset must be a regular file")
                data = package.extractfile(member).read()
                if sha256(data).hexdigest() != digest:
                    raise ValueError("Cytoscape asset checksum mismatch")
                verified[name] = data
    except (tarfile.TarError, KeyError) as error:
        raise ValueError("Invalid Cytoscape package") from error
    # Validate every member before replacing even one cached file. Never extract paths.
    cache.mkdir(parents=True, exist_ok=True)
    for name, data in verified.items():
        targets[name].write_bytes(data)
    return list(targets.values())


def revision(directory):
    result = subprocess.run(
        ["git", "-C", str(directory), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def stage_project(project, stage, site, site_url, asset, map_assets=None):
    shutil.copytree(project / "docs", stage / "docs")
    shutil.copytree(ENGINE / "theme/assets", stage / "docs/_docs_kit")
    shutil.copy2(asset, stage / "docs/_docs_kit/mermaid-12.3.0.min.js")
    shutil.copytree(ENGINE / "theme/overrides", stage / "overrides")
    model_context = None
    if (project / "components.yaml").is_file():
        if map_assets is None:
            raise ValueError("Component maps require verified Cytoscape assets")
        for map_asset in map_assets:
            shutil.copy2(map_asset, stage / "docs/_docs_kit" / map_asset.name)
        try:
            from .docs_model import generate, records_for
            from .model_site import render_map
        except ImportError:
            from docs_model import generate, records_for
            from model_site import render_map
        generated_docs = stage / "docs/_generated"
        if generated_docs.exists():
            raise ValueError("docs/_generated is reserved for generated model pages")
        manifest = generate(project, project / "build/model")
        registry, records, context = records_for(project)
        paths = {record['code']['path'] for record in records
                 if record.get('code') and record['kind'] == 'file'}
        model_context = (paths, context)
        generated_docs.mkdir()
        (generated_docs / "code-map.md").write_text(render_map(registry, records, context), encoding="utf-8")
        for relative in manifest['files']:
            target = stage / "docs/_docs_kit/model" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project / "build/model" / relative, target)
    # Only the renderer boundary uses Zensical's configuration format.
    import yaml

    asset_version = (ENGINE / "VERSION").read_text().strip()
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
        "extra_css": [f"_docs_kit/{name}?v={asset_version}"
                      for name in ("levels.css", "site.css")],
        "extra_javascript": [f"_docs_kit/levels.js?v={asset_version}"],
        "extra": {"quokki_map": bool(model_context)},
        "markdown_extensions": [
            "md_in_html", "attr_list", "tables", {"toc": {"permalink": True}},
            {"pymdownx.superfences": {"custom_fences": [{
                "name": "mermaid", "class": "mermaid",
                "format": "!!python/name:pymdownx.superfences.fence_code_format",
            }]}},
        ],
    }
    if model_context:
        config["extra_css"].append(f"_docs_kit/project-map.css?v={asset_version}")
        config["extra_javascript"].append(f"_docs_kit/project-map.js?v={asset_version}")
    if "nav" in site:
        config["nav"] = list(site["nav"])
        if model_context:
            config["nav"].append({"Карта кода": "_generated/code-map.md"})
    # Zensical's mkdocs-compatible YAML expects a callable tag, not a quoted string.
    encoded = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    encoded = encoded.replace("'!!python/name:pymdownx.superfences.fence_code_format'",
                              "!!python/name:pymdownx.superfences.fence_code_format")
    (stage / "mkdocs.yml").write_text(encoded, encoding="utf-8")
    return model_context


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
    map_assets = cytoscape_assets(cache) if (project / "components.yaml").is_file() else None
    with tempfile.TemporaryDirectory(prefix="docs-kit-") as temp:
        stage = Path(temp)
        model_context = stage_project(project, stage, site, site_url, asset, map_assets)
        subprocess.run(
            [sys.executable, "-m", "zensical", "build", "--strict", "-f", str(stage / "mkdocs.yml")],
            cwd=stage, check=True,
        )
        generated = stage / "site"
        speed = site.get("reading_words_per_minute", DEFAULT_WORDS_PER_MINUTE)
        for page in generated.rglob("*.html"):
            source = page.read_text(encoding="utf-8")
            if model_context:
                try:
                    from .model_site import resolve_links
                except ImportError:
                    from model_site import resolve_links
                source = resolve_links(source, *model_context)
            page.write_text(annotate_html(source, speed), encoding="utf-8")
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
