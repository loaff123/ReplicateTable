#!/usr/bin/env bash
# Fresh exact public profile. Binaries, local paths and logs stay outside checkout.
set -euo pipefail
profile="$1"
destination="$2"
case "$profile" in public312) minor=3.12;; public313) minor=3.13;; *) exit 2;; esac
qualification="$(cd "$(dirname "$0")" && pwd)"
test ! -e "$destination"
mkdir -p "$destination"
cp -R "$qualification/runtime-inputs/." "$destination/"
cd "$destination"
mkdir -p logs downloads profiles receipts metadata
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH PYTHONHOME
python3 -I -S -B recipes/acquire_interpreters.py "$profile"
python3 -I -S -B recipes/tree_snapshot.py "profiles/$profile/python" "receipts/$profile-interpreter-before.json"
"profiles/$profile/python/bin/python$minor" -I -B recipes/inspect_python.py "$profile" before
"profiles/$profile/python/bin/python$minor" -I -B -m venv --copies "profiles/$profile/venv"
python3 -I -S -B recipes/fetch_locked_wheels.py "$profile"
bash recipes/install_and_inspect.sh "$profile"
python3 -I -S -B recipes/verify_upstream_artifacts.py "$profile"
python3 -I -S -B "$qualification/verify_runtime.py" --runtime "$destination" --profile "$profile" --output "receipts/$profile-preflight.json"
