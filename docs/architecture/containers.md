---
id: architecture
type: architecture
status: implemented
---
# Архитектура фазы 1

<div class="lvl lvl-1" markdown>

## Обзор

Три границы: репозиторий проекта хранит содержание, версионируемый движок
выполняет сборку в CI, GitHub Pages раздаёт готовую статику читателю.
Базы данных и серверного приложения нет.

</div>

<div class="lvl lvl-2" markdown="1">

## Как устроено

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
минимальный переключатель уровней. Подготовка контента происходит при сборке.

</div>

<div class="lvl lvl-3" markdown="1">

## Детали

У проекта и движка отдельные checkout. SHA движка берётся из определения
reusable job. Таким образом, обновление ветки движка не влияет на проект,
который закрепил старый релиз или SHA.

В самом docs-kit CI проверяет исходники текущего коммита и независимый demo.
После успешного CI на push в `main` отдельный workflow документации собирает
проверенный коммит, вызывая опубликованную версию движка.

Компоненты будущих фаз — модель, docs-check, журнал, статистика — **planned**.
Они будут добавляться перед рендерингом, но сейчас в конвейере отсутствуют.
Агенты обновляют объяснения в Markdown вместе с кодом; автоматического вызова
LLM при сборке нет.

</div>
