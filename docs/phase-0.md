---
id: phase-0
type: experiment
status: implemented
---
# Фаза 0 — проверка гипотез

<div class="level-control" role="group" aria-label="Глубина документации" hidden>
<button type="button" data-level="1" aria-pressed="false">Обзор</button>
<button type="button" data-level="2" aria-pressed="false">Как устроено</button>
<button type="button" data-level="3" aria-pressed="false">Детали</button>
</div>

<div class="lvl lvl-1" markdown>

## Обзор

**Фаза 0 завершена 2026-11-08.** Zensical подходит для продолжения работы:
проверены Markdown внутри HTML, Mermaid, переход по узлу, накопительные уровни
с сохранением выбора, навигация и две темы. Менять генератор оснований нет.

Установлен **Zensical 0.1.0**, Mermaid закреплён на **12.3.0**.
Минимальный стенд находится в `demo/phase0/`. Это проверка гипотез, а не
реализованный движок docs-kit. Фаза 1 не начата.

Сборка `zensical build --strict` проходит без предупреждений. Браузерный тест
в Chromium проверяет основные сценарии. В основном контексте нет ошибок
страницы, ответов HTTP ≥400 и внешних запросов.

Результаты записываются в `build/phase0/browser-results.json`; рядом находятся
скриншоты светлой, тёмной и мобильной версий. Полные команды воспроизведения
приведены в `demo/phase0/README.md`.

</div>

<div class="lvl lvl-2" markdown="1">

## Как устроено

| Проверка запуском | Результат |
| --- | --- |
| Голый `markdown`, `markdown="1"`, `markdown="block"` | Вложенные заголовки, список, ссылки и код превращаются в HTML |
| Mermaid внутри lvl-2 | SVG отрисовывается; виден после раскрытия блока |
| `click probe href` | Настоящий клик мышью переводит на страницу компонента под `/docs-kit/` |
| Уровни 1/2/3 | Показывают соответственно первый, первые два или все три блока |
| Сохранение выбора | Работает после перезагрузки и перехода на другую страницу |
| Instant navigation | Контент меняется без пересоздания окна; выбор сохраняется; обработчики не дублируются |
| Клавиатура | Enter на кнопке меняет уровень |
| Тема и мобильная ширина | Светлая/тёмная тема переключается; при ширине 390 px страница не переполняется по горизонтали |
| Отказ хранилища уровней | Переключатель продолжает работать |
| JavaScript отключён | Все текстовые блоки и исходник Mermaid доступны; неработающие кнопки скрыты |

### Подключение Mermaid

Штатный bundle темы загружает плавающий `mermaid@12` с CDN. Один пин Zensical
не фиксирует версию Mermaid. Поэтому подготовительный скрипт скачивает точный
ассет **12.3.0** и проверяет SHA-256. Небольшой override шаблона подключает
локальный ассет **до** bundle темы. Тема использует уже доступный `window.mermaid`
и не обращается к CDN. Остальная отрисовка остаётся штатной.

Проверенный `click … href` работает с **securityLevel strict**. Ослабление до
`loose` не потребовалось. Официальная документация Mermaid предупреждает об
ограничении интерактивности в strict; результат относится только к проверенному
href-сценарию версии 12.3.0. JavaScript callbacks не проверялись.

### Переключение уровней

Небольшой собственный JS скрывает блоки глубже выбранного уровня, записывает
выбор в localStorage и обрабатывает `document$` для instant navigation. Без JS
контент открыт полностью. Связанные вкладки Zensical не использованы: они
показывают одну панель, тогда как требование задаёт накопительный показ.

</div>

<div class="lvl lvl-3" markdown="1">

## Детали

### Воспроизведение

Из корня репозитория:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-phase0.lock
.venv/bin/python demo/phase0/prepare.py
.venv/bin/zensical build --strict -f demo/phase0/zensical.toml
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 --directory demo/phase0/site
```

Открыть `http://127.0.0.1:8765/docs-kit/`. Локальный HTTP-сервер нужен только для
проверки статики; сервер приложения не появляется. В другом терминале:

