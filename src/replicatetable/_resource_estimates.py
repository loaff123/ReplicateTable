"""Private symbolic Formula 2 projection. No numerical/native engine imports.

Every repeated result/trace structure is scalar multiplication. This module
projects owned metadata; it does not qualify live source/runtime/unit state.
"""
from dataclasses import dataclass
from . import resources as r
from .codec import OwnedMap
from .errors import Refusal,ComputationError
from . import _native_budget as _native
from ._resource_bounds import (NUMBER,NULL,BOOL,EMPTY,DIGEST,ESTIMATE_KEYS,ESTIMATE_COST,
    QUERY_ENVELOPE_BYTES,_JP,_Fold,_literal_cost,_checked_add,_checked_mul,_sum_counts,
    _count,_check_cap,_shape_product,_ceil_log2_ge2,_utf8,_repeat_cost,_container_cost)
from ._resource_inputs import (_CompilationInput,_VariableFacts,_CoordinateFacts,
    _SourceScalars,_owned_cost,_max_scalar_j,_runtime_cost,_inspection_cost,_recipe_cost,
    _variable_facts,_coordinate_find,_coordinate_totals,_coordinates_cost,_key_bound,
    _unit_cost,_fields,_names,_check_source_base)

REASONS=('missing_values','insufficient_count','zero_weight')
REASON_COST=_owned_cost(REASONS)
ASSURANCE='Source-bound exact same-engine replay; not independent numerical proof or authenticity.'
TRACE_ASSURANCE='Exact source-bound same-engine replay completed before tracing.'
TRACE_NOTICE=('Displayed cells are a bounded prefix. Complete membership is defined by selectors, '
    'support offsets, and the source, plan, and result hashes. Replay is not independent numerical proof.')
REPORT_NOTICE=('Coordinate labels in this report are ASCII JSON scalars. Quoted string labels show every '
    'space as \\u0020; this display does not alter CSV or source. Dtype headers describe exact stored '
    'coordinate types, not inferred types.')
SUPPORT_HEADERS=('n_input','n_valid','n_positive_weight_valid','weight_total','weight_valid','reasons','value')
ROOT_PAYLOADS=('recipe.json','plan.json','result.json','table.csv','schema.json','report.html')


@dataclass(frozen=True,slots=True)
class _ColumnTopology:
    stage_begin: int
    stage_count: int
    source_cells: int
    weight_cells: int
    recipe_column: OwnedMap
    measurement: _VariableFacts
    weight: _VariableFacts | None
    unit_operation: OwnedMap
    weight_unit_operation: OwnedMap | None
    input_dims: tuple
    final_dims: tuple
    broadcast: tuple
    output_dtype: str
    def __post_init__(self):
        for n in (self.stage_begin,self.stage_count,self.source_cells,self.weight_cells):_count(n)
        _count(self.stage_begin,limit=64);_count(self.stage_count,limit=2)
        if type(self.recipe_column) is not OwnedMap or type(self.measurement) is not _VariableFacts:raise Refusal('invalid_source')
        if self.weight is not None and type(self.weight) is not _VariableFacts:raise Refusal('invalid_source')
        if type(self.unit_operation) is not OwnedMap or (self.weight_unit_operation is not None and type(self.weight_unit_operation) is not OwnedMap):raise Refusal('invalid_source')
        _names(self.input_dims);_names(self.final_dims);_names(self.broadcast)
        from .model import numeric_dtype
        numeric_dtype(self.output_dtype)
    def __init_subclass__(cls,**kwargs):raise TypeError('Private resource records are final')


@dataclass(frozen=True,slots=True)
class _StageTopology:
    input_cells: int
    output_cells: int
    support_start: int
    recipe_stage: OwnedMap
    input_dims: tuple
    remaining_dims: tuple
    support_dims: tuple
    def __post_init__(self):
        _count(self.input_cells,limit=r.SHAPE_PRODUCT_LIMIT);_count(self.output_cells,limit=r.SHAPE_PRODUCT_LIMIT)
        _count(self.support_start,limit=r.SUPPORT_RECORDS_LIMIT)
        if not self.input_cells or not self.output_cells or type(self.recipe_stage) is not OwnedMap:raise Refusal('invalid_source')
        _names(self.input_dims);_names(self.remaining_dims);_names(self.support_dims)
    def __init_subclass__(cls,**kwargs):raise TypeError('Private resource records are final')


def _dim_product(inp,names,*,limit=r.SHAPE_PRODUCT_LIMIT,code='invalid_source'):
    n=1
    for name in names:
        if name not in inp.source['dimensions']: raise Refusal('invalid_source')
        n=_checked_mul(n,inp.source['dimensions'][name],limit=limit,code=code)
    return n


def _shape_cost(names):
    return _repeat_cost(len(names),NUMBER)


def _effective_unit(column):
    op=column.unit_operation
    return op['source_unit'] if op['target_unit'] is None else op['target_unit']


def _project_stage(stage):
    f=_Fold(); rec=stage.recipe_stage
    for name in ('name','dims','op','missing','min_count'): f.add(_owned_cost(rec[name]),name)
    f.add(_owned_cost(stage.input_dims),'input_dims'); f.add(_shape_cost(stage.input_dims),'input_shape')
    f.add(_owned_cost(stage.remaining_dims),'remaining_dims'); f.add(_shape_cost(stage.remaining_dims),'remaining_shape')
    f.add(_owned_cost(stage.support_dims),'support_dims'); f.add(NUMBER,'support_count'); f.add(NUMBER,'support_start')
    return f.finish()


def _project_column(column,stages):
    f=_Fold();c=column
    f.add(_literal_cost(c.recipe_column['name']),'name');f.add(_literal_cost(c.measurement.name),'source')
    f.add(_literal_cost(c.measurement.dtype),'source_dtype');f.add(_owned_cost(c.input_dims),'input_dims')
    f.add(_shape_cost(c.input_dims),'input_shape');f.add(_owned_cost(c.final_dims),'final_dims')
    f.add(_owned_cost(c.broadcast),'broadcast');f.add(_literal_cost(c.output_dtype),'output_dtype')
    f.add(_unit_cost(c.unit_operation),'unit_operation')
    if c.weight is None:f.add(NULL,'weight')
    else:
        w=_Fold();w.add(_literal_cost(c.weight.name),'source');w.add(_literal_cost(c.weight.dtype),'dtype')
        w.add(_owned_cost(c.weight.dims),'dims');w.add(_shape_cost(c.weight.dims),'shape')
        w.add(_unit_cost(c.weight_unit_operation),'unit_operation');f.add(w.finish(),'weight')
    s=_Fold()
    for i in range(c.stage_begin,c.stage_begin+c.stage_count):s.add(_project_stage(stages[i]))
    f.add(s.finish(),'stages');return f.finish()


