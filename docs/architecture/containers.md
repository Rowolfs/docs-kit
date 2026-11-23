---
id: architecture
type: architecture
status: implemented
verified_commit: e02b1a7abc80b61eb5c7ea946608502574cde042
---
# Архитектура Quokki

<div class="lvl lvl-1" markdown>

## Кратко

Три границы: репозиторий проекта хранит содержание, версионируемый движок
выполняет сборку в CI, GitHub Pages раздаёт готовую статику читателю.
Базы данных и серверного приложения нет.

</div>

<div class="lvl lvl-2" markdown="1">

## Подробно

```mermaid
flowchart TB
  subgraph project["Репозиторий проекта"]
    docs["Markdown + docs-kit.toml"]
    caller["Тонкий workflow с версией движка"]
  end
  subgraph engine["GitHub Actions: выбранная версия docs-kit"]
    build["Python: временный проект сборки"]
    zensical["Zensical: HTML + CSS + JS"]
    artifact["Pages-артефакт"]
  end
  docs --> build
  caller --> build
  build --> zensical --> artifact
  artifact --> pages["GitHub Pages"]
  pages --> human["Браузер читателя"]
```

На сайте работает только браузерный JavaScript: тема, поиск, диаграммы и
ползунок глубины чтения. Метрики добавляются в HTML при сборке.

</div>

<div class="lvl lvl-3" markdown="1">

## Полностью

У проекта и движка отдельные checkout. SHA движка берётся из определения
reusable job. Таким образом, обновление ветки движка не влияет на проект,
который закрепил старый релиз или SHA.

В движке docs-kit CI проверяет исходники текущего коммита и независимый demo.
После успешного CI на push в `main` отдельный workflow документации собирает
проверенный коммит, вызывая опубликованную версию движка.

Модель файлов и папок генерируется перед рендерингом из `components.yaml`.
JSON и карта кода добавляются в готовую статику.
Cytoscape.js в браузере показывает объявленные зависимости и раскрывает
папки и файлы по JSON; внешний сервис визуализации не используется.
Проверки docs-check, журнал и статистика остаются **planned**.
Агенты обновляют объяснения в Markdown вместе с кодом; автоматического вызова
LLM при сборке нет.

</div>
