---
id: browser
type: component
status: implemented
verified_commit: 0e580d7308017d1d00db8d1a63e30c8e502ce1a3
---
# Браузерная проверка

<div class="lvl lvl-1" markdown>

## Кратко

`check_browser.py` открывает собранный сайт в Chromium через Playwright и
проверяет уровни чтения, переходы, поиск, темы и адаптивность. Отдельный `check_map.py` проверяет навигацию интерактивной карты. Это код demo,
который попадает в [генерируемую карту](../_generated/code-map.md).

</div>

<div class="lvl lvl-2" markdown>

## Подробно

Скрипт запускается после сборки demo и старта локального HTTP-сервера.
При ошибке сохраняются снимок экрана и JSON-отчёт. Тесты проверяют поведение
интерфейса, а понимание текста человеком и экранный диктор требуют отдельной
ручной проверки.

</div>

<div class="lvl lvl-3" markdown>

## Полностью

Зависимость Playwright закреплена в `requirements-browser.txt`. Артефакты
сохраняются в `build/phase2`, не коммитятся и доступны в CI как browser-evidence.
Исходники: [check_browser.py](file:check_browser.py),
[check_map.py](file:check_map.py). В реестр также включена сохранённая проверка
фазы 0: она даёт реальную вложенную папку для проверки раскрытия карты.

</div>
