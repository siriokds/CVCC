#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
deps=${CVCC_DEPS_DIR:-.work/deps}
build=${CVCC_BUILD_DIR:-build}
mkdir -p "$build"
# Upstream code stays outside the public repository.
cc=${CC:-cc}
"$cc" -std=c11 -D_DEFAULT_SOURCE -O2 -I"$deps/tree-sitter/lib/include" -I"$deps/tree-sitter/lib/src" -c "$deps/tree-sitter/lib/src/lib.c" -o "$build/tree-sitter.o"
"$cc" -std=c11 -O0 -I"$deps/tree-sitter-cpp/src" -c "$deps/tree-sitter-cpp/src/parser.c" -o "$build/cpp-parser.o"
"$cc" -std=c11 -O2 -I"$deps/tree-sitter-cpp/src" -c "$deps/tree-sitter-cpp/src/scanner.c" -o "$build/cpp-scanner.o"
"$cc" -std=c11 -Wall -Wextra -Werror -pedantic -O2 -I"$deps/tree-sitter/lib/include" src/cvcc.c "$build/tree-sitter.o" "$build/cpp-parser.o" "$build/cpp-scanner.o" -o "$build/cvcc"
