"""New finite authored fixtures and hand-worked expectations; not a runtime adapter.

Expected results below are explicit per-group scalars. This script never evaluates
candidate code, reads candidate source, or derives expectations through oracle.py.
"""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write(name, value):
    (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n')

def coord(dtype, values):
    return {'dtype': dtype, 'values': values}

def var(dims, values, units=None, dtype='float64'):
    return {'dims': dims, 'values': values, 'units': units, 'dtype': dtype}

def stage(name='reduce', dims=None, op='mean', missing='skip', min_count=1, weights=None, weight_unit=None):
    result = dict(name=name, dims=dims or ['sample'], op=op, missing=missing, min_count=min_count)
    if op == 'weighted_mean':
        result.update(weights=weights or 'weights', weight_unit=weight_unit)
    return result

def column(name='value', source='response', stages=None, source_unit=None, target_unit=None, broadcast=None):
    return dict(name=name, source=source, source_unit=source_unit, target_unit=target_unit, broadcast=broadcast or [], stages=stages or [])

def case(id, purpose, coords, variables, row_dims, columns, kind='execute', dimensions=None):
    return dict(id=id, kind=kind, purpose=purpose,
                data=dict(coords=coords, variables=variables, dimensions=dimensions or {d:len(c['values']) for d,c in coords.items()}),
                recipe=dict(version=1,row_dims=row_dims,columns=columns))

def support(name, st, keys, n, valid, positive, total, weight_valid, value, reasons=None, unit=None):
    return dict(column=name, stage=st, keys=keys, n_input=n, n_valid=valid, n_positive_weight_valid=positive,
                weight_total=Fraction(str(total)),weight_valid=Fraction(str(weight_valid)),
                value=None if value is None else Fraction(str(value)),reasons=reasons or [],unit=unit)

def expected(row_dims, units, rows, supports):
    # Each row tuple supplies its already-hand-worked value mapping/reasons.
    cooked=[]; exact=[]
    for keys, values, reasons in rows:
        cooked.append(dict(keys=keys, values={k:float(v) if isinstance(v,Fraction) else v for k,v in values.items()}, reasons=reasons))
        exact.append(dict(keys=keys, values={k:None if v is None else str(Fraction(str(v))) for k,v in values.items()}))
    records=[]; exact_support=[]
    for item in supports:
        record=dict(item)
        exact_support.append({k:item[k] for k in ['column','stage','keys'] } | {k:None if item[k] is None else str(item[k]) for k in ['weight_total','weight_valid','value']})
        for key in ['weight_total','weight_valid','value']:
            record[key]=None if item[key] is None else float(item[key])
        records.append(record)
    return dict(status='success',result=dict(version=1,row_dims=row_dims,units=units,rows=cooked,support=records),exact=dict(rows=exact,support=exact_support))

F=Fraction
cases=[]; outcomes={}; derivations={}

def add(c,e,why):
    cases.append(c); outcomes[c['id']]=e; derivations[c['id']]=why

# Exact direct data and keys, including values that binary64 cannot represent.
id='S01_direct_uint64_keys_and_integer_values'
keys=[18446744073709551615,9007199254740993,9007199254740995]
c=case(id,'Exact int64/uint64 direct outputs and uint64 row keys; direct binary32 and signed zero.',
       {'key:00':coord('uint64',keys)},
       {'signed':var(['key:00'],[-9223372036854775808,9007199254740993,9223372036854775807],dtype='int64'),
        'unsigned':var(['key:00'],[18446744073709551615,9007199254740995,0],dtype='uint64'),
        'binary32':var(['key:00'],[0.5,-0.0,16777216.0],dtype='float32')},
       ['key:00'],[column('key:00','signed'),column('n_valid','unsigned'),column('stage','binary32')])
rows=[({'key:00':keys[i]},{'key:00':c['data']['variables']['signed']['values'][i],'n_valid':c['data']['variables']['unsigned']['values'][i],'stage':c['data']['variables']['binary32']['values'][i]},dict.fromkeys(['key:00','n_valid','stage'],[])) for i in [1,2,0]]
e=expected(['key:00'],dict.fromkeys(['key:00','n_valid','stage'],None),rows,[])
e['exact_dtype']={'key:00':'int64','n_valid':'uint64','stage':'float32'}
e['exact_signed_zero']=[{'path':['result','rows',0,'values','stage'],'negative':True}]
add(c,e,'Integer keys and values are literal exact integers. Physical key order is permuted to ascending integer order; no float coercion. Float32 inputs are exactly representable, including stored -0.0.')

id='S02_direct_signed_extreme_keys'
keys=[9223372036854775807,-9223372036854775808,9007199254740993]
c=case(id,'Signed int64 extreme and large keys remain exact.',{'case':coord('int64',keys)},
       {'response':var(['case'],[7,8,9],dtype='int64')},['case'],[column()])
add(c,expected(['case'],{'value':None},[({'case':keys[i]},{'value':[7,8,9][i]},{'value':[]}) for i in [1,2,0]],[]),'Signed integer ordering: -2**63, 2**53+1, 2**63-1; output literals 8,9,7.')

id='S03_percent_named_alignment'
coords={'sample':coord('int64',[9,2]),'case':coord('<U1',['z','a']),'replicate':coord('int64',[7,3])}
variables={'response':var(['sample','case','replicate'],[2,10,4,20,6,None,8,40]),'weights':var(['replicate','sample'],[0,25,75,100],units='percent')}
cols=[column('equal_replicates',stages=[stage('samples',['sample'],'weighted_mean',weights='weights',weight_unit='percent'),stage('replicates',['replicate'])]),
      column('pooled',stages=[stage('pooled',['sample','replicate'],'weighted_mean',weights='weights',weight_unit='percent')])]
c=case(id,'Weight dimensions are reordered relative to physical source and subset-aligned by name.',coords,variables,['case'],cols)
s=[]
for k,r,v,n,w in [('a',3,F(220,7),2,F(7,4)),('a',7,8,2,F(1,4)),('z',3,10,1,F(3,4)),('z',7,6,2,F(1,4))]:
    s.append(support('equal_replicates','samples',{'case':k,'replicate':r},2,n,1 if r==7 or k=='z' else 2,F(1,4) if r==7 else F(7,4),w,v))
for k,v in [('a',F(138,7)),('z',8)]: s.append(support('equal_replicates','replicates',{'case':k},2,2,2,2,2,v))
for k,v,n,p,w in [('a',F(57,2),4,3,2),('z',9,3,2,1)]: s.append(support('pooled','pooled',{'case':k},4,n,p,2,w,v))
add(c,expected(['case'],{'equal_replicates':None,'pooled':None},[
    ({'case':'a'},{'equal_replicates':F(138,7),'pooled':F(57,2)},{'equal_replicates':[],'pooled':[]}),
    ({'case':'z'},{'equal_replicates':F(8),'pooled':F(9)},{'equal_replicates':[],'pooled':[]})],s),
    'Percent scale=1/100. Weights at replicate7 are (0,1/4), replicate3 (3/4,1). a: sample means 8 and 220/7, equal mean 138/7; pooled numerator57 denominator2. z: means6 and10, equal8; pooled numerator9 denominator1. Coordinate sort does not change alignment.')

id='S04_two_stage_failure_policies'
coords={'case':coord('<U1',['b','a']),'replicate':coord('int64',[2,0,1]),'sample':coord('int64',[1,0])}
variables={'response':var(['case','replicate','sample'],[2,None,10,14,None,None,None,None,5,None,20,24])}
cols=[]
for name,missing,mc,firstmissing in [('skip1','skip',1,'skip'),('skip2','skip',2,'skip'),('prop1','propagate',1,'skip'),('prop2','propagate',2,'propagate')]:
    cols.append(column(name,stages=[stage('samples',['sample'],missing=firstmissing,min_count=2),stage('replicates',['replicate'],missing=missing,min_count=mc)]))
c=case(id,'Failed intermediate values become missing; final reasons belong only to final stage.',coords,variables,['case'],cols)
s=[]
for col in cols:
    name=col['name']; propagate=col['stages'][0]['missing']=='propagate'
    for k,r,n,v in [('a',0,1,None),('a',1,2,22),('a',2,0,None),('b',0,2,12),('b',1,0,None),('b',2,1,None)]:
        reasons=(['missing_values'] if propagate and n!=2 else [])+(['insufficient_count'] if n<2 else [])
        s.append(support(name,'samples',{'case':k,'replicate':r},2,n,n,2,n,v,reasons))
    for k,v in [('a',22),('b',12)]:
        reasons=(['missing_values'] if name.startswith('prop') else [])+(['insufficient_count'] if name.endswith('2') else [])
        s.append(support(name,'replicates',{'case':k},3,1,1,3,1,v if not reasons else None,reasons))
rows=[]
for k,v in [('a',22),('b',12)]:
    rows.append(({'case':k},{'skip1':F(v),'skip2':None,'prop1':None,'prop2':None},
                 {'skip1':[],'skip2':['insufficient_count'],'prop1':['missing_values'],'prop2':['missing_values','insufficient_count']}))
add(c,expected(['case'],dict.fromkeys([x['name'] for x in cols],None),rows,s),'First-stage min_count2 leaves only a=22 and b=12, each among three replicates. Second-stage valid count1 satisfies min_count1 only; propagate detects two missing predecessors. Intermediate reason labels never leak into final reasons.')

id='S05_one_stage_failure_reason_order'
coords={'case':coord('<U7',['zero','missing','short','partial']),'sample':coord('int64',[2,0,1])}
variables={'response':var(['case','sample'],[1,2,3,None,None,None,4,None,None,2,None,10]),'weights':var(['case','sample'],[0,0,0,100,200,0,0,100,300,25,100,75],units='percent')}
cols=[column(m,stages=[stage('samples',['sample'],'weighted_mean',m,2,weight_unit='percent')]) for m in ['skip','propagate']]
c=case(id,'One-stage missing/min-count/zero-weight predicates and exact reason order.',coords,variables,['case'],cols)
s=[]; rows=[]
info={'missing':(0,0,3,0,None),'partial':(2,2,2,1,8),'short':(1,0,4,0,None),'zero':(3,0,0,0,None)}
for col in cols:
    for k,(n,p,t,w,v) in info.items():
        reasons=(['missing_values'] if col['name']=='propagate' and n!=3 else [])+(['insufficient_count'] if n<2 else [])+(['zero_weight'] if w==0 else [])
        s.append(support(col['name'],'samples',{'case':k},3,n,p,t,w,None if reasons else v,reasons))
for k,(n,p,t,w,v) in info.items():
    rr={m:(['missing_values'] if m=='propagate' and n!=3 else [])+(['insufficient_count'] if n<2 else [])+(['zero_weight'] if w==0 else []) for m in ['skip','propagate']}
    rows.append(({'case':k},{m:None if rr[m] else F(v) for m in rr},rr))
add(c,expected(['case'],{'skip':None,'propagate':None},rows,s),'Partial numerator=2*(1/4)+10*(3/4)=8 and valid denominator1, total2. Finite zero-weight values count toward n_valid, but never positive count. Missing and short retain every applicable reason in prescribed order.')

for id,units,target,raw,scale,offset,first,final,pooled,minimum,maximum in [
 ('S06_affine_celsius_kelvin','degC','K',[0,10,20,None],'1','27315/100',['5613/20','5863/20'],'2869/10','5663/20','5463/20','5863/20'),
 ('S07_affine_fahrenheit_celsius','degF','degC',[32,50,68,None],'5/9','-160/9',['15/2','20'],'55/4','10','0','20')]:
    coords={'replicate':coord('int64',[1,0]),'sample':coord('int64',[9,2])}
    variables={'response':var(['replicate','sample'],raw,units=units),'weights':var(['sample'],[25,75],units='percent'),'direct':var([], [raw[0]],units=units)}
    cols=[column('two_stage',source_unit=units,target_unit=target,stages=[stage('samples',['sample'],'weighted_mean',weight_unit='percent'),stage('replicates',['replicate'])]),
          column('pooled',source_unit=units,target_unit=target,stages=[stage('pooled',['replicate','sample'],'weighted_mean',weight_unit='percent')]),
          column('minimum',source_unit=units,target_unit=target,stages=[stage('extrema',['sample','replicate'],'min')]),
          column('maximum',source_unit=units,target_unit=target,stages=[stage('extrema',['sample','replicate'],'max')]),
          column('direct','direct',source_unit=units,target_unit=target)]
    c=case(id,'Positive affine conversion is applied once before ordered reductions and direct output.',coords,variables,[],cols)
    s=[support('two_stage','samples',{'replicate':0},2,1,1,1,F(1,4),F(first[1]),unit=target),support('two_stage','samples',{'replicate':1},2,2,2,1,1,F(first[0]),unit=target),support('two_stage','replicates',{},2,2,2,2,2,F(final),unit=target),support('pooled','pooled',{},4,3,3,2,F(5,4),F(pooled),unit=target),support('minimum','extrema',{},4,3,3,4,3,F(minimum),unit=target),support('maximum','extrema',{},4,3,3,4,3,F(maximum),unit=target)]
    vals=dict(two_stage=F(final),pooled=F(pooled),minimum=F(minimum),maximum=F(maximum),direct=F(raw[0])*F(scale)+F(offset))
    add(c,expected([],dict.fromkeys(vals,target),[({},vals,dict.fromkeys(vals,[]))],s),f'Exact affine map y={scale}*x+{offset}. Weighted per-replicate converted means are {first}; equal-replicate mean {final}; pooled valid weight5/4 and mean {pooled}. Extrema and direct conversion are explicit.')

id='S08_direct_nan_and_signed_zero_key'
c=case(id,'Direct NaN is missing with reason; stored float key signed zero is retained.',{'case':coord('float64',[1.0,-0.0])},{'response':var(['case'],[2.5,None])},['case'],[column()])
e=expected(['case'],{'value':None},[({'case':-0.0},{'value':None},{'value':['missing_values']}),({'case':1.0},{'value':2.5},{'value':[]})],[])
e['exact_signed_zero']=[{'path':['result','rows',0,'keys','case'],'negative':True}]
add(c,e,'Only direct float null is admitted; it represents a source NaN, with missing_values even without stages. Stored -0.0 sorts before1.0 and remains negative zero.')

id='S09_opaque_name_collisions'
names=['n_input','key:00','value:00','reasons:00','stage','n_valid']
c=case(id,'Logical row, column, stage and support-looking names cannot collide physically.',{'n_input':coord('int64',[2,1]),'stage':coord('int64',[0,1])},{'response':var(['n_input','stage'],[2,4,6,8])},['n_input'],[column(n,stages=[stage('value',['stage'])]) for n in names])
s=[support(n,'value',{'n_input':key},2,2,2,2,2,value) for n in names for key,value in [(1,7),(2,3)]]
e=expected(['n_input'],dict.fromkeys(names,None),[({'n_input':k},dict.fromkeys(names,F(v)),dict.fromkeys(names,[])) for k,v in [(1,7),(2,3)]],s)
e['table_headers']=['key:00']+[f'{role}:{i:02d}' for i in range(6) for role in ['value','reasons']]
e['support_headers']=['key:00','n_input','n_valid','n_positive_weight_valid','weight_total','weight_valid','reasons','value']
add(c,e,'Each column has mean7 at key1 and mean3 at key2. Logical names are opaque; schema uses positional physical headers, all unique.')

# New finite refusal controls, complete source fixtures, not inferred old NB2-NB9 files.
def refuse(c,category,exit=2,code=None,phase='compile',why=''):
    if code is None:
        code = {
            'selected_coordinate':'duplicate_coordinate',
            'invalid_weight':'negative_weight' if c['id']=='R05_negative_weight_at_missing' else 'nonfinite_weight',
            'stage_count':'invalid_recipe', 'stage_order':'unsupported_later_stage_weights',
            'stage_dimensions':'invalid_recipe', 'min_count':'invalid_recipe',
            'duplicate_output_name':'invalid_recipe', 'unit_assertion':'source_unit_mismatch',
            'weight_unit_assertion':'weight_unit_mismatch', 'weight_dimensions':'invalid_weights',
            'integer_null_result':'invalid_result', 'weight_sum_envelope':'invalid_result',
        }[category]
    add(c,dict(status='refused' if exit==2 else 'failed',category=category,exit_code=exit,code=code,phase=phase),why)

def simple(id,values=(1.0,2.0),units=None,target=None,weighted=False,weights=None):
    variables={'response':var(['sample'],list(values),units=units)}
    if weighted: variables['weights']=var(['sample'],weights if weights is not None else [1.0]*len(values))
    return case(id,id,{'sample':coord('int64',list(range(len(values))))},variables,[],[column(source_unit=units,target_unit=target,stages=[stage(op='weighted_mean' if weighted else 'mean')])])

for id,typ in [('R01_missing_reduced_coordinate','absent'),('R02_duplicate_reduced_label','duplicate'),('R03_missing_reduced_label','missing')]:
    c=simple(id)
    if typ=='absent': c['data']['coords']={}
    elif typ=='duplicate': c['data']['coords']['sample']['values']=[0,0]
    else: c['data']['coords']['sample']=coord('object',['present',None])
    refuse(c,'selected_coordinate',code='missing_coordinate' if typ!='duplicate' else None,why='Every selected reduced dimension requires complete unique nonmissing labels, even if no row key uses it.')

c=simple('R04_duplicate_signed_zero_reduced_labels'); c['data']['coords']['sample']=coord('float64',[0.0,-0.0]); refuse(c,'selected_coordinate',why='+0.0 and -0.0 are duplicate labels, despite preserved stored sign for a unique zero.')
for id,weight in [('R05_negative_weight_at_missing',-1.0),('R06_nan_weight_at_missing',None),('R07_infinite_weight_at_missing',{'float_special':'+inf'})]:
    c=simple(id,values=(None,2.0),weighted=True,weights=[weight,1.0]); refuse(c,'invalid_weight',phase='execute',why='All physical weights must be finite/nonnegative, including the weight at a missing measurement.')
c=simple('R08_infinite_measurement',values=({'float_special':'+inf'},2.0)); refuse(c,'nonfinite_measurement',code='nonfinite_value',phase='execute',why='Measurement infinity refuses rather than becoming missing.')

c=simple('R09_conversion_overflow',values=(1e308,),units='s',target='ms'); c['recipe']['columns'][0]['stages']=[]; c['recipe']['row_dims']=['sample']; refuse(c,'numeric_overflow',3,'numeric_overflow','execute','1e308*1000 exceeds finite binary64; direct conversion must not yield a null.')
c=simple('R10_weighted_product_overflow',values=(1e308,),weighted=True,weights=[2.0]); refuse(c,'numeric_overflow',3,'numeric_overflow','execute','Finite product1e308*2 overflows even though algebraically divided by2 afterward.')
c=simple('R11_mean_sum_overflow',values=(1e308,1e308)); refuse(c,'numeric_overflow',3,'numeric_overflow','execute','The finite-input mean accumulation overflows; replacing sum/division with a rescaled algorithm would erase this frozen intermediate-failure control.')
c=simple('R12_weight_sum_overflow',values=(0.0,0.0),weighted=True,weights=[1e308,1e308]); refuse(c,'numeric_overflow',3,'numeric_overflow','execute','Products are zero, but aligned weight_total and weight_valid overflow.')
c=case('R13_second_stage_sum_overflow','Overflow also fails at second stage.',{'replicate':coord('int64',[0,1]),'sample':coord('int64',[0])},{'response':var(['replicate','sample'],[1e308,1e308])},[],[column(stages=[stage('samples',['sample']),stage('replicates',['replicate'])])]); refuse(c,'numeric_overflow',3,'numeric_overflow','execute','First-stage singleton means are finite1e308; second-stage sum exceeds finite binary64.')

c=simple('R14_three_stages'); c['recipe']['columns'][0]['stages']=[stage('a'),stage('b'),stage('c')]; refuse(c,'stage_count',phase='recipe',why='Exactly zero, one or two stages are permitted.')
c=case('R15_weighted_second_stage','A second weighted stage is forbidden.',{'replicate':coord('int64',[0]),'sample':coord('int64',[0,1])},{'response':var(['replicate','sample'],[1,2]),'weights':var(['replicate'],[1])},[],[column(stages=[stage('samples',['sample']),stage('replicates',['replicate'],'weighted_mean')])]); refuse(c,'stage_order',why='Source weights are legal only for stage zero.')
c=simple('R16_repeated_removed_dimension'); c['recipe']['columns'][0]['stages']=[stage('a'),stage('b')]; refuse(c,'stage_dimensions',why='Stage one cannot reduce a dimension already removed by stage zero.')
for id,value in [('R17_zero_min_count',0),('R18_bool_min_count',True)]:
    c=simple(id); c['recipe']['columns'][0]['stages'][0]['min_count']=value; refuse(c,'min_count',phase='recipe',why='min_count is an exact int>=1; bool is not int.')
c=simple('R19_duplicate_output_name'); c['recipe']['columns'].append(deepcopy(c['recipe']['columns'][0])); refuse(c,'duplicate_output_name',phase='recipe',why='Opaque names are permitted, but logical output column names must be unique.')
c=simple('R20_exact_source_unit_assertion',units='s'); c['recipe']['columns'][0]['source_unit']='second'; refuse(c,'unit_assertion',why='Equivalent physical units do not satisfy an unequal raw source-label assertion.')
c=simple('R21_exact_weight_unit_assertion',weighted=True,weights=[25,75]); c['data']['variables']['weights']['units']='percent'; c['recipe']['columns'][0]['stages'][0]['weight_unit']='%'; refuse(c,'weight_unit_assertion',why='Percent and % are physically equivalent but raw weight assertions compare exact labels.')
c=simple('R22_extra_weight_dimension',weighted=True); c['data']['coords']['other']=coord('int64',[0,1]); c['data']['dimensions']['other']=2; c['data']['variables']['weights']['dims']=['other']; refuse(c,'weight_dimensions',why='A named weight dimension must be among original measurement dimensions; equal lengths do not imply alignment.')

# Direct result corruption is separate from the inability to encode NaN in int arrays.
for id,col in [('M01_direct_int64_null','key:00'),('M02_direct_uint64_null','n_valid')]:
    c=dict(id=id,kind='result_mutation',purpose='Integer direct values cannot be null even with missing_values.',base_case='S01_direct_uint64_keys_and_integer_values',mutations=[dict(path=['rows',0,'values',col],value=None),dict(path=['rows',0,'reasons',col],value=['missing_values'])])
    refuse(c,'integer_null_result',phase='result_constructor',why='Both value/reasons are changed coherently, so the refusal specifically protects nonnullable direct integer outputs, not a generic null/reason mismatch.')

id='M03_rounded_weight_envelope_accept'
record=dict(column='value',stage='reduce',keys={},n_input=4,n_valid=3,n_positive_weight_valid=3,weight_total=1e16,weight_valid=1e16+2,reasons=[],value=0.9999999999999998,unit=None)
c=dict(id=id,kind='support_model',purpose='Separately rounded weight_valid may exceed weight_total within approved envelope.',stage=stage(op='weighted_mean'),record=record)
add(c,dict(status='accepted',exact_record=record,exact_binary_rationals={k:str(F(v)) for k,v in record.items() if k in ['weight_total','weight_valid','value']},relative_envelope=3*2**-52),
    'This is structural admission only. abs(V-T)=2; the approved relative envelope is3*2**-52 and permits V=10000000000000002>T=10000000000000000. Exact stored value is4503599627370495/4503599627370496. No accumulation order or algebraic relation of independently rounded sums is imposed.')

id='M04_rounded_weight_envelope_refuse'
record=deepcopy(record); record['weight_valid']=1e16+32
c=dict(id=id,kind='support_model',purpose='Outside-envelope valid weight still refuses.',stage=stage(op='weighted_mean'),record=record)
refuse(c,'weight_sum_envelope',phase='result_constructor',why='A32-unit difference at1e16 exceeds rel_tol3*2**-52; the finite rounded-sum allowance is bounded.')

write('fixtures.json',{'version':1,'corpus_id':'replicatetable-clean-rebuild-supplement-v1','cases':cases})
write('expected.json',{'version':1,'numeric_comparison':{'abs_tol':1e-12,'rel_tol':1e-12,'scope':'Only computed float values/weight sums; exact keys/types/counts/reasons/units and model-admission literals are never tolerant.'},'cases':outcomes})
write('derivations.json',{'version':1,'cases':derivations})
print('Authored',len(cases),'new cases')
