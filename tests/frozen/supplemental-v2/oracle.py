"""Independent finite scalar/Fraction verifier for the new supplemental corpus.

Arithmetic uses fractions.Fraction and Python/math scalar binary64 only. No array,
unit, dataframe, candidate, recovered-oracle, or runtime imports are permitted.
Frozen expectations are independently authored in author_cases.py. This evaluator
contains only the finite unit pairs and validation rules required by these cases.
It is not the product implementation or a claim of complete unit/parser coverage.
"""
from fractions import Fraction
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
F = Fraction
CONVERSIONS = {(None, None):(F(1),F(0)), ('s','s'):(F(1),F(0)),
               ('s','ms'):(F(1000),F(0)), ('degC','K'):(F(1),F(27315,100)),
               ('degF','degC'):(F(5,9),F(-160,9))}

class Outcome(Exception):
    def __init__(self, category, phase='compile', exit_code=2, code=None):
        self.value=dict(status='refused' if exit_code==2 else 'failed',category=category,
                        phase=phase,exit_code=exit_code,code=code)

def stop(category,phase='compile',exit_code=2,code=None):
    if code is None:
        code = {
            'selected_coordinate':'duplicate_coordinate',
            'stage_count':'invalid_recipe','stage_order':'unsupported_later_stage_weights',
            'stage_dimensions':'invalid_recipe','min_count':'invalid_recipe',
            'duplicate_output_name':'invalid_recipe','unit_assertion':'source_unit_mismatch',
            'weight_unit_assertion':'weight_unit_mismatch','weight_dimensions':'invalid_weights',
            'integer_null_result':'invalid_result','weight_sum_envelope':'invalid_result',
        }[category]
    raise Outcome(category,phase,exit_code,code)

def checked_float(value):
    try:
        result=float(value)
    except OverflowError:
        stop('numeric_overflow','execute',3,'numeric_overflow')
    if not math.isfinite(result):
        stop('numeric_overflow','execute',3,'numeric_overflow')
    return result

def checked_sum(values):
    # Exact mathematical sum is the independent scientific expectation. A scalar
    # float lane checks the explicit intermediate-overflow cases separately.
    exact=F(0); floating=0.0
    for value in values:
        exact += value
        floating=checked_float(floating+checked_float(value))
    return exact

def grid(dims,coordinates):
    if not dims:
        yield ()
        return
    for value in coordinates[dims[0]]:
        for rest in grid(dims[1:],coordinates):
            yield (value,)+rest

def scalar(value,kind):
    if value is None:
        return None
    if type(value) is dict:
        if kind=='weight': stop('invalid_weight','execute',code='nonfinite_weight')
        stop('nonfinite_measurement','execute',code='nonfinite_value')
    if type(value) not in (int,float):
        raise AssertionError('Invalid corpus numeric primitive')
    if type(value) is float and not math.isfinite(value):
        raise AssertionError('Noncanonical JSON source')
    return F(str(value))

def ordered_key(keys):
    return tuple((name,type(keys[name]).__name__,keys[name]) for name in sorted(keys))

def rational(value):
    return None if value is None else str(value)