def _project_plan0(inp,top):
    f=_Fold();f.add(NUMBER,'version');f.add(NUMBER,'formula_version')
    f.add(_owned_cost(inp.source['source']),'source');f.add(_recipe_cost(inp.recipe),'recipe')
    f.add(_runtime_cost(inp.runtime),'runtime');f.add(_coordinates_cost(inp.coordinates),'coordinates')
    selected=_Fold();vs=_Fold()
    for v in top[0]:vs.add(_literal_cost(v.name))
    selected.add(vs.finish(),'variables');selected.add(_owned_cost(top[3]),'dimensions')
    selected.add(NUMBER,'numeric_bytes');f.add(selected.finish(),'selected')
    columns=_Fold()
    for c in top[1]:columns.add(_project_column(c,top[2]))
    f.add(columns.finish(),'columns');f.add(_owned_cost(inp.binding),'resource_binding');return f.finish()


def _row_cost(inp,top):
    f=_Fold();f.add(_key_bound(inp.recipe.row_dims,inp.coordinates),'keys')
    values=_Fold();reasons=_Fold()
    for c in top[1]:
        values.add(NUMBER,c.recipe_column['name']);reasons.add(REASON_COST,c.recipe_column['name'])
    f.add(values.finish(),'values');f.add(reasons.finish(),'reasons');return f.finish()


def _support_cost(inp,column,stage):
    f=_Fold();f.add(_literal_cost(column.recipe_column['name']),'column')
    f.add(_literal_cost(stage.recipe_stage['name']),'stage')
    f.add(_key_bound(stage.support_dims,inp.coordinates),'keys')
    for name in ('n_input','n_valid','n_positive_weight_valid','weight_total','weight_valid'):f.add(NUMBER,name)
    f.add(REASON_COST,'reasons');f.add(NUMBER,'value');f.add(_literal_cost(_effective_unit(column)),'unit')
    return f.finish()


def _project_result(inp,top):
    f=_Fold();f.add(NUMBER,'version');f.add(_owned_cost(inp.recipe.row_dims),'row_dims')
    units=_Fold()
    for c in top[1]:units.add(_literal_cost(_effective_unit(c)),c.recipe_column['name'])
    f.add(units.finish(),'units');rows=_rows(inp)
    f.add(_repeat_cost(rows,_row_cost(inp,top)),'rows');support=_Fold()
    for c in top[1]:
        for i in range(c.stage_begin,c.stage_begin+c.stage_count):
            stage=top[2][i];support.add(_support_cost(inp,c,stage),count=stage.output_cells)
    f.add(support.finish(),'support');cost=f.finish()
    return _JP(cost.json_bytes,_checked_add(cost.object_bytes,_checked_mul(136,_checked_add(rows,_support(top)))))


def _table_header_field(position,key_count,column_count):
    _count(key_count,limit=16);_count(column_count,limit=32);_count(position,limit=79)
    if position>=key_count+2*column_count:raise Refusal('invalid_source')
    if position<key_count:return f'key:{position:02d}'
    p=position-key_count
    return f'value:{p//2:02d}' if p%2==0 else f'reasons:{p//2:02d}'


def _support_header_field(position,key_count):
    _count(key_count,limit=16);_count(position,limit=22)
    if position>=key_count+7:raise Refusal('invalid_source')
    return f'key:{position:02d}' if position<key_count else SUPPORT_HEADERS[position-key_count]


def _csv_string(value):return _checked_add(2,_checked_mul(2,_utf8(value)))


def _csv_record_bound(fields):
    if type(fields) is not tuple:raise Refusal('invalid_source')
    return _checked_add(_sum_counts(fields),max(len(fields)-1,0)+1)


def _schema_field(position,header,role,name,dtype,nullable,*,table,unit=None):
    f=_Fold();f.add(NUMBER,'position');f.add(_literal_cost(header),'header')
    f.add(_literal_cost(role),'role');f.add(_literal_cost(name),'name');f.add(_literal_cost(dtype),'dtype')
    if table:f.add(_literal_cost(unit),'unit')
    f.add(BOOL,'nullable');return f.finish()


def _table_schema(inp,top):
    fields=_Fold();scratch=0
    for position,name in enumerate(inp.recipe.row_dims):
        coord=_coordinate_find(name,inp.coordinates)
        q=_schema_field(position,_table_header_field(position,len(inp.recipe.row_dims),len(top[1])),
            'key',name,coord.coordinate.dtype,False,table=True)
        scratch=max(scratch,q.object_bytes);fields.add(q)
    position=len(inp.recipe.row_dims)
    for c in top[1]:
        for role in ('value','reasons'):
            q=_schema_field(position,_table_header_field(position,len(inp.recipe.row_dims),len(top[1])),role,
                c.recipe_column['name'],c.output_dtype if role=='value' else 'reason-array',
                role=='value' and c.output_dtype.startswith('float'),table=True,
                unit=_effective_unit(c) if role=='value' else None)
            fields.add(q);scratch=max(scratch,q.object_bytes);position+=1
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost('table'),'kind')
    f.add(_owned_cost(inp.recipe.row_dims),'row_dims');f.add(fields.finish(),'columns')
    return f.finish(),scratch


def _support_schema(inp,c,s):
    fields=_Fold();scratch=0
    for position,name in enumerate(s.support_dims):
        coord=_coordinate_find(name,inp.coordinates)
        q=_schema_field(position,_support_header_field(position,len(s.support_dims)),
            'key',name,coord.coordinate.dtype,False,table=False)
        scratch=max(scratch,q.object_bytes);fields.add(q)
    position=len(s.support_dims)
    for index,name in enumerate(SUPPORT_HEADERS):
        role='count' if index<3 else 'weight' if index<5 else name
        dtype='int64' if index<3 else 'reason-array' if name=='reasons' else 'float64'
        q=_schema_field(position,name,role,name,dtype,name=='value',table=False)
        scratch=max(scratch,q.object_bytes);fields.add(q);position+=1
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost('support'),'kind')
    f.add(_literal_cost(c.recipe_column['name']),'column');f.add(_literal_cost(s.recipe_stage['name']),'stage')
    f.add(_owned_cost(s.support_dims),'key_dims');f.add(_literal_cost(_effective_unit(c)),'unit')
    f.add(fields.finish(),'columns');return f.finish(),scratch


def _csv_bounds(inp,top,c=None,s=None):
    names=inp.recipe.row_dims if s is None else s.support_dims
    k=len(names)+(2*len(top[1]) if s is None else 7)
    header=row=0
    for position in range(k):
        h=_table_header_field(position,len(names),len(top[1])) if s is None else _support_header_field(position,len(names))
        header=_checked_add(header,_csv_string(h))
        if position<len(names):
            coord=_coordinate_find(names[position],inp.coordinates)
            field=2+2*coord.max_utf8 if coord.coordinate.dtype.startswith('<U') else 32
        elif s is None:field=32 if (position-len(names))%2==0 else 2+2*REASON_COST.json_bytes
        else:field=2+2*REASON_COST.json_bytes if position-len(names)==5 else 32
        row=_checked_add(row,field)
    return _checked_add(header,max(k-1,0)+1),_checked_add(row,max(k-1,0)+1)


def _stage_path(column_index,stage_index,schema=False):
    _count(column_index,limit=31);_count(stage_index,limit=1)
    if type(schema) is not bool:raise Refusal('invalid_source')
    return f'support/c{column_index:02d}-s{stage_index:02d}'+('.schema.json' if schema else '.csv')


