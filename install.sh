#!/usr/bin/env bash
# Run from the root of the project receiving Quokki documentation.
set -euo pipefail

QUOKKI_VERSION='v0.3.0-alpha.2'
if [[ "${1:-}" == '--help' ]]; then
  printf '%s\n' 'Quokki: run in a Git repository root.' \
    'No arguments: create documentation scaffolding and a generated model.' \
    '--model COMMAND [ARGS]: run the pinned docs-model CLI without changing scaffolding.'
  exit 0
fi
command -v git >/dev/null || { printf '%s\n' 'Quokki requires Git.' >&2; exit 1; }
command -v python3 >/dev/null || { printf '%s\n' 'Quokki requires Python 3.11+ with venv.' >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Quokki requires Python 3.11+")'
project_directory="$PWD"
repository_root=$(git rev-parse --show-toplevel)
[[ "$(cd "$repository_root" && pwd -P)" == "$(pwd -P)" ]] || {
  printf '%s\n' 'Run Quokki from the repository root.' >&2; exit 1;
}
temporary_directory=$(mktemp -d "${TMPDIR:-/tmp}/quokki-install.XXXXXXXX")
trap 'rm -rf -- "$temporary_directory"' EXIT
git clone --quiet --depth 1 --branch "$QUOKKI_VERSION" \
  https://github.com/Rowolfs/docs-kit.git "$temporary_directory/engine"
python3 -m venv "$temporary_directory/venv"
python="$temporary_directory/venv/bin/python"
"$python" -m pip install --quiet --disable-pip-version-check 'PyYAML==6.0.3'
if [[ "${1:-}" == '--model' ]]; then
  shift
  "$python" "$temporary_directory/engine/scripts/docs_model.py" \
    --project-dir "$project_directory" "$@"
else
  "$python" "$temporary_directory/engine/scripts/install.py" \
    --project-dir "$project_directory" --engine-version "$QUOKKI_VERSION" "$@"
fi
