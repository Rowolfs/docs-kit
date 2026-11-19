"""Create factual Quokki scaffolding without overwriting authored documentation."""

import argparse
from collections import defaultdict
from hashlib import sha256
import html
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

VERSION = "v0.3.0-alpha.1"
START = "<!-- quokki:instructions:start -->"
END = "<!-- quokki:instructions:end -->"
MANAGED = {"components.yaml", "docs-kit.toml", "AGENTS.md", ".gitignore"}


def git(project, *args):
    result = subprocess.run(["git", "-C", str(project), *args], capture_output=True, check=True)
    return result.stdout


def safe_target(project, relative):
    path = project / relative
    if not path.resolve().is_relative_to(project):
        raise ValueError(f"Target escapes project: {relative}")
    current = path
    while current != project:
        if current.is_symlink():
            raise ValueError(f"Symlink target is not supported: {relative}")
        if current != path and current.exists() and not current.is_dir():
            raise ValueError(f"Parent is not a directory: {relative}")
        current = current.parent
    if path.exists() and not path.is_file():
        raise ValueError(f"Target is not a file: {relative}")
    return path


def files(project):
    try:
        from .docs_model import list_files
    except ImportError:
        from docs_model import list_files
    return [name for name in list_files(project) if name not in MANAGED]


def markdown_text(value):
    value = html.escape(" ".join(value.splitlines()))
    return re.sub(r"([\\`*_{}\[\]()#+.!|])", r"\\\1", value)


def glob_literal(value):
    return "".join({"[": "[[]", "?": "[?]", "*": "[*]"}.get(char, char) for char in value)


def registry_for(names):
    groups = defaultdict(list)
    for name in names:
        path = Path(name)
        groups[path.parts[0] if len(path.parts) > 1 else ""].append(name)
    components = {}
    for group, paths in sorted(groups.items()):
        stem = re.sub(r"[^a-z0-9_-]+", "-", group.lower()).strip("-") if group else "root-files"
        stem = stem or "component"
        if not re.match(r"[a-z]", stem):
            stem = "component-" + stem
        digest = sha256(group.encode()).hexdigest()[:12]
        identifier = stem if len(stem) <= 64 else stem[:51].rstrip("-_") + "-" + digest
        attempt = 0
        while identifier in components:
            attempt += 1
            suffix = "-" + digest + (f"-{attempt}" if attempt > 1 else "")
            identifier = stem[:64 - len(suffix)].rstrip("-_") + suffix
        components[identifier] = {
            "title": group or "Файлы корня", "paths": [glob_literal(group) + "/**"] if group else [glob_literal(path) for path in paths],
            "depends_on": [], "page": f"docs/components/{identifier}.md",
        }
    return {"components": components}


def instructions(version):
    url = f"https://raw.githubusercontent.com/Rowolfs/docs-kit/{version}/install.sh"
    return f'''{START}
## Документация Quokki

Движок закреплён на `{version}`. Установщик создаёт структуру и заготовки,
а объяснения пишет агент после чтения кода. Он не определяет зависимости
между компонентами по именам файлов. Уточняй реестр `components.yaml` по коду.

Для запуска модели из корня репозитория:

```bash
bash <(wget -qO- {url}) --model changed --base HEAD
bash <(wget -qO- {url}) --model show <component-id>
```

После существенного изменения кода:

1. Определи затронутые компоненты (`changed`), прочитай их запись, страницу
   и diff. Перед push сравни с базовой веткой PR: `--base <base-ref>`; сравнение
   с `HEAD` показывает только незакоммиченные изменения. Для нужной базы
   предварительно получи её обычным `git fetch`.
2. Обнови только затронутые блоки Markdown. Страница компонента имеет три
   накопительных уровня `.lvl-1` / `.lvl-2` / `.lvl-3`: Кратко / Подробно /
   Полностью. Используй ссылки `[подпись](file:путь/к/файлу)`.
3. Описывай только проверенное по коду. Заготовки отмечены `planned` из-за
   отсутствия объяснений; после проверки укажи фактический статус компонента
   `implemented`, `planned` или `deprecated` и `verified_commit` — SHA
   проверенного коммита. Не представляй будущую реализацию как готовую.
4. Не копируй в Markdown генерируемые списки файлов и факты из модели.
   Модель `build/model/` генерируется и не коммитится.
5. Для существенного изменения добавь `docs/changelog/entries/<дата>-<slug>.md`:
   frontmatter `date`, `pr`, `components`, `c4_impact`; разделы Что, Зачем,
   Как работает, Затронуто, Ограничения, Что проверить, Ссылка на PR.
   Сборщик журнала ещё запланирован на фазу 5.
6. Запусти доступные проверки документации и существующие lint/test/build
   проекта: сначала найди команды в README, конфигурации и CI. Не выдумывай
   команды и не считай отсутствие проверок их успешным прохождением.
   `docs-check` пока не реализован (фаза 4); до его появления проверь ссылки,
   статусы, объяснения, Mermaid и отсутствие секретов вручную и собери сайт
   доступным workflow. Лимиты: кратко до 200 слов, подробно ориентир
   400–800, полностью до 1500; не растягивай текст ради нижней границы.
7. При ошибке останови отправку и исправь причину. Код и документация идут
   в одном PR. Commit/push выполняй после проверок в рамках разрешения
   пользователя; не делай force push. Сам установщик не коммитит и не пушит.
   После push GitHub Actions автоматически собирает сайт; публикация
   выполняется для `main` после настройки Pages как GitHub Actions.

`Docs-Impact: none — причина` — предусмотренное исключение будущих мягких
правил фазы 4, не способ пропустить существующие проверки проекта.
{END}
'''