def _payload_paths(top):
    # Bounded path ledger, never output rows. Released before trace projection.
    paths=list(ROOT_PAYLOADS)
    for ci,c in enumerate(top[1]):
        for si in range(c.stage_count):
            paths.append(_stage_path(ci,si));paths.append(_stage_path(ci,si,True))
    return tuple(paths)


def _manifest_cost(inp,top,*,include_runtime):
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost('replicatetable-bundle-v2'),'bundle_format')
    f.add(NUMBER,'formula_version');f.add(_owned_cost(inp.source['source']),'source')
    for name in ('recipe_sha256','plan_sha256','result_sha256'):f.add(DIGEST,name)
    if include_runtime:f.add(_runtime_cost(inp.runtime),'runtime')
    f.add(DIGEST,'runtime_sha256');files=_Fold();entry=_Fold()
    entry.add(DIGEST,'sha256');entry.add(NUMBER,'size_bytes');ep=entry.finish()
    for name in ROOT_PAYLOADS:files.add(ep,name)
    for ci,c in enumerate(top[1]):
        for si in range(c.stage_count):
            files.add(ep,_stage_path(ci,si));files.add(ep,_stage_path(ci,si,True))
    f.add(files.finish(),'files');totals=_Fold()
    for name in ('rows','support_records','payload_bytes'):totals.add(NUMBER,name)
    f.add(totals.finish(),'totals');f.add(_literal_cost(ASSURANCE),'assurance');return f.finish()


def _finding_cost():
    f=_Fold();f.add(_JP(770,640),'code');f.add(_JP(3074,2176),'message');f.add(NUMBER,'exit_code')
    return f.finish()


def _checks_cost():
    f=_Fold()
    for name in ('structure','source_binding','runtime_binding','replay','report'):
        f.add(_literal_cost('not_attempted'),name)
    return f.finish()


def _receipt_costs(source):
    # Four named shapes, no invented enclosing list charge in schema_objects.
    src=_owned_cost(source);v=_Fold();v.add(NUMBER,'version');v.add(_literal_cost('cancelled'),'status')
    v.add(_checks_cost(),'checks');v.add(src,'source')
    for name in ('plan_sha256','result_sha256','manifest_sha256'):v.add(DIGEST,name)
    v.add(_finding_cost(),'finding');v.add(BOOL,'committed')
    b=_Fold();b.add(NUMBER,'version');b.add(_literal_cost('committed'),'status');b.add(src,'source')
    for name in ('recipe_sha256','plan_sha256','result_sha256','runtime_sha256','manifest_sha256'):b.add(DIGEST,name)
    b.add(NUMBER,'bundle_bytes');b.add(BOOL,'interrupted_after_commit')
    p=_Fold();p.add(NUMBER,'version');p.add(_literal_cost('committed'),'status');p.add(DIGEST,'plan_sha256')
    p.add(NUMBER,'plan_bytes');p.add(BOOL,'interrupted_after_commit')
    ready=_Fold();ready.add(NUMBER,'version');ready.add(_literal_cost('bundle'),'kind');ready.add(src,'source')
    for name in ('recipe_sha256','plan_sha256','result_sha256','runtime_sha256','manifest_sha256'):ready.add(DIGEST,name)
    ready.add(NUMBER,'output_bytes')
    return v.finish(),b.finish(),p.finish(),ready.finish()


def _summary_cost(inp,top):
    f=_Fold();f.add(_owned_cost(inp.source['source']),'source')
    for name in ('recipe_sha256','plan_sha256','result_sha256','runtime_sha256'):f.add(DIGEST,name)
    f.add(_owned_cost(inp.recipe.row_dims),'row_dims');columns=_Fold();reasons=_Fold();stages=_Fold()
    for c in top[1]:
        cf=_Fold();cf.add(_literal_cost(c.recipe_column['name']),'name')
        cf.add(_literal_cost(_effective_unit(c)),'effective_unit');cf.add(_owned_cost(c.broadcast),'broadcast');columns.add(cf.finish())
        cr=_Fold();cr.add(_literal_cost(c.recipe_column['name']),'column')
        for name in REASONS:cr.add(NUMBER,name)
        reasons.add(cr.finish())
        for i in range(c.stage_begin,c.stage_begin+c.stage_count):
            sr=_Fold();sr.add(_literal_cost(c.recipe_column['name']),'column')
            sr.add(_literal_cost(top[2][i].recipe_stage['name']),'stage')
            for name in REASONS:sr.add(NUMBER,name)
            stages.add(sr.finish())
    f.add(columns.finish(),'columns');totals=_Fold();totals.add(NUMBER,'rows');totals.add(NUMBER,'support_records')
    f.add(totals.finish(),'totals');f.add(reasons.finish(),'column_reasons');f.add(stages.finish(),'stage_reasons')
    return f.finish()


def _preview_bound(count,headers,cells):
    _count(count);_count(headers);_count(cells)
    return _sum_counts((512,headers,_checked_mul(min(100,count),_checked_add(32,cells))))


def _preview(inp,top,c=None,s=None):
    names=inp.recipe.row_dims if s is None else s.support_dims
    header=cells=0
    for name in names:
        coord=_coordinate_find(name,inp.coordinates)
        header=_checked_add(header,32+6*_utf8(name)+3+6*_utf8(coord.coordinate.dtype))
        cells=_checked_add(cells,32+(6*coord.max_utf8+2 if coord.coordinate.dtype.startswith('<U') else 32))
    if s is None:
        for column in top[1]:
            header=_checked_add(header,2*(32+6*_utf8(column.recipe_column['name'])))
            cells=_checked_add(cells,(32+32)+(32+6*REASON_COST.json_bytes))
    else:
        for name in SUPPORT_HEADERS:
            header=_checked_add(header,32+6*_utf8(name))
            cells=_checked_add(cells,32+(6*REASON_COST.json_bytes if name=='reasons' else 32))
    return _preview_bound(_rows(inp) if s is None else s.output_cells,header,cells)


def _project_report(inp,top):
    total=_sum_counts((32768,222,_checked_mul(6,_summary_cost(inp,top).json_bytes),_preview(inp,top)))
    for c in top[1]:
        for i in range(c.stage_begin,c.stage_begin+c.stage_count):
            total=_checked_add(total,_preview(inp,top,c,top[2][i]))
    return _check_cap('report',total)


@dataclass(frozen=True,slots=True)
class _OutputBounds:
    recipe_json: int
    plan_json: int
    result_json: int
    result_objects: int
    table_csv: int
    stage_csv: int
    schema_json: int
    report: int
    manifest_json: int
    bundle: int
    schema_objects: int
    record_scratch: int
    max_scalar_j: int
    support_blocks: int
    row_j: int
    row_p: int
    def __post_init__(self):
        for value in (self.recipe_json,self.plan_json,self.result_json,self.result_objects,self.table_csv,
                      self.stage_csv,self.schema_json,self.report,self.manifest_json,self.bundle,
                      self.schema_objects,self.record_scratch,self.max_scalar_j,self.support_blocks,self.row_j,self.row_p):_count(value)
    def __init_subclass__(cls,**kwargs):raise TypeError('Private resource records are final')


