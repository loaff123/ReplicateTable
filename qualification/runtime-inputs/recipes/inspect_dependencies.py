#!/usr/bin/env python3
"""Bounded dependency preparation inventories and tiny native/import smoke checks.
This intentionally does not import ReplicateTable or run its qualification.
"""
import hashlib, importlib, importlib.metadata as metadata, io, json, os, pathlib, re, stat, sys, sysconfig, zipfile
ROOT=pathlib.Path(__file__).resolve().parent.parent; PROFILE=sys.argv[1]
THREAD_KEYS=('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS','BLIS_NUM_THREADS')
assert all(os.environ.get(k)=='1' for k in THREAD_KEYS),'thread limits required before imports'
PINS=dict(line.strip().split('==') for line in (ROOT/'recipes/requirements-qualification.txt').read_text().splitlines() if line.strip())
PINS['pip']={'public312':'25.0.1','public313':'25.1.1'}[PROFILE]
normalize=lambda x:re.sub('[-_.]+','-',x).lower()
all_dist={normalize(d.metadata['Name']):d.version for d in metadata.distributions()}
assert all_dist==PINS,('installed version closure mismatch',all_dist,PINS)
SITE=pathlib.Path(sysconfig.get_path('purelib')).resolve()
PAYLOADS={'numpy':['numpy','numpy.libs'],'pandas':['pandas'],'xarray':['xarray'],'pint':['pint'],'h5py':['h5py','h5py.libs'],'h5netcdf':['h5netcdf'],'flexcache':['flexcache'],'flexparser':['flexparser'],'platformdirs':['platformdirs'],'typing-extensions':['typing_extensions.py'],'packaging':['packaging'],'python-dateutil':['dateutil'],'pytz':['pytz'],'tzdata':['tzdata'],'six':['six.py']}
IMPORTS={'numpy':'numpy','pandas':'pandas','xarray':'xarray','pint':'pint','h5py':'h5py','h5netcdf':'h5netcdf','flexcache':'flexcache','flexparser':'flexparser','platformdirs':'platformdirs','typing-extensions':'typing_extensions','packaging':'packaging','python-dateutil':'dateutil','pytz':'pytz','tzdata':'tzdata','six':'six','pint-xarray':'pint_xarray','build':'build','pyproject-hooks':'pyproject_hooks','wheel':'wheel'}
ARTIFACTS={r['name']:r for r in json.loads((ROOT/'receipts'/f'{PROFILE}-wheel-artifacts.json').read_text())}
def hashfile(p):
 s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_size<=128*1024*1024
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(65536):h.update(b)
 assert p.stat().st_size==s.st_size
 return {'sha256':h.hexdigest(),'size_bytes':s.st_size}
