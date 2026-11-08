---
id: docs-kit
type: project
status: implemented
verified_commit: 8dff56d2b41af6f6df99bcd1638fab72d39dcd37
---
<p class="docs-eyebrow">Документация, которой можно доверять</p>

# Quokki

Quokki — имя сайта и системы документации. Репозиторий движка и reusable
workflow сохраняют техническое имя `docs-kit`.

<p class="docs-lead">От общего понимания проекта — к устройству компонентов и реальному коду.</p>

<div class="lvl lvl-1" markdown>

<span id="_1" class="legacy-anchor"></span>

## О проекте {#overview}

docs-kit превращает Markdown проекта в единый статический сайт. Проект
хранит содержание и тонкий конфиг; версионируемый движок предоставляет
сборку, оформление и публикацию на GitHub Pages.

Этот сайт описывает движок и одновременно показывает его работу. Начните с
назначения системы, затем выберите глубину ползунком.

<div class="docs-grid" markdown="1">

<div class="docs-card" markdown="1">

### [Как устроена система](architecture/containers.md) {#start-architecture}

Границы проекта, путь от Markdown к сайту и ответственность каждой части.

</div>

<div class="docs-card" markdown="1">

### [Сборка документации](components/build.md) {#start-build}

Реализованный компонент: подготовка контента, рендеринг и результат сборки.

</div>

<div class="docs-card" markdown="1">

### [Подключить свой проект](connect.md) {#start-connect}

Конфигурация и workflow для публикации документации вашего репозитория.

</div>

<div class="docs-card" markdown="1">

### [Принципы документации](documentation-standard.md) {#start-principles}

Понятные объяснения, два независимых измерения и проверяемые требования.

</div>

</div>

Сборка и публикация реализованы. Модель кода, docs-check, журнал и статистика
запланированы на следующие фазы и пока не входят в движок.

</div>

<div class="lvl lvl-2" markdown="1">

<span id="_2" class="legacy-anchor"></span>

## Путь документации {#documentation-flow}

```mermaid
flowchart LR
  accTitle: Путь документации через docs-kit
  accDescr: Markdown и конфиг проекта поступают в сборщик docs-kit. Сборщик вызывает Zensical. Готовый статический сайт публикуется на GitHub Pages.
  content["Markdown и конфиг проекта"] --> build["Сборщик docs-kit"]
  build --> renderer["Zensical"]
  renderer --> site["Статический сайт на Pages"]
  classDef component stroke-width:2px
  class build component
  click build href "components/build/" "Открыть компонент сборки" _self
```

Одна версия workflow определяет и версию скриптов с темой. Сборка работает
во временном каталоге; исходные страницы не переписываются. Mermaid входит
в готовую статику, поэтому чтение диаграмм не требует обращения к CDN.

</div>

<div class="lvl lvl-3" markdown="1">

<span id="_3" class="legacy-anchor"></span>

## Детали реализации {#reader-details}

Контент остаётся доступным без JavaScript. В готовом сайте нет серверного
приложения: браузер получает HTML, CSS, локальные скрипты и диаграммы.

- [Фаза 0](phase-0.md) — результаты выбора генератора.
- [Фаза 1](phase-1.md) — результаты проверки сборки и публикации.
- [Фаза 2](phase-2.md) — тема, ползунок и метрики текста.

Исходники и рабочая инструкция находятся в
[репозитории docs-kit](https://github.com/Rowolfs/docs-kit).
Статус `implemented` описывает реализованную возможность. Привязка к коммиту
показывает проверенную ревизию; она не заменяет содержательную проверку
объяснения человеком. Отсутствие docs-check пока не означает, что страницы
прошли будущие строгие и мягкие проверки.

</div>
