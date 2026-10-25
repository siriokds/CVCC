#!/bin/sh
set -eu
compiler_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
deps=${CVCC_DEPS_DIR:-"$compiler_dir/.deps"}
build=${CVCC_BUILD_DIR:-"$compiler_dir/build"}
for source in "$deps/tree-sitter/lib/src/lib.c" "$deps/tree-sitter-cpp/src/parser.c" "$deps/tree-sitter-cpp/src/scanner.c"; do
    if [ ! -f "$source" ]; then
        printf 'Missing dependency source: %s\nSee %s/README.md or set CVCC_DEPS_DIR.\n' "$source" "$compiler_dir" >&2
        exit 1
    fi
done
mkdir -p "$build"
# Upstream code stays outside the public repository.
cc=${CC:-cc}
"$cc" -std=c11 -D_DEFAULT_SOURCE -O2 -I"$deps/tree-sitter/lib/include" -I"$deps/tree-sitter/lib/src" -c "$deps/tree-sitter/lib/src/lib.c" -o "$build/tree-sitter.o"
"$cc" -std=c11 -O0 -I"$deps/tree-sitter-cpp/src" -c "$deps/tree-sitter-cpp/src/parser.c" -o "$build/cpp-parser.o"
"$cc" -std=c11 -O2 -I"$deps/tree-sitter-cpp/src" -c "$deps/tree-sitter-cpp/src/scanner.c" -o "$build/cpp-scanner.o"
"$cc" -std=c11 -Wall -Wextra -Werror -pedantic -O2 -I"$deps/tree-sitter/lib/include" "$compiler_dir/src/cvcc.c" "$build/tree-sitter.o" "$build/cpp-parser.o" "$build/cpp-scanner.o" -o "$build/cvcc"
printf 'Built %s/cvcc\n' "$build"
