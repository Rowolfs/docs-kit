---
id: build
type: component
status: implemented
verified_commit: 8dff56d2b41af6f6df99bcd1638fab72d39dcd37
---
# Сборка документации

<div class="lvl lvl-1" markdown>

<span id="_2"></span>

## Кратко {#component-overview}

Сборка превращает Markdown этого demo в статический сайт через внешний
движок docs-kit. Исходные страницы остаются в проекте; сервер приложения
для чтения готового сайта не нужен.

[Вернуться на главную](../index.md).

</div>

<div class="lvl lvl-2" markdown="1">

<span id="_3"></span>

## Подробно {#component-flow}

Движок читает `docs-kit.toml`, подготавливает контент и свои ассеты во
временном каталоге, затем запускает Zensical с закреплёнными зависимостями.
Полученный HTML, CSS и JavaScript поступают в каталог результата сборки.

</div>

<div class="lvl lvl-3" markdown="1">

<span id="_4"></span>

## Полностью {#component-details}

Demo не содержит собственной копии движка. В CI reusable workflow получает
исходники проекта и нужную версию docs-kit. Локальная проверка использует тот
же Python-скрипт сборки из рабочего каталога движка.

Настройки Pages и права GitHub Actions относятся к репозиторию, который
публикует сайт. Генератор модели кода и проверки содержимого документации
появятся в последующих фазах.

</div>
