# Проверочный стенд фазы 0

Минимальный эксперимент, подтверждающий пригодность Zensical. Рабочая тема,
reusable workflow и публикация ещё не реализованы.

Из корня репозитория:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-phase0.lock
.venv/bin/python demo/phase0/prepare.py
.venv/bin/zensical build --strict -f demo/phase0/zensical.toml
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 --directory demo/phase0/site
```

Открыть <http://127.0.0.1:8765/docs-kit/>. Сервер здесь нужен только для локальной
проверки готовой статики. Остановить его — Ctrl+C.

`prepare.py` скачивает Mermaid **12.3.0**, проверяет SHA-256 и создаёт локальный
ассет для ранней загрузки до bundle темы. Это предотвращает штатную загрузку
плавающего `mermaid@12` с CDN. Генерируемый ассет не хранится в Git. Подготовка
требует сеть; просмотр уже собранного demo обходится без внешних запросов.
Тот же скрипт копирует единственный исходник отчёта `docs/phase-0.md` в demo;
сгенерированный `docs/report.md` вручную не редактировать.

Для браузерной проверки, в другом терминале, пока сервер работает:

```bash
python -m venv /tmp/docs-kit-browser
/tmp/docs-kit-browser/bin/python -m pip install -r demo/phase0/requirements-browser.txt
/tmp/docs-kit-browser/bin/python demo/phase0/check_browser.py --browser /usr/bin/chromium-browser
```

Нужен установленный Chromium. Путь можно передать через `--browser`.
Проверка сохраняет JSON с результатами и скриншоты в `build/phase0/`.
В тесте временно сохраняются ссылки на закрытые ShadowRoot без изменения их
режима; это позволяет проверить SVG и определить координаты настоящего клика.
Инструментализация не включена в сайт.

Проверено: Python 3.13.9, Chromium 142.0.7444.175, Playwright 1.56.0 на Linux.
`requirements-phase0.lock` — точный снимок Python-зависимостей эксперимента,
без хэшей пакетов; это ещё не система фиксации зависимостей движка.