def _project_outputs(inp,top,plan0):
    recipe=_recipe_cost(inp.recipe).json_bytes+1
    plan=_check_cap('metadata',_sum_counts((plan0.json_bytes,1,ESTIMATE_COST.json_bytes,1)))
    result=_project_result(inp,top);b=_check_cap('bundle',result.json_bytes+1)
    row=_row_cost(inp,top);table_schema,scratch=_table_schema(inp,top)
    schemaj=_check_cap('metadata',table_schema.json_bytes+1);schemap=table_schema.object_bytes
    scratch=max(scratch,row.object_bytes);head,record=_csv_bounds(inp,top)
    table=_checked_add(head,_checked_mul(_rows(inp),record));csv=0
    for c in top[1]:
        for i in range(c.stage_begin,c.stage_begin+c.stage_count):
            s=top[2][i];schema,one_scratch=_support_schema(inp,c,s)
            schemaj=_checked_add(schemaj,_check_cap('metadata',schema.json_bytes+1))
            schemap=_checked_add(schemap,schema.object_bytes)
            scratch=max(scratch,one_scratch,_support_cost(inp,c,s).object_bytes)
            head,record=_csv_bounds(inp,top,c,s)
            csv=_checked_add(csv,_checked_add(head,_checked_mul(s.output_cells,record)))
    report=_project_report(inp,top)
    manifest=_check_cap('metadata',_manifest_cost(inp,top,include_runtime=True).json_bytes+1)
    schemap=_checked_add(schemap,_manifest_cost(inp,top,include_runtime=False).object_bytes)
    for receipt in _receipt_costs(inp.source['source']):schemap=_checked_add(schemap,receipt.object_bytes)
    bundle=_check_cap('bundle',_sum_counts((recipe,plan,b,table,csv,schemaj,report,manifest)))
    maxj=max(_max_scalar_j(inp.source),_max_scalar_j(inp.runtime),_max_scalar_j(inp.recipe.columns),
             _max_scalar_j(inp.recipe.row_dims),_literal_cost(TRACE_NOTICE).json_bytes,
             _literal_cost(REPORT_NOTICE).json_bytes)
    for coord in inp.coordinates:maxj=max(maxj,coord.max_token_j)
    for pair in inp.units:
        maxj=max(maxj,_max_scalar_j(pair[0]))
        if pair[1] is not None:maxj=max(maxj,_max_scalar_j(pair[1]))
    return _OutputBounds(recipe,plan,b,result.object_bytes,table,csv,schemaj,report,manifest,
                         bundle,schemap,scratch,maxj,len(top[2]),row.json_bytes,row.object_bytes)


def _selector_cost(names,fixed):
    f=_Fold()
    for name in names:f.add(NUMBER if name in fixed else NULL)
    return f.finish()


def _source_cell_cost(inp,c):
    f=_Fold();f.add(_shape_cost(c.input_dims),'indices');labels=_Fold()
    for name in c.input_dims:
        coord=_coordinate_find(name,inp.coordinates);labels.add(_JP(coord.max_label_j,coord.max_label_p))
    f.add(labels.finish(),'labels');f.add(NUMBER,'raw');f.add(NUMBER,'converted')
    f.add(NULL if c.weight is None else NUMBER,'raw_weight')
    f.add(NUMBER if c.stage_count or c.weight is not None else NULL,'normalized_weight')
    exclusion=_literal_cost('missing_value') if c.measurement.dtype.startswith('float') else _literal_cost('zero_weight') if c.weight is not None else NULL
    f.add(exclusion,'exclusion_reason');return f.finish()


def _trace_record_cost(inp,c,s):
    f=_Fold();f.add(NUMBER,'support_index');f.add(_support_cost(inp,c,s),'record')
    # Remaining dimensions are fixed; removed dimensions range over membership.
    f.add(_selector_cost(s.input_dims,s.remaining_dims),'membership');return f.finish()


def _section_counters(f):
    for name in ('total','shown'):f.add(NUMBER,name)
    f.add(BOOL,'truncated')
    for name in ('limit_omitted','byte_omitted'):f.add(NUMBER,name)


def _trace_column(inp,c,stages):
    f=_Fold()
    for name,value in (('name',c.recipe_column['name']),('source',c.measurement.name),
                       ('source_dtype',c.measurement.dtype),('converted_dtype',c.output_dtype),('output_dtype',c.output_dtype)):
        f.add(_literal_cost(value),name)
    for name,value in (('input_dims',c.input_dims),('final_dims',c.final_dims),('broadcast',c.broadcast)):
        f.add(_owned_cost(value),name)
    conv=_Fold();op=c.unit_operation
    for name in ('source_unit','target_unit'):conv.add(_literal_cost(op[name]),name)
    conv.add(_literal_cost(_effective_unit(c)),'effective_unit');conv.add(NUMBER,'scale');conv.add(NUMBER,'offset')
    f.add(conv.finish(),'conversion')
    if c.weight is None:f.add(NULL,'weight')
    else:
        w=_Fold();w.add(_literal_cost(c.weight.name),'source');w.add(_literal_cost(c.weight.dtype),'dtype')
        w.add(_owned_cost(c.weight.dims),'dims');w.add(_literal_cost(c.weight_unit_operation['source_unit']),'source_unit')
        w.add(_literal_cost('dimensionless'),'unit');w.add(NUMBER,'scale');w.add(NUMBER,'offset');f.add(w.finish(),'weight')
    f.add(NUMBER,'value');f.add(REASON_COST,'reasons');source=_Fold();_section_counters(source)
    source.add(_selector_cost(c.input_dims,inp.recipe.row_dims),'selection');source.add(EMPTY,'cells');f.add(source.finish(),'source_cells')
    sf=_Fold()
    for index in range(c.stage_begin,c.stage_begin+c.stage_count):
        s=stages[index];section=_Fold();_section_counters(section)
        for name in ('name','dims','op','missing','min_count'):section.add(_owned_cost(s.recipe_stage[name]),name)
        section.add(_owned_cost(s.input_dims),'input_dims');section.add(_owned_cost(s.remaining_dims),'remaining_dims')
        section.add(NULL if index==c.stage_begin else NUMBER,'input_stage');section.add(NUMBER,'support_start')
        section.add(EMPTY,'records');sf.add(section.finish())
    f.add(sf.finish(),'stages');return f.finish()


def _trace_skeleton(inp,top,limit):
    _count(limit,'invalid_explanation',limit=1000)
    if not limit:raise Refusal('invalid_explanation')
    f=_Fold();f.add(NUMBER,'version');f.add(_owned_cost(inp.source['source']),'source')
    for name in ('recipe_sha256','plan_sha256','result_sha256','runtime_sha256'):f.add(DIGEST,name)
    f.add(_owned_cost(inp.recipe.row_dims),'row_dims');f.add(_key_bound(inp.recipe.row_dims,inp.coordinates),'key')
    coords=_Fold()
    for c in inp.coordinates:
        cf=_Fold();cf.add(_literal_cost(c.coordinate.dtype),'dtype');cf.add(NUMBER,'length');coords.add(cf.finish(),c.name)
    f.add(coords.finish(),'coordinates');f.add(NUMBER,'limit');f.add(BOOL,'byte_truncated')
    f.add(_literal_cost(TRACE_ASSURANCE),'assurance');f.add(_literal_cost(TRACE_NOTICE),'notice');cols=_Fold()
    for c in top[1]:cols.add(_trace_column(inp,c,top[2]))
    f.add(cols.finish(),'columns');return f.finish()