def initial_files(project, registry, version):
    components = registry["components"]
    index = f'''---
id: project
type: project
status: planned
---
# {markdown_text(project.name)}

<div class="lvl lvl-1" markdown>

## Кратко

Описание пока не написано. Агенту нужно прочитать код и объяснить назначение,
основной сценарий и текущее состояние проекта.

[Карта кода](_generated/code-map.md) строится при сборке из реестра и модели.
[Архитектура](architecture/containers.md) требует объяснения по коду.

</div>

<div class="lvl lvl-2" markdown>

## Подробно

Описание пока не написано. Добавь проверенное объяснение взаимодействий.

</div>

<div class="lvl lvl-3" markdown>

## Полностью

Описание пока не написано. Добавь ограничения и ссылки на код.

</div>
'''
    result = {
        "components.yaml": "# Created by Quokki; edit the registry after reading the code.\n" + yaml.safe_dump(registry, allow_unicode=True, sort_keys=False),
        "docs-kit.toml": '[site]\nname = ' + json.dumps(project.name, ensure_ascii=False) + '\ndescription = "Документация проекта"\n',
        "docs/index.md": index,
        "docs/architecture/containers.md": '''---
id: structure
type: architecture
status: planned
---
# Архитектура проекта

Описание пока не написано. Агенту нужно проверить границы системы, окружение,
взаимодействия и ограничения по коду, затем написать объяснение и C4-схему.
Не считать верхние папки отдельными архитектурными контейнерами без проверки.

[Карта кода](../_generated/code-map.md) генерируется при сборке и не копируется
в этот документ. [Вернуться на главную](../index.md).
''',
        ".github/workflows/docs.yml": f'''name: Documentation

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: quokki-documentation
  cancel-in-progress: false

jobs:
  docs:
    uses: Rowolfs/docs-kit/.github/workflows/build.yml@{version}
    with:
      deploy: ${{{{ github.event_name != 'pull_request' && github.ref == 'refs/heads/main' }}}}
''',
    }
    for identifier, entry in components.items():
        result[entry["page"]] = f'''---
id: {identifier}
type: component
status: planned
---
# {markdown_text(entry["title"])}

<div class="lvl lvl-1" markdown>

## Кратко

Описание пока не написано. Прочитай код и объясни назначение и границы.
Статус заготовки не подтверждает состояние реализации компонента.

</div>

<div class="lvl lvl-2" markdown>

## Подробно

Описание пока не написано. Проверь основной поток и зависимости по коду.

</div>

<div class="lvl lvl-3" markdown>

## Полностью

Описание пока не написано. Добавь проверенные ограничения и ссылки на код.

</div>
'''
    return result


def install(project, engine_version=VERSION):
    project = Path(project).resolve()
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", engine_version):
        raise ValueError("engine-version must be a release tag")
    if Path(git(project, "rev-parse", "--show-toplevel").decode().strip()).resolve() != project:
        raise ValueError("Run the installer from the Git repository root")
    agents_path = safe_target(project, "AGENTS.md")
    existing_agents = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    if (existing_agents.count(START) != existing_agents.count(END) or existing_agents.count(START) > 1
            or START in existing_agents and existing_agents.index(START) > existing_agents.index(END)):
        raise ValueError("Malformed Quokki instruction markers in AGENTS.md")
    installed = START in existing_agents and (project / "components.yaml").is_file() and (project / "docs-kit.toml").is_file()
    plan = {} if installed else initial_files(project, registry_for(files(project)), engine_version)
    # Refuse all conflicts before changing any file, including workflow and pages.
    for name in plan:
        if safe_target(project, name).exists():
            raise ValueError(f"Existing file would be overwritten: {name}. No changes written.")
    for name in ("components.yaml", "docs-kit.toml"):
        safe_target(project, name)
    model = project / "build/model"
    for path in (project / "build", model):
        if path.is_symlink() or path.exists() and not path.is_dir():
            raise ValueError("build/model must be a real directory inside the project")
    if model.exists() and not (model / ".docs-kit-model").is_file():
        raise ValueError("Refusing an existing unrecognized build/model directory")
    if START not in existing_agents:
        plan["AGENTS.md"] = existing_agents.rstrip() + ("\n\n" if existing_agents else "") + instructions(engine_version)
    ignore_path = safe_target(project, ".gitignore")
    ignore = ignore_path.read_text(encoding="utf-8") if ignore_path.exists() else ""
    if "/build/model/" not in ignore.splitlines():
        plan[".gitignore"] = ignore + ("\n" if ignore and not ignore.endswith("\n") else "") + "/build/model/\n"
    originals = {}
    directories = set()
    try:
        for name, content in plan.items():
            target = safe_target(project, name)
            originals[name] = target.read_bytes() if target.exists() else None
            parent = target.parent
            while parent != project and not parent.exists():
                directories.add(parent)
                parent = parent.parent
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        try:
            from .docs_model import generate
        except ImportError:
            from docs_model import generate
        generate(project, model)
    except Exception:
        for name, original in originals.items():
            target = project / name
            if original is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(original)
        for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
        raise
    return sorted(plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--engine-version", default=VERSION)
    args = parser.parse_args()
    try:
        written = install(args.project_dir, args.engine_version)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Quokki: {error}\n")
    print("Quokki prepared: " + (", ".join(written) if written else "existing documentation preserved"))
    print("Model: build/model/index.json. Read AGENTS.md and write the missing explanations.")
    print("No commit or push performed. Configure Settings → Pages → GitHub Actions before deployment.")


if __name__ == "__main__":
    main()
