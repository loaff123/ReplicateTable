"""Unpatched real public workflow and refusal checks, in one isolated process.

The installed-wheel branch never adds the checkout, src, or tests to sys.path.
The demonstration is copied outside checkout; only its public API is executed.
"""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys
import sysconfig
import time

def require(value, message):
    if not value:
        raise AssertionError(message)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lane', choices=('source', 'wheel'), required=True)
    parser.add_argument('--source-package', type=Path)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--example', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode and not sys.flags.optimize,
            'Qualification requires -I -B and assertions enabled')
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS',
                'NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS','BLIS_NUM_THREADS'):
        require(os.environ.get(key) == '1', 'Missing native-thread bound: '+key)
    if args.lane == 'source':
        require(args.source_package is not None, 'Source lane requires explicit package root')
        root = args.source_package.resolve()
        sys.path.insert(0, str(root.parent))
    else:
        require(args.source_package is None, 'Wheel lane must not receive a source package root')
        root = Path(sysconfig.get_path('purelib')).resolve()/'replicatetable'
    expected = json.loads(args.manifest.read_text())
    actual = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(root.rglob('*.py'))}
    require(actual == expected, 'Product payload differs from the locked candidate source')
    import replicatetable as rt
    require(Path(rt.__file__).resolve() == root/'__init__.py', 'Wrong initial product origin')
    if args.lane == 'wheel':
        dist = importlib.metadata.distribution('replicatetable')
        require(Path(dist.locate_file('replicatetable')).resolve() == root, 'Wrong wheel distribution origin')
        require(dist.version == rt.__version__, 'Wheel metadata version mismatch')
        require(not any(ep.group == 'console_scripts' for ep in dist.entry_points), 'Unexpected CLI entry point')
    require(importlib.util.find_spec('replicatetable.__main__') is None, 'Unexpected file/CLI support')
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {'lane': args.lane, 'status': 'running', 'checks': [], 'skipped': 0,
               'platform': dict(zip(os.uname()._fields, os.uname())) if hasattr(os.uname(), '_fields')
                    else {'system': os.uname().sysname, 'kernel': os.uname().release, 'machine': os.uname().machine},
               'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    def save():
        (args.output/'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
    save()
    try:
        demo = runpy.run_path(str(args.example), run_name='replicatetable_public_example')
        source, plan, result = demo['run'](args.output/'exports')
        receipt['checks'].extend(['public_eager_memory_example', 'hand_derived_and_xarray_controls',
                                  'saved_plan_result_reload_and_replay', 'render_report', 'explain_row',
                                  'changed_source_refusal'])
        exports = args.output/'exports'
        require(set(p.name for p in exports.iterdir()) == {
            'recipe.json', 'plan.json', 'result.json', 'report.html', 'explanation.json'},
            'Unexpected or missing loose exports')
        require((exports/'report.html').read_bytes().startswith(b'<!doctype html>'), 'Missing HTML document')
        trace = json.loads((exports/'explanation.json').read_text())
        require(trace['assurance'] == 'Exact source-bound same-engine replay completed before tracing.',
                'Unexpected explanation assurance')
        from replicatetable import _native_fs_profile
        selected = _native_fs_profile._selected_profile()
        require(_native_fs_profile._PROFILE_SUPPORTED == selected, 'Native profile selection was altered')
        before = {p.name for p in args.output.iterdir()}
        destination = args.output/'unsupported.bundle'
        try:
            rt.write_bundle(plan, result, destination)
        except rt.Refusal as error:
            require(error.code == 'unsafe_path', 'Wrong native refusal: '+error.code)
            require(error.message == _native_fs_profile._PROFILE_MESSAGE, 'Wrong native refusal boundary')
            require(not error.envelope.committed and error.envelope.receipt is None,
                    'Refused output reported a commit')
            receipt['native_refusal'] = {'code': error.code, 'message': error.message,
                'exact_native_kernel_profile_selected': selected,
                'boundary': 'filesystem' if selected else 'kernel_profile',
                'committed': False}
        else:
            raise AssertionError('Expected unsupported native output parent; actual bundle success is a different profile')
        require({p.name for p in args.output.iterdir()} == before, 'Native refusal left filesystem entries')
        receipt['checks'].append('unmodified_native_bundle_refusal_no_output')
        try:
            rt.snapshot_dataset(exports/'result.json')
        except rt.Refusal as error:
            require(error.code == 'invalid_source', 'Wrong file-source refusal: '+error.code)
            receipt['file_source_refusal'] = error.code
        else:
            raise AssertionError('File path unexpectedly accepted as eager dataset')
        receipt['checks'].extend(['file_path_is_not_eager_source', 'no_cli_entrypoint'])
        origins = {}
        for name, module in sorted(sys.modules.items()):
            if name != 'replicatetable' and not name.startswith('replicatetable.'):
                continue
            path = Path(module.__file__).resolve()
            require(path.is_relative_to(root), 'Product escaped selected origin: '+name)
            relative = path.relative_to(root).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            require(digest == expected[relative], 'Imported product file changed: '+name)
            require(Path(module.__spec__.origin).resolve() == path, 'Spec/origin mismatch: '+name)
            origins[name] = {'relative_path': relative, 'sha256': digest}
        receipt.update(status='passed', product_origins=origins, product_payload_files=len(actual),
                       assertions_enabled=True, scientific_and_native_gates_patched=False,
                       full_regression_suite=False,
                       artifacts={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in exports.iterdir()})
    except BaseException as error:
        receipt.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        receipt['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        save()
    print(json.dumps({'lane': args.lane, 'status': receipt['status'], 'checks': len(receipt['checks']),
                      'skipped': 0, 'native_refusal': receipt['native_refusal']}, sort_keys=True))

if __name__ == '__main__':
    main()