def _api_shell(kind):
    if type(kind) is not str or kind not in ('descriptor','prepared','materialized','plan','result','explanation','bundle_receipt','verification'):
        raise Refusal('invalid_worker_response')
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost(kind),'kind')
    f.add(_JP(0,0),'model');f.add(EMPTY,'arrays');return f.finish()


def _standalone_reservation(source_base,metadata_bytes,metadata_objects,selected_bytes,*,
        source_kind='memory',held_coordinates=0,recipe_objects=0,raw_bytes=0,saved_objects=0):
    """Complete scalar standalone worksheet, never actual admission authority.

    metadata_objects means observed Pscan, not a sender's semantic estimate.
    Held Coordinate/Recipe/raw saved-plan state stays outside the phase max.
    File callers separately check actual file bytes; full base is not128MiB
    capped. Initial lexical/raw guards and real helper release are still owed.
    """
    _check_source_base(source_kind,source_base)
    _check_cap('metadata',raw_bytes);_count(saved_objects,limit=r.LOGICAL_JOURNEY_LIMIT)
    total=_native._standalone_guard(source_base,metadata_bytes,metadata_objects,selected_bytes,
        source_kind=source_kind,held_coordinates=held_coordinates,recipe_objects=recipe_objects)
    return _native._canonical_route_guard(total,raw_bytes=raw_bytes,saved_objects=saved_objects)


def _framed_size(metadata_bytes,raw_bytes):
    _count(metadata_bytes);_check_cap('selected',raw_bytes)
    return _sum_counts((24,metadata_bytes,raw_bytes))


def _parent_reservation(lengths,original_objects,fd_slots):
    """Isolated historical R10 worksheet, NOT complete native admission.

    It omits retained scientific caller models and cannot guard a native route.
    Complete canonical transport uses W+max(Twire,965Ncontrol), and standalone
    routes use _native_budget's complete K and named extra inputs. This helper
    remains solely to test the original isolated-counterexample arithmetic.
    """
    if type(lengths) is not tuple or len(lengths)>3:raise Refusal('invalid_worker_response')
    n=0
    for length in lengths:
        _count(length,'metadata_bytes_limit',limit=r.PARENT_ENVELOPE_BYTES_LIMIT)
        n=_checked_add(n,length)
    _count(original_objects);_count(fd_slots,limit=r.PARENT_FD_STATE_LIMIT)
    return _check_cap('journey',_sum_counts((r.RUNTIME_ALLOWANCE,r.CONTROL_STATE_BYTES,
        3*r.SERIAL_BUFFER_BYTES,_checked_mul(965,n),original_objects,512*fd_slots)))


def _nonresult_prepass(raw,*,metadata_limit,baseline_bytes):
    """B1 scan accounting only: no parse/model construction or trusted bypass.

    The owning transport first qualifies the finite return kind and reserves
    its local projection before receiving raw. B1 checks raw/baseline before
    scanning, and each live key scratch before slice/decode. This helper is
    deliberately not a result loader and cannot authorize result slot credit.
    """
    from .codec import json_prepass
    scan=json_prepass(raw,limit=metadata_limit,baseline_bytes=baseline_bytes)
    _check_cap('journey',_checked_add(baseline_bytes,_nonresult_decode_bytes(scan)))
    return scan


def _nonresult_decode_bytes(scan):
    from .codec import JsonPreflight
    if type(scan) is not JsonPreflight:raise Refusal('invalid_worker_response')
    return _checked_add(_checked_mul(5,scan.raw_bytes),_checked_mul(3,scan.object_bytes))


def _result_slot_reservation(result_objects,result_bytes,one_record_scratch,*,validator_forests=0):
    """Arithmetic-only CALLER/PARSE/FINAL proof obligation, NOT a loader.

    No caller context is accepted or inferred here; the later owning API must
    establish exact three-slot coverage and release. Generic strict_loads is
    never called with a lowered baseline or supplied counters by this module.
    """
    _count(validator_forests)
    if validator_forests:raise Refusal('estimated_memory_limit')
    _count(result_objects);_count(result_bytes);_count(one_record_scratch)
    return _check_cap('journey',_sum_counts((_checked_mul(3,result_objects),
        _checked_mul(6,result_bytes),one_record_scratch)))


def _validate_binding(binding):
    _fields(binding,('kind','base_bytes','owners','descriptor_bytes'))
    _owned_cost(binding)  # qualify every exact primitive before comparisons
    if type(binding['kind']) is not str or binding['kind'] not in ('memory','file'):
        raise Refusal('invalid_source')
    _check_source_base(binding['kind'],binding['base_bytes']);_count(binding['descriptor_bytes'])
    owners=binding['owners']
    if type(owners) is not tuple or len(owners)>80:raise Refusal('invalid_source')
    previous=None
    for owner in owners:
        _fields(owner,('kind','name','terminal_bytes','header_bytes','logical_bytes'))
        if type(owner['kind']) is not str or owner['kind'] not in ('coordinate','variable'):
            raise Refusal('invalid_source')
        from .model import validate_name
        validate_name(owner['name'])
        for name in ('terminal_bytes','header_bytes','logical_bytes'):_count(owner[name])
        key=(owner['kind'],owner['name'])
        if previous is not None and previous>=key:raise Refusal('invalid_source')
        previous=key
    if binding['kind']=='file' and owners:raise Refusal('invalid_source')


def _call_total(baseline,saved_binding,fresh_binding,extra_sources,cache_costs,*,required_count,distinct_count):
    """Post-measurement scalar accounting, not Dataset discovery/deduplication.

    Only the future exact three-slot caller can establish freshness and actual
    Dataset identity. It must finish safe layout/source measurement first,
    thereby preserving earlier source_bytes_limit/unsupported-layout refusals.
    """
    _validate_binding(saved_binding);_validate_binding(fresh_binding)
    if saved_binding!=fresh_binding:
        raise Refusal('source_resource_binding_mismatch',
            'Source resource binding changed; inspect the current source and compile a new plan before retrying.')
    _check_cap('journey',baseline)
    _count(required_count,limit=3);_count(distinct_count,limit=3)
    if distinct_count>required_count:raise Refusal('invalid_source')
    if type(extra_sources) is not tuple or len(extra_sources)>2 or type(cache_costs) is not tuple or len(cache_costs)>3:
        raise Refusal('invalid_source')
    x=cache=0
    # X contains distinct non-anchor Dataset bases, so these remain memory
    # bases. File handles do not create extra Dataset slots.
    for base in extra_sources:x=_checked_add(x,_check_cap('source_base',base))
    for cost in cache_costs:cache=_checked_add(cache,cost,limit=r.LOGICAL_JOURNEY_LIMIT,code='estimated_memory_limit')
    total=_sum_counts((baseline,x,cache))
    return OwnedMap._from_checked((('admitted',total<=r.LOGICAL_JOURNEY_LIMIT),('baseline_bytes',baseline),
        ('cache_bytes',cache),('distinct_dataset_count',distinct_count),('extra_source_bytes',x),
        ('formula_version',2),('limit_bytes',r.LOGICAL_JOURNEY_LIMIT),('required_dataset_count',required_count),
        ('total_bytes',total),('version',2)))