def evaluate_scientific(case):
    data=case['data']; recipe=case['recipe']; columns=recipe['columns']; row_dims=recipe['row_dims']
    names=[c['name'] for c in columns]
    if len(names)!=len(set(names)): stop('duplicate_output_name','recipe')
    selected=set(); selected_dims=set(row_dims)
    for column in columns:
        stages=column['stages']
        if len(stages)>2: stop('stage_count','recipe')
        selected.add(column['source'])
        for i,st in enumerate(stages):
            if type(st['min_count']) is not int or st['min_count']<1: stop('min_count','recipe')
            if st['op']=='weighted_mean':
                if i!=0: stop('stage_order')
                selected.add(st['weights'])
    for name in selected: selected_dims.update(data['variables'][name]['dims'])
    coordinates={}
    for dim in selected_dims:
        if dim not in data['coords']:
            stop('selected_coordinate',code='missing_row_key' if dim in row_dims else 'missing_coordinate')
        values=data['coords'][dim]['values']
        if any(value is None for value in values):
            stop('selected_coordinate',code='missing_row_key' if dim in row_dims else 'missing_coordinate')
        if len(set((type(v).__name__,v) for v in values))!=len(values): stop('selected_coordinate')
        coordinates[dim]=values
    # Recipe-level dimensional correctness is checked before values are consumed.
    for column in columns:
        source=data['variables'][column['source']]
        if column['source_unit']!=source['units']: stop('unit_assertion')
        dims=list(source['dims'])
        for st in column['stages']:
            if not st['dims'] or len(set(st['dims']))!=len(st['dims']) or not set(st['dims'])<=set(dims) or set(st['dims'])&set(row_dims): stop('stage_dimensions')
            if st['op']=='weighted_mean':
                weight=data['variables'][st['weights']]
                if st['weight_unit']!=weight['units']: stop('weight_unit_assertion')
                if not set(weight['dims'])<=set(source['dims']): stop('weight_dimensions')
            dims=[d for d in dims if d not in st['dims']]
        if not set(dims)<=set(row_dims): raise AssertionError('Unfrozen residual dimension')
        if column['broadcast']!=[d for d in row_dims if d not in dims]: raise AssertionError('Unfrozen broadcast mismatch')
    completed={}; units={}; support=[]; dtype={}
    for column in columns:
        source=data['variables'][column['source']]
        original_dims=list(source['dims']); dims=list(original_dims)
        unit=source['units'] if column['target_unit'] is None else column['target_unit']
        scale,offset=CONVERSIONS[(source['units'],unit)]
        units[column['name']]=unit
        is_direct_identity=not column['stages'] and scale==1 and offset==0
        dtype[column['name']]=source['dtype'] if is_direct_identity else 'float64'
        source_cells={}
        for key,raw in zip(grid(dims,coordinates),source['values'],strict=True):
            value=scalar(raw,'measurement')
            if value is not None:
                if not is_direct_identity:
                    checked_float(checked_float(checked_float(value)*checked_float(scale))+checked_float(offset))
                value=value*scale+offset
            source_cells[key]=value
        cells=source_cells
        reasons={key:['missing_values'] if value is None else [] for key,value in cells.items()}
        for st in column['stages']:
            weight_dims=[]; weight_cells={}
            if st['op']=='weighted_mean':
                weight=data['variables'][st['weights']]; weight_dims=weight['dims']
                factor=F(1,100) if weight['units']=='percent' else F(1)
                if weight['units'] not in (None,'percent'): raise AssertionError('Unfrozen weight unit')
                for key,raw in zip(grid(weight_dims,coordinates),weight['values'],strict=True):
                    w=scalar(raw,'weight')
                    if w is None: stop('invalid_weight','execute',code='nonfinite_weight')
                    if w<0: stop('invalid_weight','execute',code='negative_weight')
                    checked_float(checked_float(w)*checked_float(factor))
                    weight_cells[key]=w*factor
            remaining=[d for d in dims if d not in st['dims']]
            output={}; out_reasons={}; records=[]
            for out_key in grid(remaining,coordinates):
                fixed=dict(zip(remaining,out_key)); values=[]; weights=[]
                for reduced_key in grid(st['dims'],coordinates):
                    selector=fixed | dict(zip(st['dims'],reduced_key))
                    values.append(cells[tuple(selector[d] for d in dims)])
                    weights.append(weight_cells[tuple(selector[d] for d in weight_dims)] if st['op']=='weighted_mean' else F(1))
                valid=[(v,w) for v,w in zip(values,weights) if v is not None]
                n=len(values); nv=len(valid); positive=sum(w>0 for v,w in valid)
                total=checked_sum(weights); valid_total=checked_sum(w for v,w in valid)
                why=[]
                if st['missing']=='propagate' and nv!=n: why.append('missing_values')
                if nv<st['min_count']: why.append('insufficient_count')
                if st['op']=='weighted_mean' and valid_total==0: why.append('zero_weight')
                value=None
                if not why:
                    if st['op'] in ('mean','weighted_mean'):
                        products=[]
                        for v,w in valid:
                            checked_float(checked_float(v)*checked_float(w))
                            products.append(v*w)
                        numerator=checked_sum(products)
                        checked_float(checked_float(numerator)/checked_float(valid_total))
                        value=numerator/valid_total
                    elif st['op']=='min': value=min(v for v,w in valid)
                    elif st['op']=='max': value=max(v for v,w in valid)
                    else: raise AssertionError('Unfrozen operation')
                output[out_key]=value; out_reasons[out_key]=why
                records.append(dict(column=column['name'],stage=st['name'],keys=fixed,n_input=n,n_valid=nv,n_positive_weight_valid=positive,weight_total=total,weight_valid=valid_total,value=value,reasons=why,unit=unit))
            records.sort(key=lambda r:ordered_key(r['keys']))
            support.extend(records); dims=remaining; cells=output; reasons=out_reasons
        completed[column['name']]=(dims,cells,reasons)
    rows=[]; exact_rows=[]
    sorted_coordinates={dim:sorted(coordinates[dim]) for dim in row_dims}
    for row_key in grid(row_dims,sorted_coordinates):
        keys=dict(zip(row_dims,row_key)); values={}; why={}; exact_values={}
        for column in columns:
            name=column['name']; dims,cells,reasons=completed[name]
            selector=tuple(keys[d] for d in dims); value=cells[selector]
            exact_values[name]=rational(value)
            if value is None: values[name]=None
            elif dtype[name].startswith(('int','uint')): values[name]=int(value)
            else:
                values[name]=float(value)
                if not column['stages'] and dtype[name] in ('float32','float64') and value==0:
                    # Fraction deliberately has no signed zero. Recover the source
                    # sign only for exact identity direct data, never guessed.
                    source=data['variables'][column['source']]
                    index=list(grid(source['dims'],coordinates)).index(selector)
                    raw=source['values'][index]
                    if (column['target_unit'] is None or column['target_unit']==source['units']) and type(raw) is float:
                        values[name]=raw
            why[name]=reasons[selector]
        rows.append(dict(keys=keys,values=values,reasons=why))
        exact_rows.append(dict(keys=keys,values=exact_values))
    exact_support=[]
    for record in support:
        exact_support.append({k:record[k] for k in ['column','stage','keys']} | {k:rational(record[k]) for k in ['weight_total','weight_valid','value']})
        for field in ['weight_total','weight_valid','value']:
            record[field]=None if record[field] is None else float(record[field])
    return dict(status='success',result=dict(version=1,row_dims=row_dims,units=units,rows=rows,support=support),exact=dict(rows=exact_rows,support=exact_support)),dtype

