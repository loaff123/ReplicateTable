#!/usr/bin/env python3
"""Preparation-only full relative tree artifact snapshot; never imports product."""
import hashlib,json,os,pathlib,stat,sys
root=pathlib.Path(sys.argv[1]); result={}
assert not root.is_symlink()
for base, dirs, files in os.walk(root,followlinks=False):
 dirs.sort();files.sort()
 for name in dirs+files:
  p=pathlib.Path(base)/name; s=p.lstat(); rel=p.relative_to(root).as_posix()
  if stat.S_ISLNK(s.st_mode):
   target=os.readlink(p); actual=p.resolve(strict=True)
   assert actual.is_relative_to(root.resolve()),('external link',rel,target)
   result[rel]={'type':'symlink','target':target}
  elif stat.S_ISREG(s.st_mode):
   h=hashlib.sha256()
   with p.open('rb') as f:
    while data:=f.read(65536):h.update(data)
   result[rel]={'type':'file','size_bytes':s.st_size,'sha256':h.hexdigest()}
  else:assert stat.S_ISDIR(s.st_mode),('special file',rel)
pathlib.Path(sys.argv[2]).write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(len(result),'entries',sum(r.get('size_bytes',0) for r in result.values()),'bytes')
