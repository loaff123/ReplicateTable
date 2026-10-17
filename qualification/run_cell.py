"""Durable source/wheel cell supervisor; run with trusted bootstrap Python.

One immutable per-cell output directory, terminal JSON even after child failure,
120-second liveness, and a bounded wall time. A killed supervisor leaves running,
which must be reported as incomplete, never converted into a passing receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

THREADS = ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS',
           'NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS','BLIS_NUM_THREADS')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--profile', choices=('public312','public313'), required=True)
    parser.add_argument('--lane', choices=('source','wheel'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout-seconds', type=int, default=1200)
    parser.add_argument('--source-root', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--frozen', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--reuse-wheel-cell', type=Path,
                        help='Reuse a previously built/installed cell after fresh artifact/payload checks')
    args = parser.parse_args()
    source = (args.source_root or Path(__file__).resolve().parents[1]).resolve()
    output = args.output.resolve()
    if output.is_relative_to(source):
        raise RuntimeError('Cell output must be outside the source checkout')
    if not args.frozen:
        output.mkdir(parents=True, exist_ok=False)
        frozen = output/'harness'
        shutil.copytree(source/'qualification', frozen/'qualification')
        (frozen/'examples').mkdir()
        shutil.copyfile(source/'examples/eager_memory.py', frozen/'examples/eager_memory.py')
        hashes = {p.relative_to(frozen).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(frozen.rglob('*')) if p.is_file()}
        (output/'harness-manifest.json').write_text(json.dumps(hashes, indent=2, sort_keys=True)+'\n')
        # The process that supervises the cell now runs the snapshotted bytes.
        os.execv(sys.executable, [sys.executable, '-I', '-S', '-B',
                 str(frozen/'qualification/run_cell.py'), *sys.argv[1:],
                 '--frozen', '--source-root', str(source)])
    qualification = Path(__file__).resolve().parent
    if qualification != output/'harness/qualification':
        raise RuntimeError('Frozen supervisor is outside this cell snapshot')
    frozen = output/'harness'
    hashes = json.loads((output/'harness-manifest.json').read_text())
    actual_hashes = {p.relative_to(frozen).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(frozen.rglob('*')) if p.is_file()}
    if actual_hashes != hashes:
        raise RuntimeError('Frozen harness inventory differs before execution')
    runtime = args.runtime.resolve()
    python = runtime/'profiles'/args.profile/'venv/bin/python'
    env = {k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
    env.update({k:'1' for k in THREADS})
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    start = time.monotonic()
    receipt = {'profile': args.profile, 'lane': args.lane, 'status': 'running',
               'scope': 'portable real-workflow qualification; not full regression or native success',
               'execution_environment': 'github-actions' if env.get('GITHUB_ACTIONS') == 'true' else 'local',
               'github_run_id': env.get('GITHUB_RUN_ID'), 'github_sha': env.get('GITHUB_SHA'),
               'harness_file_sha256': hashes,
               'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'commands': []}
    def save():
        receipt['elapsed_seconds'] = round(time.monotonic()-start, 3)
        temp = output/'cell.json.tmp'
        temp.write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
        temp.replace(output/'cell.json')
    def run(label, command):
        record = {'label': label, 'command': [str(v) for v in command], 'status': 'running'}
        receipt['commands'].append(record)
        save()
        with (output/(label+'.log')).open('w') as log:
            child = subprocess.Popen(record['command'], cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT)
            record['pid'] = child.pid
            last = time.monotonic()
            try:
                while child.poll() is None:
                    time.sleep(1)
                    now = time.monotonic()
                    if now-start > args.timeout_seconds:
                        child.terminate()
                        try: child.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            child.kill(); child.wait()
                        raise TimeoutError('Cell exceeded its explicit wall-clock budget')
                    if now-last >= 120:
                        receipt['last_liveness_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        save()
                        print(json.dumps({'liveness': label, 'profile': args.profile, 'lane': args.lane,
                                          'elapsed_seconds': receipt['elapsed_seconds']}), flush=True)
                        last = now
            finally:
                if child.poll() is None:
                    child.terminate(); child.wait(timeout=10)
                record['exit_code'] = child.returncode
                record['status'] = 'passed' if child.returncode == 0 else 'failed'
                save()
        if child.returncode:
            raise RuntimeError(label+' failed; inspect '+label+'.log')
    save()
    try:
        run('runtime-preflight', [sys.executable, '-I', '-S', '-B', qualification/'verify_runtime.py',
            '--runtime', runtime, '--profile', args.profile, '--output', output/'runtime-preflight.json'])
        product = source/'src/replicatetable'
        manifest = {p.relative_to(product).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(product.rglob('*.py'))}
        (output/'product-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
        copied_example = output/'eager_memory.py'
        shutil.copyfile(frozen/'examples/eager_memory.py', copied_example)
        receipt['example_sha256'] = hashlib.sha256(copied_example.read_bytes()).hexdigest()
        test_python = python
        if args.lane == 'wheel' and args.reuse_wheel_cell:
            prior = args.reuse_wheel_cell.resolve()
            previous = json.loads((prior/'cell.json').read_text())
            if previous['profile'] != args.profile or previous['lane'] != 'wheel':
                raise RuntimeError('Wrong profile/lane for reused wheel')
            for label in ('build-sdist-wheel', 'create-wheel-venv', 'install-locked-dependencies',
                          'install-product-wheel', 'wheel-pip-check'):
                if not any(c['label'] == label and c['status'] == 'passed' and c['exit_code'] == 0
                           for c in previous['commands']):
                    raise RuntimeError('Reused wheel has no successful '+label+' receipt')
            wheel = prior/'dist'/previous['wheel']['filename']
            if hashlib.sha256(wheel.read_bytes()).hexdigest() != previous['wheel']['sha256']:
                raise RuntimeError('Reused wheel artifact changed')
            with zipfile.ZipFile(wheel) as archive:
                payload = {n.removeprefix('replicatetable/'): hashlib.sha256(archive.read(n)).hexdigest()
                           for n in archive.namelist() if n.startswith('replicatetable/') and n.endswith('.py')}
            if payload != manifest:
                raise RuntimeError('Reused wheel does not match candidate source')
            test_python = prior/'wheel-venv/bin/python'
            receipt.update(wheel=previous['wheel'], reused_build_install_receipt_sha256=
                           hashlib.sha256((prior/'cell.json').read_bytes()).hexdigest())
        elif args.lane == 'wheel':
            # Build a copy so setuptools cannot leave egg-info/build files in the candidate.
            build_source = output/'build-source'
            shutil.copytree(source, build_source)
            run('build-sdist-wheel', [python, '-I', '-B', '-m', 'build', '--no-isolation',
                                     '--outdir', output/'dist', build_source])
            wheels = list((output/'dist').glob('*.whl'))
            if len(wheels) != 1:
                raise RuntimeError('Expected exactly one product wheel')
            wheel = wheels[0]
            with zipfile.ZipFile(wheel) as archive:
                installed = {name.removeprefix('replicatetable/'): hashlib.sha256(archive.read(name)).hexdigest()
                             for name in archive.namelist() if name.startswith('replicatetable/') and name.endswith('.py')}
            if installed != manifest:
                raise RuntimeError('Built wheel payload differs from candidate')
            receipt['wheel'] = {'filename': wheel.name, 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()}
            run('create-wheel-venv', [python, '-I', '-B', '-m', 'venv', '--copies', output/'wheel-venv'])
            test_python = output/'wheel-venv/bin/python'
            if test_python.is_symlink() or hashlib.sha256(test_python.read_bytes()).digest() != hashlib.sha256(python.read_bytes()).digest():
                raise RuntimeError('New wheel venv executable differs before first execution')
            run('install-locked-dependencies', [test_python, '-I', '-B', '-m', 'pip', '--isolated',
                '--disable-pip-version-check', '--no-cache-dir', 'install', '--no-index', '--find-links',
                runtime/'downloads'/args.profile/'wheels', '--require-hashes', '--no-deps', '--no-compile',
                '--only-binary=:all:', '-r', qualification/'runtime-inputs/recipes'/f'requirements-{args.profile}-all.lock'])
            run('install-product-wheel', [test_python, '-I', '-B', '-m', 'pip', '--isolated',
                '--disable-pip-version-check', '--no-cache-dir', 'install', '--no-index', '--no-deps', '--no-compile', wheel])
        if args.lane == 'wheel':
            # Trusted bootstrap verifies bytes before executing the wheel interpreter.
            run('wheel-runtime-preflight', [sys.executable, '-I', '-S', '-B', qualification/'verify_runtime.py',
                '--runtime', runtime, '--profile', args.profile, '--venv', test_python.parent.parent,
                '--output', output/'wheel-runtime-preflight.json'])
            run('wheel-pip-check', [test_python, '-I', '-B', '-m', 'pip', '--isolated', 'check'])
        command = [test_python, '-I', '-B', qualification/'portable_probe.py', '--lane', args.lane,
                   '--manifest', output/'product-manifest.json', '--example', copied_example, '--output', output/'probe']
        if args.lane == 'source':
            command.extend(['--source-package', product])
        # venv --copies must preserve the preflighted executable even in wheel mode.
        selected_executable_sha256 = hashlib.sha256(python.read_bytes()).hexdigest()
        if test_python.is_symlink() or hashlib.sha256(test_python.read_bytes()).hexdigest() != selected_executable_sha256:
            raise RuntimeError('Product probe executable differs from preflighted public profile')
        receipt['probe_executable_sha256'] = selected_executable_sha256
        run('portable-probe', command)
        probe = json.loads((output/'probe/receipt.json').read_text())
        if probe['status'] != 'passed' or probe['skipped'] != 0:
            raise RuntimeError('Probe did not provide a terminal zero-skip pass')
        current = {p.relative_to(product).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(product.rglob('*.py'))}
        if current != manifest:
            raise RuntimeError('Candidate product changed during cell')
        final_hashes = {p.relative_to(frozen).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(frozen.rglob('*')) if p.is_file()}
        if final_hashes != hashes:
            raise RuntimeError('Frozen harness changed during execution')
        receipt.update(status='passed', checks=len(probe['checks']), skipped=0, product_payload_unchanged=True,
                       harness_unchanged=True,
                       native_refusal=probe['native_refusal'], full_regression_suite=False)
    except BaseException as error:
        receipt.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        receipt['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        save()
    print(json.dumps({k:receipt[k] for k in ('profile','lane','status','elapsed_seconds','execution_environment')}), flush=True)

if __name__ == '__main__':
    main()