def evaluate(case,all_cases):
    try:
        if case['kind']=='execute':
            return evaluate_scientific(case)[0]
        if case['kind']=='result_mutation':
            base=all_cases[case['base_case']]
            result,dtypes=evaluate_scientific(base)
            model=result['result']
            for mutation in case['mutations']:
                parent=model
                for element in mutation['path'][:-1]: parent=parent[element]
                parent[mutation['path'][-1]]=mutation['value']
            for row in model['rows']:
                for name,value in row['values'].items():
                    if dtypes[name].startswith(('int','uint')) and value is None:
                        stop('integer_null_result','result_constructor')
            raise AssertionError('Unfrozen mutation did not refuse')
        if case['kind']=='support_model':
            record=case['record']; total=record['weight_total']; valid=record['weight_valid']
            n=record['n_input']; nv=record['n_valid']; positive=record['n_positive_weight_valid']
            assert 0<=positive<=nv<=n
            assert (valid==0)==(positive==0)
            assert total!=0 or valid==0
            if not (valid<=total or math.isclose(valid,total,rel_tol=(n-1)*2**-52,abs_tol=0)):
                stop('weight_sum_envelope','result_constructor')
            assert record['reasons']==[] and nv>=case['stage']['min_count'] and record['value'] is not None
            return dict(status='accepted',exact_record=record,exact_binary_rationals={k:str(F(v)) for k,v in record.items() if k in ['weight_total','weight_valid','value']},relative_envelope=(n-1)*2**-52)
        raise AssertionError('Unknown case kind')
    except Outcome as outcome:
        return outcome.value

def strict_equal(actual,expected,path=''):
    if type(actual) is not type(expected): raise AssertionError(f'Exact type mismatch at {path}: {type(actual).__name__} != {type(expected).__name__}')
    if type(expected) is dict:
        if actual.keys()!=expected.keys(): raise AssertionError('Field mismatch at '+path)
        for k in expected: strict_equal(actual[k],expected[k],path+'/'+str(k))
    elif type(expected) is list:
        if len(actual)!=len(expected): raise AssertionError('Length mismatch at '+path)
        for i,(a,b) in enumerate(zip(actual,expected)): strict_equal(a,b,path+'/'+str(i))
    elif actual!=expected:
        raise AssertionError(f'Value mismatch at {path}: {actual!r} != {expected!r}')
    elif type(expected) is float and expected==0 and math.copysign(1,actual)!=math.copysign(1,expected):
        raise AssertionError('Signed-zero mismatch at '+path)

def verify():
    cases=json.loads((ROOT/'fixtures.json').read_text())['cases']
    index={c['id']:c for c in cases}
    frozen=json.loads((ROOT/'expected.json').read_text())['cases']
    assert len(index)==len(cases) and index.keys()==frozen.keys()
    for case in cases:
        actual=evaluate(case,index)
        expected=dict(frozen[case['id']])
        dtypes=expected.pop('exact_dtype',None)
        signzeros=expected.pop('exact_signed_zero',[])
        table_headers=expected.pop('table_headers',None)
        support_headers=expected.pop('support_headers',None)
        if dtypes is not None: strict_equal(evaluate_scientific(case)[1],dtypes)
        for assertion in signzeros:
            value=actual
            for part in assertion['path']: value=value[part]
            assert type(value) is float and value==0.0 and (math.copysign(1,value)<0)==assertion['negative']
        if table_headers is not None:
            headers=[f'key:{i:02d}' for i in range(len(case['recipe']['row_dims']))]+[f'{role}:{i:02d}' for i in range(len(case['recipe']['columns'])) for role in ['value','reasons']]
            assert headers==table_headers and len(set(headers))==len(headers)
        if support_headers is not None:
            assert support_headers==['key:00','n_input','n_valid','n_positive_weight_valid','weight_total','weight_valid','reasons','value']
        strict_equal(actual,expected,case['id'])
        print('PASS',case['id'],actual['status'])
    manifest=ROOT/'freeze_sha256.json'
    if manifest.exists():
        for name,item in json.loads(manifest.read_text())['artifacts'].items():
            raw=(ROOT/name).read_bytes()
            assert len(raw)==item['size_bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256'], 'Frozen bytes changed: '+name
        print('PASS immutable artifact manifest')
    print(f'PASS {len(cases)} newly authored cases; candidate code never imported')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.verify: verify()
    else: parser.error('use --verify')
