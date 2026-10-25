#!/bin/sh
set -eu
ide_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$ide_dir/serve.py" "$@"
