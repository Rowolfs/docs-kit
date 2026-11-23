"""Generate a file/folder model from Git metadata; never read source contents."""

import argparse
import fnmatch
import json
from pathlib import Path, PurePosixPath
import tempfile
import shutil
import re
import subprocess
from urllib.parse import quote

import yaml

MAX_BYTES = 30 * 1024
EXCLUDED_DIRS = {'.git', '.cache', '.venv', 'venv', 'node_modules', 'build', 'site', 'dist', '__pycache__', 'docs'}
SECRET_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.jks', '.keystore'}
OWNER = '.docs-kit-model'


def git(project, *args):
    result = subprocess.run(['git', '-C', str(project), *args], capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.decode('utf-8', errors='replace').strip() or 'Git command failed')
    return result.stdout


def safe_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('Paths must be nonempty relative POSIX paths')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or value.startswith('/'):
        raise ValueError(f'Path escapes project: {value}')
    return value


def included(path):
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    return (not any(part in EXCLUDED_DIRS for part in parts)
            and not any(part.lower() in {'secrets', '.ssh', '.aws'} for part in parts)
            and not name.startswith('.env') and name not in {'id_rsa', 'id_ed25519', 'credentials', 'credentials.json'}
            and PurePosixPath(name).suffix not in SECRET_SUFFIXES)


