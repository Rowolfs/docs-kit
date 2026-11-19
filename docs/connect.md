---
id: connect
type: guide
status: implemented
---
# Подключение проекта

## Установка одной командой

Из корня Git-репозитория:

```bash
bash <(wget -qO- https://raw.githubusercontent.com/Rowolfs/docs-kit/v0.3.0-alpha.1/install.sh)
```

Требуются Bash, Git и Python 3.11+ с venv. Установщик скачивает точную версию
движка и PyYAML во временное окружение; не добавляет движок в исходники проекта.
Он создаёт реестр, конфиг, заготовки страниц и workflow, дополняет `AGENTS.md`.
Если существующий файл конфликтует с заготовкой, установка завершается без
перезаписи. Повторный запуск установленного проекта сохраняет написанный текст.

Затем агент читает код, заполняет заготовки, уточняет реестр, запускает доступные
проверки и отправляет код с документацией. Установщик не запускает ИИ и не пушит.
В Settings → Pages нужно выбрать **GitHub Actions**; workflow публикует `main`.
`docs-check` пока не реализован — до фазы 4 инструкции требуют ручной проверки
документации и существующих проверок кода проекта.

Команды модели доступны через тот же закреплённый загрузчик:

```bash
bash <(wget -qO- https://raw.githubusercontent.com/Rowolfs/docs-kit/v0.3.0-alpha.1/install.sh) --model changed --base HEAD
bash <(wget -qO- https://raw.githubusercontent.com/Rowolfs/docs-kit/v0.3.0-alpha.1/install.sh) --model show <component-id>
```

Каждый вызов требует сети. `HEAD` показывает незакоммиченные изменения; для PR
нужно передать базовую ревизию, предварительно получив её через Git.

Ниже — ручной вариант подключения. Готовый template repo остаётся в фазе 7;
базовые правила агента и установщик перенесены в фазу 3.

## Содержание проекта

```text
docs-kit.toml
components.yaml
docs/index.md
docs/components/...
.github/workflows/docs.yml
```

`docs-kit.toml`:

```toml
[site]
name = "Название проекта"
description = "Короткое описание"
nav = [
  { "Главная" = "index.md" },
]
# Необязательно: расчётная скорость для оценки времени чтения
reading_words_per_minute = 200
```

`reading_words_per_minute` — необязательное целое число от 40 до 1000;
значение по умолчанию — 200. Это грубая оценка для интерфейса, не измерение
скорости читателя. Счётчик строится по отрендеренному тексту уровней.

Страницы — обычный Markdown. Необязательные уровни используют
`<div class="lvl lvl-1" markdown>...</div>` и аналогичные lvl-2/lvl-3.
Скрипты и тему в проект копировать не нужно.

## Вызов опубликованного движка

В Settings → Pages выбрать **GitHub Actions** как источник публикации.
Затем добавить `.github/workflows/docs.yml`:

```yaml
name: Documentation
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
  group: documentation
  cancel-in-progress: false

jobs:
  docs:
    uses: Rowolfs/docs-kit/.github/workflows/build.yml@v0.3.0-alpha.1
    with:
      deploy: ${{ github.event_name != 'pull_request' && github.ref == 'refs/heads/main' }}
```

Это экспериментальный prerelease `v0.3.0-alpha.1`, не стабильный `v1`. Для максимальной
фиксации вместо тега можно указать полный SHA. Существующие релизные теги
не передвигаются; изменение движка публикуется новой версией. Semver до 1.0
не означает стабильность всего будущего интерфейса.

Для проекта в подкаталоге передать `project-directory`. Для нестандартного
адреса — `site-url`. Обычный Pages URL определяется автоматически. PR получает
сборку и артефакт, но не публикацию. Reusable workflow сам не включает Pages
и не требует PAT; публикация использует стандартный `GITHUB_TOKEN`.

Поддерживается GitHub.com; GitHub Enterprise Server пока не поддерживается.
Сборка не выполняет проверки содержания будущего docs-check.
