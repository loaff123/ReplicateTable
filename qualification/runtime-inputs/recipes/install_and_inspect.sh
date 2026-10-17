#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
profile="$1"
case "$profile" in public312|public313) ;; *) exit 2;; esac
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH PYTHONHOME
p="profiles/$profile/venv/bin/python"
"$p" -I -B -m pip --isolated --disable-pip-version-check --no-cache-dir install --no-index --find-links "downloads/$profile/wheels" --only-binary=:all: --require-hashes --no-deps --no-compile --force-reinstall --report "receipts/$profile-install-private.json" -r "recipes/requirements-$profile-all.lock" >"logs/$profile-install.stdout" 2>"logs/$profile-install.stderr"
"$p" -I -B -m pip --isolated --disable-pip-version-check --no-cache-dir check >"logs/$profile-pip-check.stdout" 2>"logs/$profile-pip-check.stderr"
"$p" -I -B -m pip --isolated --disable-pip-version-check --no-cache-dir list --format=json >"receipts/$profile-installed-distributions.json"
"$p" -I -B recipes/inspect_dependencies.py "$profile" >"logs/$profile-dependency-inspection.stdout" 2>"logs/$profile-dependency-inspection.stderr"
"$p" -I -B recipes/inspect_python.py "$profile" after >"logs/$profile-python-after.stdout" 2>"logs/$profile-python-after.stderr"
python3 recipes/tree_snapshot.py "profiles/$profile/python" "receipts/$profile-interpreter-after.json" >"logs/$profile-interpreter-after.stdout"
python3 recipes/tree_snapshot.py "profiles/$profile/venv" "receipts/$profile-venv-after.json" >"logs/$profile-venv-after.stdout"
cat "logs/$profile-pip-check.stdout" "logs/$profile-dependency-inspection.stdout" "logs/$profile-python-after.stdout"