@dataclass(frozen=True,slots=True)
class _EmissionBudget:
    def __init_subclass__(cls,**kwargs):raise TypeError('Private resource records are final')
    path: str
    kind: str
    estimated_bytes: int
    hard_cap: int
    group: int
    def __post_init__(self):
        _utf8(self.path,maximum=r.BUNDLE_PATH_BYTES_LIMIT)
        if not self.path or self.path.startswith('/') or '\\' in self.path or any(p in ('','..','.') for p in self.path.split('/')):
            raise Refusal('invalid_bundle')
        if type(self.kind) is not str or self.kind not in ('recipe','metadata','bundle','report','trace'):
            raise Refusal('invalid_source')
        _count(self.hard_cap);_count(self.estimated_bytes,limit=self.hard_cap);_count(self.group)
        _check_cap(self.kind,self.hard_cap)


def _check_emission(current,fragment_bytes,budget):
    if type(budget) is not _EmissionBudget:raise Refusal('invalid_source')
    _count(current);_count(fragment_bytes)
    # Determine the first bound before addition, allocation, append, or write.
    if current>budget.estimated_bytes or fragment_bytes>budget.estimated_bytes-current:
        if budget.estimated_bytes<budget.hard_cap:
            raise ComputationError('resource_estimate_mismatch')
        raise Refusal({'report':'report_bytes_limit','trace':'explanation_bytes_limit',
            'bundle':'bundle_bytes_limit','metadata':'metadata_bytes_limit','recipe':'recipe_bytes_limit'}[budget.kind])
    return _checked_add(current,fragment_bytes)


def _find_variable(name,variables):
    for variable in variables:
        if variable.name==name:return variable
    raise Refusal('invalid_source')


def _iter_variable_facts(inp,selected):
    """Bounded internal producer, never a caller-supplied iterable seam."""
    for name in selected:
        if name not in inp.source['variables']:raise Refusal('invalid_source')
        yield _variable_facts(name,inp.source['variables'][name],inp.source['dimensions'])


def _iter_stage_topology(inp,variables):
    # Fill the sole immutable stage table. No parallel Python list owns stage
    # records. These bounded producer frames use the existing walker reserve.
    offset=0
    for index,recipe_column in enumerate(inp.recipe.columns):
        source=_find_variable(recipe_column['source'],variables)
        actual_unit=inp.source['variables'][source.name]['unit']
        if recipe_column['source_unit']!=actual_unit:
            raise Refusal('missing_unit_assertion' if recipe_column['source_unit'] is None and actual_unit is not None else 'source_unit_mismatch')
        operation,weight_operation=inp.units[index]
        if operation['source_unit']!=actual_unit or operation['target_unit']!=recipe_column['target_unit']:
            raise Refusal('invalid_source')
        weight=None
        if recipe_column['stages'] and recipe_column['stages'][0]['op']=='weighted_mean':
            weight=_find_variable(recipe_column['stages'][0]['weights'],variables)
            if any(dim not in source.dims for dim in weight.dims):raise Refusal('invalid_weights')
            if weight_operation is None:raise Refusal('invalid_weights')
        elif weight_operation is not None:raise Refusal('invalid_weights')
        current=source.dims;cells=source.cells
        for recipe_stage in recipe_column['stages']:
            removed=recipe_stage['dims']
            if any(dim not in current or dim in inp.recipe.row_dims for dim in removed):raise Refusal('invalid_recipe')
            remaining=tuple(dim for dim in current if dim not in removed)
            support=tuple(sorted(remaining));out=_dim_product(inp,remaining)
            offset=_checked_add(offset,out,limit=r.SUPPORT_RECORDS_LIMIT,code='support_records_limit')
            yield _StageTopology(cells,out,offset-out,recipe_stage,current,remaining,support)
            current=remaining;cells=out
        if any(dim not in inp.recipe.row_dims for dim in current):raise Refusal('residual_dimension')
        if recipe_column['broadcast']!=tuple(dim for dim in inp.recipe.row_dims if dim not in current):
            raise Refusal('unapproved_broadcast')


def _iter_column_topology(inp,variables,stages):
    # Source/weight/unit/transition checks completed while producing stages,
    # including zero-stage columns. Reuse final stage dimensions by identity.
    begin=0
    for index,recipe_column in enumerate(inp.recipe.columns):
        source=_find_variable(recipe_column['source'],variables)
        operation,weight_operation=inp.units[index]
        count=len(recipe_column['stages']);weight=None
        if count and recipe_column['stages'][0]['op']=='weighted_mean':
            weight=_find_variable(recipe_column['stages'][0]['weights'],variables)
        final=source.dims if not count else stages[begin+count-1].remaining_dims
        dtype=source.dtype if not count and operation['scale']==1 and operation['offset']==0 else 'float64'
        yield _ColumnTopology(begin,count,source.cells,0 if weight is None else weight.cells,
            recipe_column,source,weight,operation,weight_operation,source.dims,final,recipe_column['broadcast'],dtype)
        begin+=count


def _derive_topology(inp):
    if type(inp) is not _CompilationInput:raise Refusal('invalid_source')
    # Two finite name unions. Names are not a second table of resource records.
    selected=[];dimensions=list(inp.recipe.row_dims)
    for column in inp.recipe.columns:
        name=column['source']
        if name not in selected:selected.append(name)
        if column['stages'] and column['stages'][0]['op']=='weighted_mean':
            name=column['stages'][0]['weights']
            if name not in selected:selected.append(name)
    if len(selected)>64:raise Refusal('invalid_source')
    selected.sort()
    variables=tuple(_iter_variable_facts(inp,selected))
    del selected
    for fact in variables:
        for dim in fact.dims:
            if dim not in dimensions:dimensions.append(dim)
    dimensions.sort()
    # Only this at-most-rank16 list/tuple transition uses the already named
    # dimension-finalization scratch. The old list dies on assignment.
    dimensions=tuple(dimensions)
    for name in inp.recipe.row_dims:
        if name not in inp.source['dimensions']:raise Refusal('invalid_source')
        if not any(c.name==name for c in inp.coordinates):raise Refusal('missing_row_key')
    for name in dimensions:
        coord=_coordinate_find(name,inp.coordinates)
        if coord.length!=inp.source['dimensions'][name]:raise Refusal('invalid_coordinate')
    if len(inp.coordinates)!=len(dimensions):raise Refusal('invalid_source_phase')
    stages=tuple(_iter_stage_topology(inp,variables))
    columns=tuple(_iter_column_topology(inp,variables,stages))
    # Each exact table is constructed once, then borrowed by this carrier.
    # No mutable record-table builders, copies or live producer frames remain.
    top=(variables,columns,stages,dimensions)
    _rows(inp);_support(top);_selected_numeric(top);_work(inp,top);_scratch(top)
    return top


def _rows(inp):return _dim_product(inp,inp.recipe.row_dims,limit=r.OUTPUT_ROWS_LIMIT,code='output_rows_limit')