def list_files(project):
    """Tracked and untracked nonignored files; symlinks are not code targets."""
    project = Path(project).resolve()
    root = Path(git(project, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    output = git(project, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')
    result = []
    for raw in output.split(b'\0'):
        if not raw:
            continue
        path = raw.decode('utf-8')
        safe_path(path)
        target = project / path
        if not included(path) or not target.is_file() or target.is_symlink():
            continue
        if not target.resolve().is_relative_to(project):
            continue
        if any(parent.is_symlink() for parent in target.parents if parent != project and parent.is_relative_to(project)):
            continue
        result.append(path)
    return sorted(set(result))


def matches(path, pattern):
    """Match POSIX globs; ** spans zero or more directories, * spans one."""
    pieces = pattern.split('/')
    names = path.split('/')

    def visit(i, j):
        if i == len(pieces):
            return j == len(names)
        if pieces[i] == '**':
            return visit(i + 1, j) or (j < len(names) and visit(i, j + 1))
        return j < len(names) and fnmatch.fnmatchcase(names[j], pieces[i]) and visit(i + 1, j + 1)
    return visit(0, 0)


def matching_components(registry, path):
    return [key for key, item in registry.items() if any(matches(path, pattern) for pattern in item['paths'])]


def load_registry(project):
    project = Path(project).resolve()
    source = project / 'components.yaml'
    if source.is_symlink():
        raise ValueError('components.yaml must not be a symlink')
    data = yaml.safe_load(source.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) != {'components'} or not isinstance(data['components'], dict):
        raise ValueError('components.yaml must contain a components mapping')
    registry = data['components']
    for key, item in registry.items():
        if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', key):
            raise ValueError(f'Invalid component ID: {key}')
        if not isinstance(item, dict) or set(item) - {'title', 'paths', 'depends_on', 'page'}:
            raise ValueError(f'Invalid component record: {key}')
        if not isinstance(item.get('title'), str) or not item['title'].strip():
            raise ValueError(f'Component needs title: {key}')
        if not isinstance(item.get('paths'), list) or not item['paths']:
            raise ValueError(f'Component needs paths: {key}')
        for pattern in item['paths']:
            safe_path(pattern)
        dependencies = item.get('depends_on', [])
        if not isinstance(dependencies, list) or any(not isinstance(dep, str) or dep not in registry for dep in dependencies):
            raise ValueError(f'Unknown dependency in {key}')
        page = safe_path(item.get('page'))
        target = project / page
        if not page.startswith('docs/') or target.suffix != '.md' or not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(project / 'docs'):
            raise ValueError(f'Component page must exist within docs/: {key}')
        if (project / 'docs').is_symlink() or any(parent.is_symlink() for parent in target.parents if parent != project and parent.is_relative_to(project)):
            raise ValueError(f'Component page cannot use symlinks: {key}')
        item.setdefault('depends_on', [])
    return dict(sorted(registry.items()))


def head_commit(project):
    result = subprocess.run(['git', '-C', str(project), 'rev-parse', '--verify', 'HEAD'],
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def source_metadata(project):
    commit = head_commit(project)
    remote = subprocess.run(['git', '-C', str(project), 'remote', 'get-url', 'origin'], capture_output=True, text=True)
    root = Path(git(project, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    prefix = project.relative_to(root).as_posix()
    prefix = '' if prefix == '.' else prefix + '/'
    committed = (git(project, 'ls-tree', '-r', '--name-only', '-z', '--full-name', 'HEAD', '--', '.').split(b'\0')
                 if commit else [])
    committed_paths = [raw.decode('utf-8')[len(prefix):] for raw in committed
                       if raw and raw.decode('utf-8').startswith(prefix) and included(raw.decode('utf-8')[len(prefix):])]
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?/?', remote.stdout.strip())
    return {'commit': commit, 'repository': f'https://github.com/{match[1]}' if match else None, 'prefix': prefix, 'committed_paths': sorted(committed_paths)}


def code_url(project, path, source=None):
    safe_path(path)
    source = source if source is not None else source_metadata(project)
    return f"{source['repository']}/blob/{source['commit']}/{quote(source['prefix'] + path, safe='/')}" if source['repository'] and path in source['committed_paths'] else None


def build_model(project):
    project = Path(project).resolve()
    registry = load_registry(project)
    files = list_files(project)
    source = source_metadata(project)
    components = {}
    root = {'id': 'project', 'kind': 'project', 'parent': None, 'code': {'path': '.', 'lines': None}}
    records = [root]
    seen_dirs = {key: set() for key in [None, *registry]}
    for key, component in registry.items():
        record = {'id': f'component:{key}', 'kind': 'component', 'parent': 'project',
                  'code': {'path': None, 'lines': None}, 'doc': component['page'], 'title': component['title'],
                  'depends_on': component['depends_on']}
        records.append(record)
        components[key] = []
    for path in files:
        owners = matching_components(registry, path)
        if len(owners) > 1:
            raise ValueError(f'Overlapping components for {path}: {", ".join(owners)}')
        key = owners[0] if owners else None
        component_records = components[key] if key else records
        parent = f'component:{key}' if key else 'project'
        for folder in list(PurePosixPath(path).parents)[-2::-1]:
            directory = str(folder)
            identifier = f'directory:{key or "_"}:{directory}'
            if identifier not in seen_dirs[key]:
                seen_dirs[key].add(identifier)
                component_records.append({'id': identifier, 'kind': 'directory', 'parent': parent,
                                          'code': {'path': directory, 'lines': None}})
            parent = identifier
        component_records.append({'id': f'file:{path}', 'kind': 'file', 'parent': parent,
                                  'code': {'path': path, 'lines': None,
                                           'url': code_url(project, path, source)}})
    return {'schema_version': 1, 'source': source, 'records': records, 'components': components}


def records_for(project):
    model = build_model(project)
    records = model['records'] + [record for group in model['components'].values() for record in group]
    return load_registry(project), records, model['source']


def encode(data):
    return (json.dumps(data, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + '\n').encode('utf-8')


def write_pages(output, stem, records, extra=None):
    """Write bounded pages linked by next; return paths relative to output."""
    extra = extra or {}
    chunks = [[]]
    # Reserve enough for next paths and the envelope before grouping records.
    for record in records:
        candidate = chunks[-1] + [record]
        if len(encode({**extra, 'records': candidate, 'next': stem + '-999999.json'})) > MAX_BYTES:
            if not chunks[-1]:
                raise ValueError('Single model record exceeds the 30 KiB limit')
            chunks.append([record])
        else:
            chunks[-1] = candidate
    paths = [f'{stem}.json' if i == 0 else f'{stem}-{i + 1:04d}.json' for i in range(len(chunks))]
    for i, chunk in enumerate(chunks):
        data = {**extra, 'records': chunk, 'next': paths[i + 1] if i + 1 < len(paths) else None}
        payload = encode(data)
        if len(payload) > MAX_BYTES:
            raise ValueError('Model page exceeds the 30 KiB limit')
        target = output / paths[i]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return paths


def generate(project, output=None):
    project = Path(project).resolve()
    output = Path(output).absolute() if output is not None else project / 'build/model'
    model = build_model(project)
    # Never recursively delete a directory. Only replace files owned by our manifest.
    if output.is_symlink() or not output.resolve().is_relative_to(project / 'build'):
        raise ValueError('Model output must be inside the project build/ directory, without symlinks')
    if output.exists() and not (output / OWNER).is_file() and any(output.iterdir()):
        raise ValueError('Refusing an output directory not owned by docs-kit')
    if output.exists() and any(path.is_symlink() for path in output.rglob('*')):
        raise ValueError('Symlinks inside model output are not supported')
    output.mkdir(parents=True, exist_ok=True)
    old = json.loads((output / OWNER).read_text()) if (output / OWNER).exists() else []
    for name in old:
        safe_path(name)
        target = output / name
        if not target.resolve().is_relative_to(output.resolve()) or target.is_symlink():
            raise ValueError('Unsafe previous model manifest')
    with tempfile.TemporaryDirectory(prefix='docs-kit-model-') as directory:
        stage = Path(directory)
        paths = []
        index_records = list(model['records'])
        for key, records in model['components'].items():
            component_paths = write_pages(stage, f'components/{key}', records)
            paths.extend(component_paths)
            index_records.extend({'id': f'model:{path}', 'kind': 'model-file', 'parent': f'component:{key}',
                                  'code': {'path': None, 'lines': None}, 'model_file': path} for path in component_paths)
        paths.extend(write_pages(stage, 'index', index_records, {'schema_version': 1, 'source': {key: value for key, value in model['source'].items() if key != 'committed_paths'}}))
        for name in paths:
            if (output / name).exists() and name not in old:
                raise ValueError(f'Refusing to overwrite unowned model file: {name}')
        for name in paths:
            (output / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / name, output / name)
        for name in set(old) - set(paths):
            (output / name).unlink(missing_ok=True)
        (output / OWNER).write_bytes(encode(paths))
    return {'index': str(output / 'index.json'), 'files': paths, 'source': model['source']}


def changed(project, base='HEAD'):
    if not isinstance(base, str) or not base or base.startswith('-'):
        raise ValueError('base must be a Git revision, not an option')
    registry = load_registry(project)
    # --no-renames reports both old and new paths for renames.
    if base == 'HEAD' and head_commit(project) is None:
        names = list_files(project)
    else:
        paths = git(project, 'diff', '--relative', '--name-only', '--no-renames', '-z', base, '--', '.').split(b'\0')
        paths += git(project, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0')
        names = sorted({path.decode('utf-8') for path in paths if path and included(path.decode('utf-8'))})
    return {'base': base, 'files': names, 'components': sorted({key for path in names for key in matching_components(registry, path)})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', type=Path, default=Path.cwd())
    parser.add_argument('--output-dir', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('build')
    for command, argument in [('show', 'id'), ('find', 'query'), ('deps', 'id')]:
        commands.add_parser(command).add_argument(argument)
    commands.add_parser('changed').add_argument('--base', default='HEAD')
    args = parser.parse_args()
    try:
        if args.command == 'build':
            result = generate(args.project_dir, args.output_dir)
        elif args.command == 'changed':
            result = changed(args.project_dir, args.base)
        else:
            model = build_model(args.project_dir)
            records = model['records'] + [record for items in model['components'].values() for record in items]
            if args.command == 'find':
                result = [record for record in records if args.query.casefold() in json.dumps(record, ensure_ascii=False).casefold()]
            elif args.command == 'show':
                identifier = args.id if ':' in args.id or args.id == 'project' else f'component:{args.id}'
                result = next((record for record in records if record['id'] == identifier), None)
                if result is None:
                    raise ValueError(f'Unknown ID: {args.id}')
            else:
                identifier = args.id.removeprefix('component:')
                registry = load_registry(args.project_dir)
                if identifier not in registry:
                    raise ValueError(f'Unknown component: {args.id}')
                result = {'id': identifier, 'depends_on': registry[identifier]['depends_on'],
                          'used_by': [key for key, value in registry.items() if identifier in value['depends_on']]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, yaml.YAMLError) as error:
        parser.exit(1, f'docs-model: {error}\n')


if __name__ == '__main__':
    main()
