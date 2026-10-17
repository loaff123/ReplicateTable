#!/usr/bin/env python3
"""Validate recorded loaded-file origins from the standalone Python probe.
This is intentionally narrower than the product's complete live import checks.
"""
import hashlib,json,pathlib,sys,zipfile
ROOT=pathlib.Path(__file__).resolve().parent.parent
for profile,minor in [('public312','3.12'),('public313','3.13')]:
 for phase in ('before','after'):
  private=json.loads((ROOT/'receipts'/f'{profile}-{phase}-origin-private.json').read_text())
  stdlib=pathlib.Path(private['stdlib']);assert stdlib==ROOT/'profiles'/profile/'python/lib'/('python'+minor)
  site=ROOT/'profiles'/profile/'venv/lib'/('python'+minor)/'site-packages'
  public={};tooling={}
  for name,path in private['loaded_stdlib_origins'].items():
   p=pathlib.Path(path)
   if name=='__main__':assert p==ROOT/'recipes/inspect_python.py';continue
   if p.is_relative_to(stdlib):
    rel=p.relative_to(stdlib)
    for end in range(1,len(rel.parts)+1):assert not (stdlib/pathlib.Path(*rel.parts[:end])).is_symlink()
    assert p.is_file();public[name]=rel.as_posix()
   else:
    assert phase=='after' and name=='_distutils_hack' and p==site/'_distutils_hack/__init__.py',(profile,name,'unexpected recorded file origin')
    wheel=[r for r in json.loads((ROOT/'receipts'/f'{profile}-wheel-artifacts.json').read_text()) if r['name']=='setuptools'][0]
    with zipfile.ZipFile(ROOT/'downloads'/profile/'wheels'/wheel['filename']) as z:assert p.read_bytes()==z.read('_distutils_hack/__init__.py')
    tooling[name]={'relative_origin':'_distutils_hack/__init__.py','distribution':'setuptools','version':wheel['version']}
  result={'profile':profile,'phase':phase,'scope':'file-origin checks from standalone Python probe, not complete live product import validation; main probe script excluded; built-in/frozen originless modules not enumerated here','stdlib_file_origins':public,'tooling_file_origins':tooling,'passed':True}
  (ROOT/'receipts'/f'{profile}-{phase}-origin-checks.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
  print(profile,phase,len(public),'stdlib file origins validated',len(tooling),'pinned tooling origins')
