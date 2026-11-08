# Quokki

Quokki — статическая документация для проектов, написанных ИИ-агентами.
`docs-kit` — имя движка и GitHub-репозитория.

**[Открыть сайт документации](https://rowolfs.github.io/docs-kit/)**

Движок превращает Markdown и тонкий конфиг проекта в сайт на GitHub Pages.
Скрипты и тема поставляются вместе с версией reusable workflow. Сервер
приложения не нужен; для сборки используется Zensical **0.1.0**.

Фазы 1 и 2 реализованы и опубликованы. Доступен экспериментальный релиз
[v0.2.0-alpha.1](https://github.com/Rowolfs/docs-kit/releases/tag/v0.2.0-alpha.1).
Модель кода, docs-check, журнал, статистика и шаблон проекта ещё не реализованы.
Эксперимент фазы 0 сохранён отдельно.

## Локальная сборка

Требуется Python 3.13; первую установку и подготовку Mermaid выполняют с сетью.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
make build
.venv/bin/python -m http.server 8767 --bind 127.0.0.1 --directory build/site
```

Открыть <http://127.0.0.1:8767/>. Канонические адреса этой сборки указывают
на Pages. Для проверки навигации с проектным префиксом использовать demo:

```bash
make demo
.venv/bin/python -m http.server 8766 --bind 127.0.0.1 --directory build/demo
```

Открыть <http://127.0.0.1:8766/docs-kit/>. Оба проекта собирает один скрипт;
исходный контент не изменяется, выходные каталоги не коммитятся.

## Каталоги

| Каталог | Назначение |
| --- | --- |
| `scripts/` | Подготовка контента и сборка сайта |
| `theme/` | Ассеты и override, подключающий точную локальную версию Mermaid |
| `docs/` | Документация самого docs-kit и отчёты фаз |
| `demo/` | Независимый тонкий проект и браузерная проверка |
| `demo/phase0/` | Сохранённый эксперимент фазы 0 |
| `tests/` | Контракты сборщика |
| `.github/workflows/build.yml` | Reusable workflow: сборка и необязательная публикация |

## Проверки

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
make test
make lint-yaml
```

Браузерные тесты требуют отдельного окружения:

```bash
python -m venv /tmp/docs-kit-browser
/tmp/docs-kit-browser/bin/python -m pip install -r demo/requirements-browser.txt
/tmp/docs-kit-browser/bin/python -m playwright install chromium
/tmp/docs-kit-browser/bin/python demo/check_browser.py
```

Последняя команда ожидает запущенный локальный сервер demo. Можно передать
`--url https://rowolfs.github.io/docs-kit/` для проверки опубликованного сайта
или `--browser /usr/bin/chromium-browser` для установленного Chromium.

[Подключение проекта](docs/connect.md) · [Архитектура](docs/architecture/containers.md)
· [Результаты фазы 0](docs/phase-0.md) · [Отчёт фазы 1](docs/phase-1.md)
· [Отчёт фазы 2](docs/phase-2.md)
