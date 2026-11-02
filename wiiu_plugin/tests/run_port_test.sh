#!/bin/sh
# Pulls the port editor out of src/main.cpp (between the "port-editor-core"
# markers) and runs tests/port_test.cpp against it. Needs a host g++; the
# plugin's Docker image has one:
#   docker run --rm -v "$PWD:/project" mh3u-revival-plugin sh tests/run_port_test.sh
set -e
cd "$(dirname "$0")/.."
mkdir -p build
sed -n '/port-editor-core begin/,/port-editor-core end/p' src/main.cpp > build/port_core.inc
if [ ! -s build/port_core.inc ]; then
    echo "port-editor-core markers not found in src/main.cpp" >&2
    exit 1
fi
${CXX:-g++} -std=c++20 -Wall -Wextra -Werror -O2 -I build tests/port_test.cpp -o build/port_test
./build/port_test