def _support(top):
    total=0
    for s in top[2]:total=_checked_add(total,s.output_cells,limit=r.SUPPORT_RECORDS_LIMIT,code='support_records_limit')
    return total


def _selected_numeric(top):
    total=0
    for v in top[0]:total=_checked_add(total,v.nbytes,limit=r.SELECTED_NUMERIC_BYTES_LIMIT,code='selected_numeric_bytes_limit')
    return total


def _scratch(top):
    maximum=0
    for c in top[1]:
        w=_checked_add(_checked_mul(32,c.source_cells),_checked_mul(16,c.weight_cells))
        for i in range(c.stage_begin,c.stage_begin+c.stage_count):
            s=top[2][i];w=_sum_counts((w,_checked_mul(64,s.input_cells),_checked_mul(128,s.output_cells)))
        maximum=max(maximum,w)
    return maximum


def _work(inp,top):
    v=0
    def add(amount,current):return _checked_add(current,amount,limit=r.WORK_CELL_LIMIT,code='work_cell_limit')
    for name in top[3]:
        length=inp.source['dimensions'][name];v=add(_checked_mul(length,1+_ceil_log2_ge2(length)),v)
    for c in top[1]:
        v=add(_checked_mul(4,c.source_cells),v);v=add(_checked_mul(3,c.weight_cells),v)
        for i in range(c.stage_begin,c.stage_begin+c.stage_count):
            s=top[2][i];v=add(_checked_mul(12,s.input_cells),v);v=add(_checked_mul(8,s.output_cells),v)
    v=add(_checked_mul(4,_checked_mul(_rows(inp),len(top[1]))),v)
    return add(_checked_mul(8,_support(top)),v)


def _ranged_cells(inp,names):
    total=1
    for name in names:
        if name not in inp.recipe.row_dims:total=_checked_mul(total,inp.source['dimensions'][name],limit=r.SHAPE_PRODUCT_LIMIT,code='invalid_source')
    return total


def _trace_max_scalar(inp,top):
    maximum=max(32,386,_literal_cost(TRACE_NOTICE).json_bytes,_literal_cost(TRACE_ASSURANCE).json_bytes)
    for coordinate in inp.coordinates:maximum=max(maximum,coordinate.max_token_j,_literal_cost(coordinate.name).json_bytes)
    for c in top[1]:
        for value in (c.recipe_column['name'],c.measurement.name,c.measurement.dtype,c.output_dtype,
                      c.unit_operation['source_unit'],c.unit_operation['target_unit']):
            maximum=max(maximum,_literal_cost(value).json_bytes)
        if c.weight is not None:
            maximum=max(maximum,_literal_cost(c.weight.name).json_bytes,
                _literal_cost(c.weight.dtype).json_bytes,_literal_cost(c.weight_unit_operation['source_unit']).json_bytes)
        for i in range(c.stage_begin,c.stage_begin+c.stage_count):
            maximum=max(maximum,_literal_cost(top[2][i].recipe_stage['name']).json_bytes)
    return maximum


def _project_trace(inp,top,*,limit):
    skeleton=_trace_skeleton(inp,top,limit);sbytes=_check_cap('trace',skeleton.json_bytes+1)
    sobjects=_checked_add(skeleton.object_bytes,1024)
    candidate=sbytes;objects=shown=worst=0
    # One section at a time. No list of section bounds or displayed records.
    for c in top[1]:
        record=_source_cell_cost(inp,c);k=min(limit,_ranged_cells(inp,c.input_dims))
        candidate=_checked_add(candidate,_checked_mul(k,record.json_bytes+1))
        objects=_checked_add(objects,_checked_mul(k,record.object_bytes));shown=_checked_add(shown,k)
        worst=max(worst,record.object_bytes)
        del record
        for i in range(c.stage_begin,c.stage_begin+c.stage_count):
            s=top[2][i];record=_trace_record_cost(inp,c,s);k=min(limit,_ranged_cells(inp,s.remaining_dims))
            candidate=_checked_add(candidate,_checked_mul(k,record.json_bytes+1))
            objects=_checked_add(objects,_checked_mul(k,record.object_bytes));shown=_checked_add(shown,k)
            worst=max(worst,record.object_bytes)
            del record
    key=_key_bound(inp.recipe.row_dims,inp.coordinates)
    key_charge=max(_sum_counts((key.json_bytes,key.object_bytes,1)),QUERY_ENVELOPE_BYTES)
    maxj=_trace_max_scalar(inp,top)
    total=_sum_counts((sobjects,objects,512,_checked_mul(128,shown),_checked_mul(8,shown),
                       worst,_checked_mul(5,maxj),256,32768,key_charge))
    del skeleton,key  # no active section/JP aggregate survives trace handoff
    # Approved ten-int return, retained/charged through transport/finalization.
    return (sbytes,sobjects,candidate,min(r.EXPLANATION_BYTES_LIMIT,candidate),total,
            shown,objects,worst,maxj,key_charge)


def _array_descriptor_cost(variable):
    f=_Fold();f.add(_literal_cost(variable.name),'name');f.add(_literal_cost(variable.dtype),'dtype')
    f.add(_shape_cost(variable.dims),'shape');f.add(NUMBER,'nbytes');f.add(DIGEST,'sha256');f.add(NUMBER,'offset')
    return f.finish()


def _api_projection(inp,top,plan0,kind):
    if type(kind) is not str or kind not in ('descriptor','prepared','materialized','plan'):
        raise Refusal('invalid_worker_response')
    if kind=='descriptor':model=_inspection_cost(inp.source)
    elif kind in ('prepared','materialized'):
        prepared=_Fold();prepared.add(_inspection_cost(inp.source),'inspection')
        prepared.add(_coordinates_cost(inp.coordinates),'coordinates');model=prepared.finish()
    else:model=_JP(_sum_counts((plan0.json_bytes,ESTIMATE_COST.json_bytes,1)),
                   _sum_counts((plan0.object_bytes,ESTIMATE_COST.object_bytes,512)))
    shell=_api_shell(kind);arrays=_Fold()
    if kind=='materialized':
        for variable in top[0]:arrays.add(_array_descriptor_cost(variable))
    ap=arrays.finish()
    # J excludes LF, as every other cost pair; arrays shell replaced once.
    return _JP(_sum_counts((shell.json_bytes,model.json_bytes,ap.json_bytes-2)),
               _sum_counts((shell.object_bytes,model.object_bytes,ap.object_bytes-512)))


