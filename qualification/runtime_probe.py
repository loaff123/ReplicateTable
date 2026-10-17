"""Live preparation-only dependency origins under the selected isolated Python."""
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys

site, stdlib, receipt = map(Path, sys.argv[1:])
if not sys.flags.isolated or not sys.dont_write_bytecode or sys.flags.optimize:
    raise RuntimeError('Requires -I -B without optimization')
pins = json.loads(receipt.read_text())
for pin in pins:
    if importlib.metadata.version(pin['name']) != pin['version']:
        raise RuntimeError('Installed version differs: '+pin['name'])
roots = ('numpy','pandas','xarray','pint','h5py','h5netcdf','flexcache','flexparser',
         'platformdirs','typing_extensions','packaging','dateutil','pytz','tzdata','six')
for root in roots:
    importlib.import_module(root)
origins = {}
for name, module in sorted(sys.modules.items()):
    filename = getattr(module, '__file__', None)
    if name.split('.')[0] not in roots or filename is None:
        continue
    path = Path(filename).resolve()
    if not path.is_relative_to(site) or Path(module.__spec__.origin).resolve() != path:
        raise RuntimeError('Dependency origin mismatch: '+name)
    origins[name] = {'relative_path': path.relative_to(site).as_posix(),
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
if Path(sys.base_prefix).resolve() != stdlib.parents[1]:
    raise RuntimeError('Wrong base interpreter prefix')
print(json.dumps({'dependency_origins': origins, 'distribution_versions_checked': len(pins),
                  'isolated': True, 'bytecode_disabled': True, 'product_imported': False}, sort_keys=True))
