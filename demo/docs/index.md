---
id: demo
type: project
status: implemented
---
<p class="docs-eyebrow">Один проект · один понятный сайт</p>

# Quokki · demo

<p class="docs-lead">Небольшой пример документации, подключённой к общему движку.</p>

<div class="lvl lvl-1" markdown>

<span id="_1" class="legacy-anchor"></span>

## О demo {#overview}

Этот минимальный проект показывает подключение движка docs-kit к обычной
Markdown-документации. В demo нет отдельного приложения: его содержимое —
конфигурация сайта и страницы, которые движок превращает в статику.

<div class="docs-grid" markdown="1">

<div class="docs-card" markdown="1">

### [Сборка документации](components/build.md) {#start-build}

От исходных страниц и конфигурации до готовой статики.

</div>

<div class="docs-card" markdown="1">

### [Путь контента](#documentation-flow) {#start-flow}

Посмотрите, какую работу выполняет проект, а какую — движок.

</div>

<div class="docs-card" markdown="1">

### [Подробные ограничения](#reader-details) {#start-details}

Проверьте границы стенда и доступ к полному содержанию.

</div>

</div>

</div>

<div class="lvl lvl-2" markdown="1">

<span id="_2" class="legacy-anchor"></span>

## Путь документации {#documentation-flow}

Движок получает конфигурацию проекта, Markdown и собственную тему. Результат
можно открыть на локальном HTTP-сервере или опубликовать на GitHub Pages.

```mermaid
flowchart LR
  accTitle: Путь контента в demo
  accDescr: Markdown и конфигурация поступают в сборку документации. Сборка создаёт статический сайт.
  source["Markdown и конфигурация"] --> build["Сборка документации"]
  build --> site["Статический сайт"]
  classDef component stroke-width:2px
  class build component
  click build href "components/build/" "Открыть описание сборки" _self
```

</div>

<div class="lvl lvl-3" markdown="1">

<span id="_3" class="legacy-anchor"></span>

## Детали реализации {#reader-details}

Контент остаётся доступным без JavaScript. Этот режим открывает все уровни
страницы; для чтения готового HTML сервер приложения не требуется.

`docs-kit.toml` задаёт название, описание и навигацию. Контент хранится в
`docs/`. Скрипты и тема находятся в репозитории движка и не копируются в
исходники demo. Сгенерированная статика не является исходником документации.

Анализ кода, генерация модели, docs-check, журнал и статистика не входят в
этот demo. Это запланированные возможности последующих фаз.

</div>
