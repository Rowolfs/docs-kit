---
id: demo
type: project
status: implemented
---
# docs-kit demo

<div class="lvl lvl-1" markdown>

## Обзор

Этот минимальный проект показывает подключение движка docs-kit к обычной
Markdown-документации. В demo нет отдельного приложения: его содержимое —
конфигурация сайта и страницы, которые движок превращает в статику.

[Сборка документации](components/build.md) описывает путь от исходных файлов
до готового сайта.

</div>

<div class="lvl lvl-2" markdown="1">

## Как устроено

Движок получает конфигурацию проекта, Markdown и собственную тему. Результат
можно открыть на локальном HTTP-сервере или опубликовать на GitHub Pages.

```mermaid
flowchart LR
  source["Markdown и конфигурация"] --> build["Сборка документации"]
  build --> site["Статический сайт"]
  classDef component stroke-width:2px
  class build component
  click build href "components/build/" "Открыть описание сборки" _self
```

</div>

<div class="lvl lvl-3" markdown="1">

## Детали

`docs-kit.toml` задаёт название, описание и навигацию. Контент хранится в
`docs/`. Скрипты и тема находятся в репозитории движка и не копируются в
исходники demo. Сгенерированная статика не является исходником документации.

Анализ кода, генерация модели, docs-check, журнал и статистика не входят в
этот стенд фазы 1.

</div>
