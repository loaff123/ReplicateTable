#!/usr/bin/env bash
# Run only in a fresh copy of the public recipe and text receipts, on Linux x86_64.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs downloads profiles receipts metadata
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH PYTHONHOME
for spec in 'public312 3.12' 'public313 3.13'; do
 read -r profile minor <<<"$spec"
 python3 recipes/acquire_interpreters.py "$profile"
 python3 recipes/tree_snapshot.py "profiles/$profile/python" "receipts/$profile-interpreter-before.json"
 "profiles/$profile/python/bin/python$minor" -I -B recipes/inspect_python.py "$profile" before
 "profiles/$profile/python/bin/python$minor" -I -B -m venv --copies "profiles/$profile/venv"
 python3 recipes/fetch_locked_wheels.py "$profile"
 bash recipes/install_and_inspect.sh "$profile"
done

python3 recipes/verify_preparation.py
python3 recipes/verify_prepared_origins.py
python3 recipes/check_inventory_feasibility.py
