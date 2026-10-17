#!/usr/bin/env python3
"""Fresh upstream metadata, wheel RECORD and local license checks; no product import.
Run after reproduce.sh. Does not modify pins, downloaded archives or profiles.
"""
import base64,concurrent.futures,csv,email,hashlib,io,json,pathlib,sys,time,urllib.request,zipfile
ROOT=pathlib.Path(__file__).resolve().parent.parent
PROFILE=sys.argv[1];assert PROFILE in ('public312','public313')
RELEASE={'public312':'20260924','public313':'20250723'}[PROFILE]
def sha(data):return hashlib.sha256(data).hexdigest()
def write(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
def fetch(url):
 assert url.startswith(('https://api.github.com/','https://pypi.org/'))
 req=urllib.request.Request(url,headers={'User-Agent':'ReplicateTable-runtime-preparation'})
 with urllib.request.urlopen(req,timeout=45) as f:
  assert f.geturl().startswith(('https://api.github.com/','https://pypi.org/'))
  data=f.read(16*1024*1024+1);assert len(data)<=16*1024*1024
 return data,json.loads(data)
def hashfile(p):
 h=hashlib.sha256();size=0
 with p.open('rb') as f:
  while b:=f.read(65536):h.update(b);size+=len(b)
 return h.hexdigest(),size
meta=json.loads((ROOT/'metadata'/f'github-release-{RELEASE}-selected.json').read_text());asset=meta['assets'][0]
raw,current=fetch(asset['url'])
for k in ('name','size','digest','browser_download_url'):assert current[k]==asset[k],('upstream release asset changed',k)
archive=ROOT/'downloads'/asset['name'];digest,length=hashfile(archive);assert digest==asset['digest'].split(':')[1] and length==asset['size']
write(ROOT/'receipts'/f'{PROFILE}-fresh-upstream-interpreter.json',{'profile':PROFILE,'metadata_url':asset['url'],'release_url':meta['release']['html_url'],'asset_url':asset['browser_download_url'],'filename':asset['name'],'sha256':digest,'size_bytes':length,'fresh_public_metadata_sha256':sha(raw),'retrieved_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'fresh_asset_name_digest_size_url_verified':True,'scope':'fresh preparation only; no inherited product qualification'})
records=json.loads((ROOT/'receipts'/f'{PROFILE}-wheel-artifacts.json').read_text())
def verify(r):
 url=r['pypi_metadata_url'];raw,data=fetch(url);matches=[x for x in data['urls'] if x['filename']==r['filename']];assert len(matches)==1
 x=matches[0];assert x['size']==r['size_bytes'] and x['digests']['sha256']==r['sha256'] and x['url']==r['url'] and not x['yanked']
 p=ROOT/'downloads'/PROFILE/'wheels'/r['filename'];digest,length=hashfile(p);assert digest==r['sha256'] and length==r['size_bytes']
 licenses=[]
 with zipfile.ZipFile(p) as z:
  names=z.namelist();regular={n for n in names if not n.endswith('/')};assert len(names)==len(set(names))
  metas=[n for n in names if n.count('/')==1 and n.endswith('.dist-info/METADATA')];assert len(metas)==1
  prefix=metas[0].rsplit('/',1)[0];metadata_bytes=z.read(metas[0]);m=email.message_from_bytes(metadata_bytes)
  assert sha(metadata_bytes)==r['metadata_sha256'] and m['Version']==r['version']
  assert sha(z.read(prefix+'/WHEEL'))==r['wheel_metadata_sha256']
  record_bytes=z.read(prefix+'/RECORD');assert sha(record_bytes)==r['record_sha256'];rows=list(csv.reader(io.StringIO(record_bytes.decode('utf-8'))));seen=set();hashed=0;unhashed=[]
  for n,h,s in rows:
   assert n not in seen and n in regular;seen.add(n);b=z.read(n)
   if s:assert int(s)==len(b)
   if h:
    alg,value=h.split('=',1);assert alg=='sha256';assert base64.urlsafe_b64encode(hashlib.sha256(b).digest()).rstrip(b'=').decode()==value;hashed+=1
   else:unhashed.append(n)
  assert regular==seen and unhashed==[prefix+'/RECORD'] and hashed==r['record_hashes_verified']
  for item in r['licenses']:
   n=item['name'];pp=pathlib.PurePosixPath(n);assert not pp.is_absolute() and '..' not in pp.parts and '\\' not in n
   b=z.read(n);assert len(b)==item['size_bytes'] and sha(b)==item['sha256'];dst=ROOT/'licenses'/PROFILE/r['filename']/n;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b)
   licenses.append({'relative_archive_member':n,'sha256':sha(b),'size_bytes':len(b)})
 return {'name':r['name'],'version':r['version'],'filename':r['filename'],'sha256':digest,'size_bytes':length,'url':r['url'],'pypi_metadata_url':url,'fresh_public_metadata_sha256':sha(raw),'fresh_public_filename_digest_size_url_verified':True,'yanked':False,'requires_python':x['requires_python'],'record_hashes_verified':hashed,'complete_record_member_coverage':True,'licenses_preserved_locally':licenses,'wheel_tags':r['wheel_tags']}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:verified=sorted(pool.map(verify,records),key=lambda x:x['name'])
assert len(verified)==21
write(ROOT/'receipts'/f'{PROFILE}-fresh-wheel-verification.json',{'profile':PROFILE,'scope':'new-run artifact verification only; no inherited product qualification','verified_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'package_count':21,'license_file_occurrences':sum(len(r['licenses_preserved_locally']) for r in verified),'wheels':verified})
interpreter=[];runtime=ROOT/'profiles'/PROFILE/'python'
for p in runtime.rglob('*'):
 if p.is_symlink():continue
 if p.is_file() and (p.name.lower().startswith(('license','copying','copyright','notice')) or any(c.lower()=='licenses' for c in p.relative_to(runtime).parts[:-1])):
  digest,size=hashfile(p);rel=p.relative_to(runtime);dest=ROOT/'licenses'/PROFILE/'interpreter'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes());interpreter.append({'relative_path':rel.as_posix(),'sha256':digest,'size_bytes':size})
write(ROOT/'receipts'/f'{PROFILE}-interpreter-licenses.json',{'profile':PROFILE,'license_files':sorted(interpreter,key=lambda x:x['relative_path']),'complete_upstream_archive_retained_locally':True,'redistribution_authorized':False})
print(json.dumps({'profile':PROFILE,'fresh_upstream_archive_check':True,'fresh_upstream_wheel_checks':len(verified),'wheel_record_checks':len(verified),'wheel_license_occurrences_preserved':sum(len(r['licenses_preserved_locally']) for r in verified),'interpreter_license_files_preserved':len(interpreter)}))
