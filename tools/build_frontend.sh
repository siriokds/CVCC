#!/bin/sh
# Compatibility entry point. New builds live in compiler/build/.
set -eu
tools_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$tools_dir/../compiler/build.sh" "$@"