def summary(items):
 encoded=(json.dumps(items,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode()
 return {'sha256':hashlib.sha256(encoded).hexdigest(),'file_count':len(items),'size_bytes':sum(v['size_bytes'] for v in items.values())}
def selected(root,payload=True):
 assert root.exists() and not root.is_symlink()
 if root.is_file():yield root;return
 dirs_seen=0;files_seen=0
 for base,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=sorted(d for d in dirs if d!='__pycache__');dirs_seen+=1;assert dirs_seen<=512
  for d in dirs:assert not (pathlib.Path(base)/d).is_symlink()
  for name in sorted(files):
   if name.endswith(('.pyc','.pyo')):continue
   p=pathlib.Path(base)/name;assert not p.is_symlink();files_seen+=1;assert files_seen<=2048
   yield p
inventories={}; public={};origin={};total_files=0;total_bytes=0
for name,roots in PAYLOADS.items():
 dist=metadata.distribution(name);distinfo=pathlib.Path(dist._path).resolve();assert distinfo.parent==SITE
 payload={p.relative_to(SITE).as_posix():hashfile(p) for root in roots for p in selected(SITE/root)}
 meta={}
 for p in selected(distinfo):
  rel=p.relative_to(distinfo).as_posix()
  if rel in ('METADATA','WHEEL','entry_points.txt','top_level.txt') or rel.startswith('licenses/') or p.name.lower().startswith(('license','notice','copying','copyright')):meta[rel]=hashfile(p)
 assert 'METADATA' in meta and 'WHEEL' in meta
 assert len(payload)<=2048 and len(meta)<=2048
 assert all(len(n.encode())<=128 for n in payload) and all(len(n.encode())<=128 for n in meta)
 with zipfile.ZipFile(ROOT/'downloads'/PROFILE/'wheels'/ARTIFACTS[name]['filename']) as z:
  expected={n for n in z.namelist() if not n.endswith('/') and not n.endswith(('.pyc','.pyo')) and '__pycache__' not in n.split('/') and any(n==root or n.startswith(root+'/') for root in roots)}
  assert expected==set(payload),('installed payload membership differs from wheel',name)
  for rel,data in payload.items():assert hashlib.sha256(z.read(rel)).hexdigest()==data['sha256'],('wheel/install payload mismatch',name,rel)
  for rel,data in meta.items():assert hashlib.sha256(z.read(distinfo.name+'/'+rel)).hexdigest()==data['sha256'],('wheel/install metadata mismatch',name,rel)
 inventories[name]={'payload':payload,'metadata':meta};public[name]={'version':dist.version,'payload':summary(payload),'metadata':summary(meta),'wheel_membership_and_bytes_match':True}
 origin[name]={'dist_info':str(distinfo),'payload_roots':[str(SITE/r) for r in roots]}
 total_files+=len(payload)+len(meta);total_bytes+=sum(x['size_bytes'] for x in payload.values())+sum(x['size_bytes'] for x in meta.values())
modules={name:importlib.import_module(module) for name,module in IMPORTS.items()}
imports={}
for name,m in modules.items():
 p=pathlib.Path(m.__file__).resolve();assert p.is_relative_to(SITE),(name,'module outside venv')
 assert m.__spec__.origin and pathlib.Path(m.__spec__.origin).resolve()==p,(name,'spec/file mismatch')
 imports[name]={'module':m.__name__,'relative_origin':p.relative_to(SITE).as_posix(),'sha256':hashfile(p)['sha256']}
loaded_origins={}
for module_name,module in sorted(sys.modules.items()):
 if module_name.split('.')[0] not in {m.split('.')[0] for m in IMPORTS.values()}:continue
 path=getattr(module,'__file__',None)
 if path:
  p=pathlib.Path(path).resolve();assert p.is_relative_to(SITE),(module_name,'dependency submodule outside venv')
  loaded_origins[module_name]=p.relative_to(SITE).as_posix()
np=modules['numpy'];pd=modules['pandas'];xr=modules['xarray'];pint=modules['pint'];h5py=modules['h5py'];h5netcdf=modules['h5netcdf']
assert float(np.dot(np.array([1.,2.,3.]),np.array([3.,2.,1.])))==10.
assert pd.Series([1,2,3]).sum()==6
assert float(xr.DataArray([1.,2.,3.],dims='x').mean())==2.
u=pint.UnitRegistry();assert (1*u.meter).to('centimeter').magnitude==100
with h5py.File('preparation-only-memory.h5','w',driver='core',backing_store=False) as f:
 f.create_dataset('x',data=np.array([1,2,3]));assert f['x'][:].tolist()==[1,2,3]
buffer=io.BytesIO()
with h5netcdf.File(buffer,'w') as f:
 f.dimensions={'x':3};f.create_variable('values',('x',),data=np.array([1.,2.,3.]));assert f.variables['values'][:].tolist()==[1.,2.,3.]
quantified=xr.DataArray([1.,2.],dims='x',attrs={'units':'meter'}).pint.quantify()
assert quantified.pint.to('centimeter').data.magnitude.tolist()==[100.,200.]
report={'profile':PROFILE,'status':'preparation checks passed','scope':'dependency inventories, exact versions, wheel membership and bytes, origin checks, tiny native/import smoke only; no product imports or qualification','installed_distributions':all_dist,'runtime_dependencies':public,'runtime_inventory_occurrences':total_files,'runtime_inventory_bytes':total_bytes,'top_level_imports':imports,'loaded_dependency_module_origins':loaded_origins,'thread_environment':{k:os.environ[k] for k in THREAD_KEYS},'smoke_checks':['numpy dot 3 values','pandas sum 3 values','xarray mean 3 values','stock Pint meter to centimeter','h5py in-memory dataset 3 values','h5netcdf in-memory dataset 3 values','pint-xarray conversion 2 values'],'native_versions':{'hdf5':h5py.version.hdf5_version,'h5py':h5py.version.version}}
for filename,data in [(f'{PROFILE}-dependency-preparation.json',report),(f'{PROFILE}-dependency-inventories.json',inventories),(f'{PROFILE}-dependency-origins-private.json',origin)]:
 (ROOT/'receipts'/filename).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
print(json.dumps({'profile':PROFILE,'status':report['status'],'installed_distribution_count':len(all_dist),'runtime_dependency_count':len(PAYLOADS),'runtime_inventory_occurrences':total_files,'runtime_inventory_bytes':total_bytes,'smoke_check_count':len(report['smoke_checks'])},sort_keys=True))
