#!/usr/bin/env python3
"""Reacquire the already-selected public wheels exactly; never resolve versions."""
import concurrent.futures, hashlib, json, pathlib, subprocess, sys, zipfile, stat
ROOT=pathlib.Path(__file__).resolve().parent.parent
PROFILE=sys.argv[1]
assert PROFILE in ('public312','public313')
RECORDS=json.loads((ROOT/'receipts'/f'{PROFILE}-wheel-artifacts.json').read_text())
DEST=ROOT/'downloads'/PROFILE/'wheels';DEST.mkdir(parents=True,exist_ok=True)
def acquire(r):
 name=r['filename'];assert pathlib.PurePosixPath(name).name==name and name.endswith('.whl')
 assert r['url'].startswith('https://files.pythonhosted.org/')
 dest=DEST/name;assert not dest.exists(),'refuse overwrite retained download'
 log=ROOT/'logs'/f'{PROFILE}-locked-{r["name"]}.log'
 with log.open('w') as f:
  p=subprocess.run(['curl','--fail','--location','--max-time','180','--proto','=https','--proto-redir','=https','--max-filesize',str(r['size_bytes']),r['url'],'-o',str(dest)],stdout=f,stderr=subprocess.STDOUT)
 assert p.returncode==0,(r['name'],'download failed; partial bytes retained')
 assert dest.stat().st_size==r['size_bytes']
 h=hashlib.sha256()
 with dest.open('rb') as f:
  while b:=f.read(65536):h.update(b)
 assert h.hexdigest()==r['sha256'],(r['name'],'digest mismatch')
 # Check metadata before any installer executes this previously verified archive.
 seen=set();expanded=0
 with zipfile.ZipFile(dest) as z:
  for i in z.infolist():
   n=i.filename.rstrip('/');assert n and '\\' not in n and not n.startswith('/') and all(c not in ('','.','..') for c in n.split('/'))
   assert n not in seen and len(n.encode())<=512;seen.add(n);assert len(seen)<=50000
   assert not stat.S_ISLNK(i.external_attr>>16)
   assert i.file_size<=128*1024*1024;expanded+=i.file_size;assert expanded<=512*1024*1024
 return {'name':r['name'],'filename':name,'sha256':h.hexdigest(),'size_bytes':dest.stat().st_size,'download_exit':p.returncode}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:receipts=list(pool.map(acquire,RECORDS))
(ROOT/'receipts'/f'{PROFILE}-locked-reacquisition.json').write_text(json.dumps(receipts,sort_keys=True,indent=2)+'\n')
