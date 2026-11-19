#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run scripts/uninstall.py with Python 3.11+. Usage: scripts/uninstall.sh [TARGET] [options]
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/python.sh
. "$here/lib/python.sh"
py=$(stagegate_find_python)
"$py" -E -s "$here/uninstall.py" "$@"
