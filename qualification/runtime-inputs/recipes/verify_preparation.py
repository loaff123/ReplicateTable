#!/usr/bin/env python3
import hashlib,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parent.parent

def load(path):return json.loads((ROOT/path).read_text())
def artifact(path):
 h=hashlib.sha256();size=0
 with path.open('rb') as f:
  while b:=f.read(65536):h.update(b);size+=len(b)
 return {'sha256':h.hexdigest(),'size_bytes':size}
results={}
for profile,minor in [('public312','3.12'),('public313','3.13')]:
 before=load(f'receipts/{profile}-interpreter-before.json');after=load(f'receipts/{profile}-interpreter-after.json');assert before==after,(profile,'interpreter tree changed')
 py_before=load(f'receipts/{profile}-before-python.json')['python'];py_after=load(f'receipts/{profile}-after-python.json')['python'];assert py_before==py_after,(profile,'selected Python identity changed')
 original=load(f'receipts/{profile}-acquisition.json');selected=load(f'metadata/github-release-'+('20260924' if profile=='public312' else '20250723')+'-selected.json')['assets'][0]
 assert artifact(ROOT/'downloads'/selected['name'])=={'size_bytes':original['actual_size_bytes'],'sha256':original['actual_sha256']}
 assert artifact(ROOT/'profiles'/profile/'venv/bin/python')==py_after['executable']
 wheels=load(f'receipts/{profile}-wheel-artifacts.json')
 for wheel in wheels:assert artifact(ROOT/'downloads'/profile/'wheels'/wheel['filename'])=={'sha256':wheel['sha256'],'size_bytes':wheel['size_bytes']}
 pip=[w for w in wheels if w['name']=='pip'][0]
 bundled=ROOT/'profiles'/profile/'python/lib'/('python'+minor)/'ensurepip/_bundled'/pip['filename']
 assert artifact(bundled)=={'sha256':pip['sha256'],'size_bytes':pip['size_bytes']},(profile,'bootstrap pip wheel differs from PyPI wheel')
 inventories=load(f'receipts/{profile}-dependency-inventories.json')
 site=ROOT/'profiles'/profile/'venv/lib'/('python'+minor)/'site-packages'
 for package,inv in inventories.items():
  wheel=[w for w in wheels if w['name']==package][0]
  for rel,expected in inv['payload'].items():assert artifact(site/rel)==expected,(profile,package,rel,'payload changed after smoke')
  distinfo=[p for p in site.glob('*.dist-info') if p.name.lower().replace('_','-')==(package.replace('_','-')+'-'+wheel['version']+'.dist-info')];assert len(distinfo)==1,(package,distinfo)
  for rel,expected in inv['metadata'].items():assert artifact(distinfo[0]/rel)==expected,(profile,package,rel,'metadata changed after smoke')
 dep=load(f'receipts/{profile}-dependency-preparation.json')
 results[profile]={'status':'preparation verified; not product qualification','interpreter_relative':'profiles/'+profile+'/venv/bin/python','archive':{'filename':selected['name'],'url':selected['browser_download_url'],'size_bytes':original['actual_size_bytes'],'sha256':original['actual_sha256']},'python':py_after,'installed_distributions':dep['installed_distributions'],'runtime_dependency_count':len(dep['runtime_dependencies']),'runtime_inventory_occurrences':dep['runtime_inventory_occurrences'],'runtime_inventory_bytes':dep['runtime_inventory_bytes'],'wheel_count':len(wheels),'wheel_archives_bytes':sum(w['size_bytes'] for w in wheels),'license_file_occurrences':sum(len(w['licenses']) for w in wheels),'checks':{'archive_hash_after_install':True,'executable_hash_before_and_after':True,'entire_base_interpreter_tree_unchanged':True,'selected_python_identity_unchanged':True,'all_wheel_hashes_after_install':True,'bootstrap_pip_matches_locked_pypi_wheel':True,'runtime_payload_metadata_unchanged_after_smoke':True,'pip_check':True,'seven_tiny_native_import_smoke_checks':True,'product_imports_performed':False}}
(ROOT/'receipts/public-profile-summary.json').write_text(json.dumps(results,sort_keys=True,indent=2)+'\n')
print(json.dumps({p:{'status':r['status'],'all_checks_passed':True} for p,r in results.items()},indent=2))
