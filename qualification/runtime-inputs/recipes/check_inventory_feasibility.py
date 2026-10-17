#!/usr/bin/env python3
"""Standalone bounded inventory feasibility, including repeated Pint occurrences.
Never imports recovered product code. Product resources are explicitly pending.
"""
import hashlib,json,os,pathlib,stat,sys
ROOT=pathlib.Path(__file__).resolve().parent.parent
LIMITS={'file_occurrences':8192,'directory_visits':4096,'hashed_bytes':256*1024**2,'single_file_bytes':128*1024**2,'inventory_files':2048,'inventory_directories':512,'relative_name_bytes':128,'retained_name_bytes':128*1024}
PAYLOADS={'numpy':['numpy','numpy.libs'],'pandas':['pandas'],'xarray':['xarray'],'pint':['pint'],'h5py':['h5py','h5py.libs'],'h5netcdf':['h5netcdf'],'flexcache':['flexcache'],'flexparser':['flexparser'],'platformdirs':['platformdirs'],'typing-extensions':['typing_extensions.py'],'packaging':['packaging'],'python-dateutil':['dateutil'],'pytz':['pytz'],'tzdata':['tzdata'],'six':['six.py']}
def canonical(x):return (json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode()
for profile,minor in [('public312','3.12'),('public313','3.13')]:
 site=ROOT/'profiles'/profile/'venv/lib'/('python'+minor)/'site-packages';stdlib=ROOT/'profiles'/profile/'python/lib'/('python'+minor)
 budget={'file_occurrences':0,'directory_visits':1,'hashed_bytes':0} # bounded dist-info discovery root visit
 def hashfile(p):
  st=p.lstat();assert stat.S_ISREG(st.st_mode) and 0<=st.st_size<=LIMITS['single_file_bytes']
  assert budget['file_occurrences']<LIMITS['file_occurrences'];budget['file_occurrences']+=1
  assert budget['hashed_bytes']+st.st_size<=LIMITS['hashed_bytes'];budget['hashed_bytes']+=st.st_size
  h=hashlib.sha256()
  with p.open('rb') as f:
   while b:=f.read(65536):h.update(b)
  assert st.st_size==p.stat().st_size
  return {'sha256':h.hexdigest(),'size_bytes':st.st_size}
 def selected(name,kind):
  base=name.rsplit('/',1)[-1]
  if base.endswith(('.pyc','.pyo')):return False
  if kind=='payload':return True
  if kind=='stdlib':return not base.startswith('_sysconfigdata_') and (base.endswith(('.py','.so')) or '.so.' in base)
  if kind=='pint':return base.endswith('.txt')
  if kind=='metadata':return name in ('METADATA','WHEEL','entry_points.txt','top_level.txt') or 'licenses' in name.split('/')[:-1] or base.lower().startswith(('license','notice','copying','copyright'))
  raise AssertionError(kind)
 def inventory(root,roots,kind):
  queue=[];files=[];directories=[];live_name_bytes=0;peak_name_bytes=0;max_name_bytes=0
  def retain(name,isdir):
   nonlocal live_name_bytes,peak_name_bytes,max_name_bytes
   size=len(name.encode());assert size<=LIMITS['relative_name_bytes'];max_name_bytes=max(max_name_bytes,size)
   assert live_name_bytes+size<=LIMITS['retained_name_bytes'];live_name_bytes+=size;peak_name_bytes=max(peak_name_bytes,live_name_bytes)
   if isdir:
    assert len(directories)<LIMITS['inventory_directories'];assert budget['directory_visits']<LIMITS['directory_visits'];budget['directory_visits']+=1
    directories.append(name);queue.append(name)
   else:assert len(files)<LIMITS['inventory_files'];files.append(name)
  for rel in roots:
   p=root/rel;st=p.lstat();assert not p.is_symlink()
   if stat.S_ISDIR(st.st_mode):retain(rel,True)
   else:assert stat.S_ISREG(st.st_mode);retain(rel,False)
  while queue:
   rel=queue.pop();live_name_bytes-=len(rel.encode())
   with os.scandir(root/rel) as it:
    for entry in it:
     n=entry.name
     if n=='__pycache__' or n.endswith(('.pyc','.pyo')) or (kind=='stdlib' and (n in ('site-packages','dist-packages') or n.startswith(('config-','_sysconfigdata_')))):continue
     logical=rel+'/'+n if rel else n;assert not entry.is_symlink(),('symlink refused',kind,logical)
     if entry.is_dir(follow_symlinks=False):retain(logical,True)
     elif entry.is_file(follow_symlinks=False):
      if selected(logical,kind):retain(logical,False)
     else:raise AssertionError(('unsupported file type',kind,logical))
  assert len(files)==len(set(files))
  values={name:hashfile(root/name) for name in sorted(files)}
  return values,{'sha256':hashlib.sha256(canonical(values)).hexdigest(),'file_count':len(values),'size_bytes':sum(v['size_bytes'] for v in values.values()),'directory_visits':len(directories),'max_relative_name_bytes':max_name_bytes,'measured_peak_retained_name_bytes':peak_name_bytes,'conservative_all_file_and_directory_name_bytes':sum(len(n.encode()) for n in files+directories)}
 components={};inventories={}
 components['executable']={'file_count':1,'directory_visits':0,**hashfile(ROOT/'profiles'/profile/'venv/bin/python')}
 python=json.loads((ROOT/'receipts'/f'{profile}-after-python.json').read_text())['python'];assert python['core_libraries']=={}
 components['core_libraries']={'file_count':0,'directory_visits':0,'size_bytes':0,'observed_mapped_images':{}}
 values,components['stdlib_code']=inventory(stdlib,[''],'stdlib');inventories['stdlib_code']=values
 expected_stdlib=json.loads((ROOT/'receipts'/f'{profile}-after-stdlib-inventory.json').read_text());assert values==expected_stdlib
 expected_deps=json.loads((ROOT/'receipts'/f'{profile}-dependency-inventories.json').read_text())
 wheels=json.loads((ROOT/'receipts'/f'{profile}-wheel-artifacts.json').read_text());versions={r['name']:r['version'] for r in wheels}
 metadata_headers={}
 for name,roots in sorted(PAYLOADS.items()):
  values,components[name+'/payload']=inventory(site,roots,'payload');inventories[name+'/payload']=values;assert values==expected_deps[name]['payload']
  distinfo=[p for p in site.glob('*.dist-info') if p.name.lower().replace('_','-')==name+'-'+versions[name]+'.dist-info'];assert len(distinfo)==1
  values,components[name+'/metadata']=inventory(distinfo[0],[''],'metadata');inventories[name+'/metadata']=values;assert values==expected_deps[name]['metadata']
  header_bytes=0;max_line=0;identity={}
  with (distinfo[0]/'METADATA').open('rb') as f:
   while True:
    line=f.readline(4097);assert len(line)<=4096;header_bytes+=len(line);assert header_bytes<=131072;max_line=max(max_line,len(line))
    if line in (b'\n',b'\r\n',b''):break
    for field in (b'Name:',b'Version:'):
     if line.startswith(field):assert field not in identity;identity[field]=line[len(field):].strip();assert 1<=len(identity[field])<=128
  assert set(identity)=={b'Name:',b'Version:'};metadata_headers[name]={'header_bytes':header_bytes,'max_raw_line_bytes':max_line}
 values,components['pint_definitions_repeated']=inventory(site/'pint',[''],'pint');inventories['pint_definitions_repeated']=values;assert {'constants_en.txt','default_en.txt'}<=values.keys() and len(values)<=256
 totals={key:budget[key] for key in ('file_occurrences','directory_visits','hashed_bytes')}
 headroom={key:LIMITS[key]-value for key,value in totals.items()}
 assert len(canonical(inventories))<=16*1024*1024
 report={'profile':profile,'status':'installed runtime components fit unchanged caps; final product resources pending','scope':'bounded standalone preparation, no product imports, no product runtime-scanner/lifecycle/RSS qualification','limits':LIMITS,'totals_excluding_pending_product_resources':totals,'headroom_for_final_product_resources':headroom,'product_resources':{'status':'not counted; final product source identity and actual file/directory/byte counts required','maximum_product_files_by_separate_map_limit':256},'components':components,'dist_info_discovery_directory_visits':1,'metadata_header_measurements':metadata_headers,'runtime_bound_distributions':sorted(PAYLOADS),'extras_outside_runtime_binding':{k:v for k,v in versions.items() if k not in PAYLOADS},'pint_definitions_counted_again':True,'all_relative_paths_public_safe':True,'inventory_evidence_canonical_bytes':len(canonical(inventories))}
 (ROOT/'receipts'/f'{profile}-runtime-feasibility.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
 (ROOT/'receipts'/f'{profile}-runtime-feasibility-inventories.json').write_text(json.dumps(inventories,sort_keys=True,indent=2)+'\n')
 print(profile,json.dumps({'totals_excluding_product':totals,'headroom_for_product':headroom,'largest_inventory':max(components,key=lambda k:components[k]['file_count']),'max_metadata_header_bytes':max(v['header_bytes'] for v in metadata_headers.values())},sort_keys=True))
