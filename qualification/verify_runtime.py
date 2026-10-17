"""Check exact existing profile bytes before executing it, then live import origins.

Uses immutable selected input inventories, not a previous run's success flag.
This is preparation evidence, not product qualification or hosted execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

PINS = {
    'public312': ('3.12', 'edffa803e5c4d73a1357f7f2c6c9fd38e9693712b2c06793e6a5e5cc1090d03a'),
    'public313': ('3.13', '0eba26d5f04a3673ee264ca406ef286d5025da098c1a24987a8118c23d69153c'),
}

def artifact(path):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError('Expected regular non-symlink file: ' + str(path))
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(65536):
            h.update(chunk)
    return {'sha256': h.hexdigest(), 'size_bytes': path.stat().st_size}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--profile', choices=PINS, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--venv', type=Path, help='Check an isolated wheel venv against the same public profile')
    args = parser.parse_args()
    inputs = Path(__file__).resolve().parent/'runtime-inputs'
    runtime = args.runtime.resolve()
    profile = runtime/'profiles'/args.profile
    minor, expected = PINS[args.profile]
    venv = args.venv.resolve() if args.venv else profile/'venv'
    python = venv/'bin/python'
    result = {'profile': args.profile, 'status': 'running', 'scope': 'fresh preparation-only preflight',
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    try:
        for executable in (python, profile/'python/bin'/('python'+minor)):
            if artifact(executable)['sha256'] != expected:
                raise RuntimeError('Interpreter executable digest mismatch before execution')
        receipts = inputs/'receipts'
        wheels = json.loads((receipts/f'{args.profile}-wheel-artifacts.json').read_text())
        for wheel in wheels:
            if artifact(runtime/'downloads'/args.profile/'wheels'/wheel['filename']) != {
                    'sha256': wheel['sha256'], 'size_bytes': wheel['size_bytes']}:
                raise RuntimeError('Locked wheel artifact differs: '+wheel['name'])
        stdlib = profile/'python/lib'/('python'+minor)
        stdlib_inventory = json.loads((receipts/f'{args.profile}-after-stdlib-inventory.json').read_text())
        for name, expected_file in stdlib_inventory.items():
            if artifact(stdlib/name) != expected_file:
                raise RuntimeError('Selected standard library differs: '+name)
        site = venv/'lib'/('python'+minor)/'site-packages'
        dependency_inventory = json.loads((receipts/f'{args.profile}-dependency-inventories.json').read_text())
        count = 0
        for name, inventory in dependency_inventory.items():
            wheel = next(w for w in wheels if w['name'] == name)
            matches = [p for p in site.glob('*.dist-info') if p.name.lower().replace('_','-') ==
                       name.replace('_','-')+'-'+wheel['version']+'.dist-info']
            if len(matches) != 1:
                raise RuntimeError('Non-unique dependency metadata: '+name)
            for category, root in [('payload', site), ('metadata', matches[0])]:
                for relative, expected_file in inventory[category].items():
                    if artifact(root/relative) != expected_file:
                        raise RuntimeError('Selected dependency file differs: '+name+'/'+relative)
                    count += 1
        completed = subprocess.run([str(python), '-I', '-B', str(Path(__file__).with_name('runtime_probe.py')),
                                    str(site), str(stdlib), str(receipts/f'{args.profile}-wheel-artifacts.json')],
                                   text=True, capture_output=True, check=True)
        origins = json.loads(completed.stdout)
        result.update(status='passed', executable_sha256=artifact(python)['sha256'],
                      selected_stdlib_files=len(stdlib_inventory), dependency_file_occurrences=count,
                      locked_wheels=len(wheels), live_probe=origins)
    except BaseException as error:
        result.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        result['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'profile': args.profile, 'status': result['status'], 'dependency_file_occurrences': count}))

if __name__ == '__main__':
    main()
