#!/usr/bin/env bash
# Fresh preparation plus independently refreshed official provenance/licenses.
set -euo pipefail
cd "$(dirname "$0")/.."
bash recipes/reproduce.sh
python3 -I -S -B recipes/verify_upstream_artifacts.py public312
python3 -I -S -B recipes/verify_upstream_artifacts.py public313
