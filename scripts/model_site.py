"""Render generated file facts and resolve file: links without changing Markdown."""
import html
from html.parser import HTMLParser
from pathlib import PurePosixPath
import re
from urllib.parse import quote, unquote


def file_url(path, context):
    if not context['repository'] or path not in context['committed_paths']:
        return None
    full = context['prefix'] + path
    return f"{context['repository']}/blob/{context['commit']}/{quote(full, safe='/')}"


def render_map(registry, records, context):
    def safe(value):
        return html.escape(str(value)).replace('|', '&#124;').replace('\n', ' ').replace('[', '&#91;').replace(']', '&#93;')
    lines = ['---', 'id: generated-code-map', 'type: reference', 'status: implemented', '---',
             '# Карта проекта', '', '<div class="lvl lvl-1" markdown="1">', '', '## Кратко', '',
             'Эта страница генерируется из реестра компонентов и списка файлов при сборке.',
             'Назначение кода и зависимости из импортов автоматически не определяются.',
             'Незакоммиченные файлы показаны без ссылки на GitHub.', '', '</div>', '',
             '<div class="lvl lvl-2" markdown="1">', '', '## Компоненты', '',
             '| Компонент | Пути | Объявленные зависимости |', '| --- | --- | --- |']
    for identifier, component in registry.items():
        page = PurePosixPath(component['page']).relative_to('docs').as_posix()
        url = '../' + quote(page, safe='/')
        lines.append(f"| [{safe(component['title'])}]({url}) | {safe(', '.join(component['paths']))} | {safe(', '.join(component.get('depends_on', [])) or '—')} |")
    if registry:
        lines.extend(['', '```mermaid', 'flowchart LR', '  accTitle: Объявленные зависимости компонентов'])
        node_ids = {key: f'c{index}' for index, key in enumerate(registry)}
        for key, value in registry.items():
            # Diagram labels are IDs validated by the registry, never arbitrary descriptions.
            lines.append(f'  {node_ids[key]}["{key}"]')
            parts = list(PurePosixPath(value['page']).relative_to('docs').with_suffix('').parts)
            if parts[-1] == 'index':
                parts.pop()
            target = '../../' + quote('/'.join(parts), safe='/') + ('/' if parts else '')
            lines.append(f'  click {node_ids[key]} href "{target}" "Компонент" _self')
        for key, value in registry.items():
            for dependency in value.get('depends_on', []):
                lines.append(f'  {node_ids[key]} --> {node_ids[dependency]}')
        lines.extend(['```', ''])
    lines.extend(['</div>', '', '<div class="lvl lvl-3" markdown="1">', '', '## Файлы и папки', '',
                  '| Путь | Тип |', '| --- | --- |'])
    paths = {record['code']['path']: record['kind'] for record in records
             if record.get('code') and record['kind'] in {'file', 'folder', 'directory'}}
    for path, kind in sorted(paths.items()):
        url = file_url(path, context) if kind == 'file' else None
        label = f'<code>{safe(path)}</code>'
        if url:
            label = f'<a href="{html.escape(url, quote=True)}">{label}</a>'
        lines.append(f'| {label} | {safe(kind)} |')
    lines.extend(['', '</div>', ''])
    return '\n'.join(lines)


class LinkResolver(HTMLParser):
    def __init__(self, source, paths, context):
        super().__init__(convert_charrefs=False)
        self.source, self.paths, self.context = source, paths, context
        self.offsets = [0] + [m.end() for m in re.finditer('\n', source)]
        self.edits = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get('href', '')
        if tag != 'a' or not href.startswith(('file:', 'sym:')):
            return
        if href.startswith('sym:'):
            raise ValueError('sym: links require deferred symbol support; use file: links')
        path = unquote(href[5:])
        if path not in self.paths:
            raise ValueError(f'Unknown file link: {path}')
        url = file_url(path, self.context)
        if not url:
            raise ValueError(f'Cannot pin file:{path}: commit the file and configure a GitHub origin')
        raw = self.get_starttag_text()
        raw = re.sub(r'''(?<=\s)href\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)''',
                     lambda _: 'href="' + html.escape(url, quote=True) + '"', raw, count=1,
                     flags=re.IGNORECASE | re.DOTALL)
        line, column = self.getpos()
        start = self.offsets[line - 1] + column
        self.edits.append((start, start + len(self.get_starttag_text()), raw))


def resolve_links(source, paths, context):
    parser = LinkResolver(source, paths, context)
    parser.feed(source)
    parser.close()
    for start, end, replacement in reversed(parser.edits):
        source = source[:start] + replacement + source[end:]
    return source
