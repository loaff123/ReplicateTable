#!/usr/bin/env python3
"""Standalone preparation inspection, not ReplicateTable qualification."""
import hashlib, json, os, pathlib, platform, struct, sys, sysconfig
ROOT=pathlib.Path(__file__).resolve().parent.parent
profile=sys.argv[1]; phase=sys.argv[2]
def artifact(p):
 h=hashlib.sha256();n=0
 with p.open('rb') as f:
  while b:=f.read(65536):h.update(b);n+=len(b)
 return {'sha256':h.hexdigest(),'size_bytes':n}
stdlib=pathlib.Path(sysconfig.get_path('stdlib')).resolve(); entries={};dirs_count=0
for base,dirs,files in os.walk(stdlib,followlinks=False):
 dirs[:]=sorted(d for d in dirs if d not in ('site-packages','dist-packages','__pycache__') and not d.startswith('config-'))
 dirs_count+=1; assert dirs_count<=512
 for d in dirs:assert not (pathlib.Path(base)/d).is_symlink()
 for f in sorted(files):
  if f.startswith('_sysconfigdata_') or not (f.endswith('.py') or f.endswith('.so') or '.so.' in f):continue
  p=pathlib.Path(base)/f; assert not p.is_symlink() and p.is_file()
  rel=p.relative_to(stdlib).as_posix();assert len(rel.encode())<=128
  assert len(entries)<2048
  entries[rel]=artifact(p)
canonical=(json.dumps(entries,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
exe=pathlib.Path('/proc/self/exe').resolve(); core={};core_paths={}
for line in pathlib.Path('/proc/self/maps').read_text().splitlines():
 fields=line.split(None,5)
 if len(fields)==6 and fields[5].startswith('/') and pathlib.Path(fields[5]).name.startswith('libpython'):
  p=pathlib.Path(fields[5]); key=p.name
  assert key not in core_paths or core_paths[key]==str(p)
  core_paths[key]=str(p); core[key]=artifact(p)
abi={'cache_tag':sys.implementation.cache_tag,'soabi':sysconfig.get_config_var('SOABI'),'abiflags':sys.abiflags,'multiarch':sysconfig.get_config_var('MULTIARCH'),'platform':sys.platform,'machine':platform.machine(),'pointer_bits':struct.calcsize('P')*8,'byteorder':sys.byteorder,'debug':bool(sysconfig.get_config_var('Py_DEBUG')),'gil_disabled':bool(sysconfig.get_config_var('Py_GIL_DISABLED')),'optimization':sys.flags.optimize}
public={'profile':profile,'phase':phase,'scope':'preparation only, not product runtime binding or qualification','python':{'implementation':sys.implementation.name,'version':platform.python_version(),'sys_version':sys.version,'build':platform.python_build(),'compiler':platform.python_compiler(),'abi':abi,'executable':artifact(exe),'core_libraries':core,'stdlib_code':{'sha256':hashlib.sha256(canonical).hexdigest(),'file_count':len(entries),'size_bytes':sum(x['size_bytes'] for x in entries.values())}},'stdlib_directory_count':dirs_count}
private={'executable':str(exe),'sys_executable':sys.executable,'sys_prefix':sys.prefix,'sys_base_prefix':sys.base_prefix,'sys_path':sys.path,'stdlib':str(stdlib),'core_paths':core_paths,'loaded_stdlib_origins':{name:getattr(mod,'__file__',None) for name,mod in sorted(sys.modules.items()) if getattr(mod,'__file__',None)}}
for name,data in [(f'{profile}-{phase}-python.json',public),(f'{profile}-{phase}-origin-private.json',private),(f'{profile}-{phase}-stdlib-inventory.json',entries)]:
 (ROOT/'receipts'/name).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
print(json.dumps(public,sort_keys=True))