```bash
python -m venv /tmp/docs-kit-browser
/tmp/docs-kit-browser/bin/python -m pip install -r demo/phase0/requirements-browser.txt
/tmp/docs-kit-browser/bin/python demo/phase0/check_browser.py
```

Проверено на Python **3.13.9**, Chromium **142.0.7444.175**, Playwright **1.56.0**.
Точный снимок Python-зависимостей сохранён в `requirements-phase0.lock`.
Он не содержит хэшей пакетов. У Mermaid отдельно проверяется SHA-256:

```text
336df803d87a38b70a01e736e666c8f7601d2ce42f5e47c8fafe5d721074b9a3
```

Тема помещает диаграмму в **закрытый Shadow DOM**. Тест сохраняет ссылки на
настоящие ShadowRoot до загрузки страницы, не меняя их режим, и получает
координаты узла для обычного клика мышью. Эта инструментализация отсутствует
в JS сайта. Отдельный первоначальный эксперимент со штатной CDN-загрузкой
также подтвердил SVG и переход при strict.

### Что не проверено и ограничения

- GitHub Pages, reusable workflow, права GitHub и удалённая публикация — фаза 1.
- Firefox, Safari, настоящий телефон, полная доступность и поведение поиска
  по скрытым блокам — пока не проверены.
- Синхронизация оглавления со скрытыми уровнями и автоматическое раскрытие
  уровня при переходе на якорь — ещё не реализованы; текущее оглавление может
  вести к скрытому заголовку. Это вопрос фазы 2.
- UI стенда минимальный; счётчик слов и финальная тема относятся к фазе 2.
- Отказ localStorage проверен для ключа уровней. Отказ хранилища всей темы
  Zensical не моделировался.
- Mermaid — локальный ассет около 5.3 MiB; оптимизация загрузки отложена.
  Первая подготовка требует доступа к unpkg, установка Python — к PyPI.
- Zensical до 1.0: пины и тест на demo нужны при каждом обновлении.
- На момент проверки Git ещё не был инициализирован, поэтому `verified_commit`
  для эксперимента не указан. Реестра, генератора модели и docs-check пока нет.

При обнаруженной в будущем несовместимости первый запасной вариант для
обсуждения — MkDocs Material. Он в этой фазе не установлен и не проверен.

### Источники и ограничения GitHub

- [PyPI Zensical](https://pypi.org/project/zensical/) — версия 0.1.0 и Python ≥3.11.
- [Markdown extensions](https://zensical.org/docs/compatibility/markdown/python-markdown/),
  [md_in_html](https://python-markdown.github.io/extensions/md_in_html/) — HTML-блоки.
- [Zensical diagrams](https://zensical.org/docs/authoring/diagrams/),
  [Mermaid interaction](https://mermaid.js.org/syntax/flowchart.html#interaction) — диаграммы.
- [Customization](https://zensical.org/docs/customization/),
  [content tabs](https://zensical.org/docs/authoring/content-tabs/#linked-content-tabs),
  [colors](https://zensical.org/docs/setup/colors/) — JS/CSS, вкладки и темы.

По официальной документации закрытый Pages требует организацию с GitHub
Enterprise Cloud. Branch protection private-репозиториев требует
Pro/Team/Enterprise; GitHub Free поддерживает защиту public-репозиториев.
Условия конкретного аккаунта не проверялись.
Источники: [Pages visibility](https://docs.github.com/en/enterprise-cloud%40latest/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site),
[branch protection](https://docs.github.com/en/rest/branches/branch-protection).

До фазы 4 представить сравнение собственных проверок с LiveDoc и дождаться
решения пользователя. Каждая фаза заканчивается остановкой до «дальше».

</div>
