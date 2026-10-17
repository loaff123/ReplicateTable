#!/usr/bin/env python3
"""Fresh public acquisition, bounded archive inspection, and isolated extraction.
Run from any directory using a trusted Python >=3.12; no product imports.
"""
import hashlib, json, os, pathlib, posixpath, stat, subprocess, sys, tarfile, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGETS = {
 'public312': {'release':'20260924','version':'3.12.14','size':34270188,'sha256':'269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41','executable_sha256':'edffa803e5c4d73a1357f7f2c6c9fd38e9693712b2c06793e6a5e5cc1090d03a'},
 'public313': {'release':'20250723','version':'3.13.5','size':35452245,'sha256':'f7ac16748be2674ec14df532a3e48d0c6f215017b537f14ca3feb837dbe86292','executable_sha256':'0eba26d5f04a3673ee264ca406ef286d5025da098c1a24987a8118c23d69153c'},
}
def write(path, value):
 path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while b:=f.read(65536):h.update(b)
 return h.hexdigest()
def audit(archive, profile):
 entries=[]; names={}; links=[]; total=0
 with tarfile.open(archive,'r:gz') as tf:
  for member in tf:
   n=member.name.rstrip('/')
   assert n and n.startswith('python/') or n=='python', ('root',n)
   assert len(n.encode())<=512 and not n.startswith('/') and '\\' not in n and all(p not in ('','.','..') for p in n.split('/')), ('path',n)
   assert n not in names, ('duplicate',n)
   assert len(entries)<50000, 'archive member bound'
   assert member.size<=256*1024*1024, ('member size',n)
   total+=member.size; assert total<=1024*1024*1024,'expanded byte bound'
   assert member.isfile() or member.isdir() or member.issym() or member.islnk(), ('type',n)
   assert not member.mode&0o6000, ('special mode',n)
   rec={'name':n,'size_bytes':member.size,'type':'file' if member.isfile() else 'directory' if member.isdir() else 'symlink' if member.issym() else 'hardlink','mode':member.mode}
   if member.issym() or member.islnk():
    link=member.linkname
    assert link and not link.startswith('/') and '\\' not in link, ('external link',n,link)
    target=posixpath.normpath(posixpath.join(posixpath.dirname(n),link) if member.issym() else link)
    assert target=='python' or target.startswith('python/'), ('escaping link',n,link)
    assert not n.startswith('python/lib/python'+TARGETS[profile]['version'].rsplit('.',1)[0]+'/'), ('stdlib link',n,link)
    rec.update(linkname=link,resolved_logical_target=target);links.append(rec)
   entries.append(rec);names[n]=rec
  for rec in entries:
   parts=rec['name'].split('/')
   for end in range(1,len(parts)):
    ancestor=names.get('/'.join(parts[:end]))
    assert ancestor is None or ancestor['type']=='directory', ('link ancestor',rec['name'])
  for rec in links:
   seen={rec['name']}; dest=rec['resolved_logical_target']
   while True:
    assert dest in names, ('missing link target',dest)
    assert dest not in seen, ('link cycle',dest)
    seen.add(dest); target=names[dest]
    if 'resolved_logical_target' not in target:break
    dest=target['resolved_logical_target']
  write(ROOT/'receipts'/f'{profile}-archive-members.json',{'member_count':len(entries),'expanded_size_bytes':total,'entries':entries,'verification':'bounded metadata validation before extraction and execution; no external symlink or stdlib symlink admitted'})
  target=ROOT/'profiles'/profile
  assert not target.exists(), 'refuse overwrite existing profile'
  target.mkdir(parents=True)
  tf.extractall(target,filter='data')
 return entries

def main(profile):
 target=TARGETS[profile]
 meta=json.loads((ROOT/'metadata'/f'github-release-{target["release"]}-selected.json').read_text())
 matches=[a for a in meta['assets'] if a['size']==target['size'] and a['digest']=='sha256:'+target['sha256']]
 assert len(matches)==1
 asset=matches[0]; url=asset['browser_download_url']; assert url.startswith('https://github.com/astral-sh/python-build-standalone/releases/download/'+target['release']+'/')
 archive=ROOT/'downloads'/asset['name']
 attempt={'profile':profile,'url':url,'expected_sha256':target['sha256'],'expected_size_bytes':target['size'],'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
 log=ROOT/'logs'/f'{profile}-archive-download.log'
 try:
  assert not archive.exists(), 'refuse overwrite prior download'
  with log.open('w') as out:
   result=subprocess.run(['curl','--fail','--location','--max-time','240','--proto','=https','--proto-redir','=https','--max-filesize',str(target['size']),'--output',str(archive),url],stdout=out,stderr=subprocess.STDOUT)
  attempt['curl_exit']=result.returncode
  assert result.returncode==0, 'download failed; preserve partial bytes'
  attempt.update(actual_size_bytes=archive.stat().st_size,actual_sha256=digest(archive))
  assert attempt['actual_size_bytes']==target['size'] and attempt['actual_sha256']==target['sha256'], 'archive mismatch'
  audit(archive,profile)
  executable=ROOT/'profiles'/profile/'python/bin'/('python'+target['version'].rsplit('.',1)[0])
  assert executable.is_file() and not executable.is_symlink()
  attempt.update(executable_relative=executable.relative_to(ROOT).as_posix(),executable_size_bytes=executable.stat().st_size,executable_sha256=digest(executable))
  assert attempt['executable_sha256']==target['executable_sha256'],'executable mismatch before execution'
  attempt['status']='checksum and archive inspection passed; extracted without execution'
 except BaseException as e:
  attempt['status']='failed';attempt['failure']=str(e);raise
 finally:write(ROOT/'receipts'/f'{profile}-acquisition.json',attempt)
 print(json.dumps(attempt,sort_keys=True))
if __name__=='__main__':main(sys.argv[1])