def _project_native_control(top,manifest_bytes):
    # Only three scalar path totals and one current path/pair. In particular,
    # do not reuse _payload_paths' list/tuple transition or retain a witness
    # forest. Native projection runs after output/path and trace frame release.
    children=path_j=path_p=0
    for name in ROOT_PAYLOADS:
        pair=_literal_cost(name)
        children=_checked_add(children,1,limit=136)
        path_j=_checked_add(path_j,pair.json_bytes);path_p=_checked_add(path_p,pair.object_bytes)
        del pair
    del name
    pair=_literal_cost('manifest.json');children=_checked_add(children,1,limit=136)
    path_j=_checked_add(path_j,pair.json_bytes);path_p=_checked_add(path_p,pair.object_bytes)
    del pair
    for ci,c in enumerate(top[1]):
        for si in range(c.stage_count):
            for schema in (False,True):
                name=_stage_path(ci,si,schema);pair=_literal_cost(name)
                children=_checked_add(children,1,limit=136)
                path_j=_checked_add(path_j,pair.json_bytes);path_p=_checked_add(path_p,pair.object_bytes)
                del name,pair
    if top[2]:
        pair=_literal_cost('support');children=_checked_add(children,1,limit=136)
        path_j=_checked_add(path_j,pair.json_bytes);path_p=_checked_add(path_p,pair.object_bytes)
        del pair
    return (_native._parent_bytes(children,path_p),
            _native._control_ceiling(children,path_j,path_p,manifest_bytes))


def _project_transport(inp,top,plan0,trace,*,manifest_bytes):
    maximum=0
    for kind in ('descriptor','prepared','materialized','plan'):
        pair=_api_projection(inp,top,plan0,kind)
        maximum=max(maximum,_native._wire_bytes(pair.json_bytes+1,pair.object_bytes))
        del pair
    shell=_api_shell('explanation')
    maximum=max(maximum,_native._wire_bytes(_checked_add(trace[3],shell.json_bytes),
        _checked_add(trace[4],shell.object_bytes)))
    del shell
    parent_bytes,control_bytes=_project_native_control(top,manifest_bytes)
    return _native._transport_bytes(_selected_numeric(top),maximum,control_bytes,parent_bytes)


def _estimate_compilation(inp):
    if type(inp) is not _CompilationInput:raise Refusal('invalid_source')
    top=_derive_topology(inp);coordinate=_coordinate_totals(inp.coordinates)
    descriptor=_inspection_cost(inp.source);plan0=_project_plan0(inp,top)
    output=_project_outputs(inp,top,plan0)
    # No path ledger is retained across this phase boundary.
    trace=_project_trace(inp,top,limit=r.EXPLANATION_CELL_LIMIT)
    transport=_project_transport(inp,top,plan0,trace,manifest_bytes=output.manifest_json);a=_selected_numeric(top)
    fixed=r.CONTROL_STATE_BYTES+r.MODEL_FIXED_BYTES+3*r.SERIAL_BUFFER_BYTES
    scalar=max(r.SERIAL_BUFFER_BYTES,_checked_add(_checked_mul(5,output.max_scalar_j),256))
    common=_sum_counts((r.RUNTIME_ALLOWANCE,inp.binding['base_bytes'],2*a,
        3*coordinate.coordinate_p,2*descriptor.object_bytes,2*plan0.object_bytes,
        ESTIMATE_COST.object_bytes,_scratch(top),output.schema_objects,2*output.record_scratch,
        scalar,fixed,transport))
    build=_sum_counts((common,output.result_objects,3*output.result_json))
    verify=_sum_counts((common,3*output.result_objects,6*output.result_json))
    explain=_sum_counts((verify,trace[4],3*trace[3]));baseline=max(build,verify,explain)
    _check_cap('journey',baseline)
    # One exact final backing. No persistent estimate wrapper or counter copy.
    result=OwnedMap._from_checked((
        ('build_bytes',build),('bundle_bytes',output.bundle),('common_bytes',common),
        ('coordinate_canonical_bytes',max(coordinate.raw_coordinate_j,coordinate.selected_coordinate_j)),
        ('coordinate_label_utf8_bytes',coordinate.coordinate_utf8),('coordinate_objects_bytes',coordinate.coordinate_p),
        ('coordinate_raw_bytes',coordinate.coordinate_raw),('descriptor_objects_bytes',descriptor.object_bytes),
        ('estimated_memory_bytes',baseline),('explain_bytes',explain),('formula_version',2),
        ('manifest_json_bytes',output.manifest_json),('numerical_scratch_bytes',_scratch(top)),
        ('output_rows',_rows(inp)),('plan_json_bytes',output.plan_json),
        ('plan_objects_bytes',plan0.object_bytes+ESTIMATE_COST.object_bytes+512),
        ('recipe_json_bytes',output.recipe_json),('report_bytes',output.report),
        ('result_json_bytes',output.result_json),('result_objects_bytes',output.result_objects),
        ('schema_json_bytes',output.schema_json),('selected_numeric_bytes',a),
        ('source_base_bytes',inp.binding['base_bytes']),('stage_csv_bytes',output.stage_csv),
        ('support_records',_support(top)),('table_csv_bytes',output.table_csv),
        ('trace_bytes',trace[3]),('trace_objects_bytes',trace[4]),('transport_reserve_bytes',transport),
        ('verify_bytes',verify),('work_cell_visits',_work(inp,top))))
    return result


def _finish_emission(budgets,estimates,files,*,rows,support_records):
    """Check actual writer counters after B2 temporary state is released.

    The future writer derives fresh per-path budgets from its revalidated plan;
    it never retains this estimator's topology/input/trace across output work.
    Digests must be actual streamed hashes supplied by that writer. This scalar
    completion check does not read/write files or certify a commit.
    """
    from ._resource_inputs import _owned_map
    if type(budgets) is not tuple or len(budgets)>r.BUNDLE_PAYLOAD_LIMIT:raise Refusal('invalid_bundle')
    _fields(estimates,ESTIMATE_KEYS)
    for _,value in estimates._items:_count(value)
    if estimates['formula_version']!=2:raise Refusal('invalid_bundle')
    _owned_map(files,maximum=r.BUNDLE_FILE_LIMIT)
    if len(files)!=len(budgets)+1 or 'manifest.json' not in files:raise Refusal('invalid_bundle')
    _count(rows);_count(support_records)
    if rows!=estimates['output_rows'] or support_records!=estimates['support_records']:
        raise ComputationError('resource_estimate_mismatch')
    payload=0
    aggregate=_EmissionBudget('bundle','bundle',estimates['bundle_bytes'],r.BUNDLE_BYTES_LIMIT,0)
    for index,budget in enumerate(budgets):
        if type(budget) is not _EmissionBudget or budget.path=='manifest.json':raise Refusal('invalid_bundle')
        for previous in range(index):
            if budgets[previous].path==budget.path:raise Refusal('invalid_bundle')
        if budget.path not in files:raise Refusal('invalid_bundle')
        record=_fields(files[budget.path],('sha256','size_bytes'),'invalid_bundle')
        _digest_counter(record['sha256']);size=_check_emission(0,record['size_bytes'],budget)
        payload=_check_emission(payload,size,aggregate)
    manifest=_fields(files['manifest.json'],('sha256','size_bytes'),'invalid_bundle');_digest_counter(manifest['sha256'])
    manifest_bytes=_check_emission(0,manifest['size_bytes'],_EmissionBudget('manifest.json','metadata',estimates['manifest_json_bytes'],r.METADATA_BYTES_LIMIT,0))
    bundle=_check_emission(payload,manifest_bytes,aggregate)
    return OwnedMap._from_checked((('bundle_bytes',bundle),('files',files),('manifest_bytes',manifest_bytes),
        ('payload_bytes',payload),('rows',rows),('support_records',support_records)))


def _digest_counter(value):
    if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
        raise Refusal('invalid_bundle')
