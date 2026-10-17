"""Private Formula 2 scalar algebra; never allocates an output-sized forest.

Counts are bounded before arithmetic. J excludes document LF. No public API
accepts these private cost records as evidence of source or runtime admission.
"""
from dataclasses import dataclass
import math
from .errors import Refusal
from . import resources as r


def _count(value, code='invalid_source', *, limit=r.COUNT_MAX):
    if type(value) is not int or type(limit) is not int or not 0 <= limit <= r.COUNT_MAX:
        raise Refusal(code)
    if value < 0 or value > limit:
        raise Refusal(code)
    return value


def _checked_add(a, b, *, limit=r.COUNT_MAX, code='estimated_memory_limit'):
    _count(a, code); _count(b, code); _count(limit, code)
    if a > limit or b > limit-a:
        raise Refusal(code)
    return a+b


def _checked_mul(a, b, *, limit=r.COUNT_MAX, code='estimated_memory_limit'):
    _count(a, code); _count(b, code); _count(limit, code)
    if a and b > limit//a:
        raise Refusal(code)
    return a*b


def _sum_counts(values, *, limit=r.COUNT_MAX, code='estimated_memory_limit'):
    if type(values) is not tuple:
        raise Refusal(code)
    total=0
    for value in values:
        total=_checked_add(total,value,limit=limit,code=code)
    return total


def _shape_product(shape, *, code='invalid_source'):
    if type(shape) is not tuple or len(shape)>r.RANK_LIMIT:
        raise Refusal(code)
    product=1
    for length in shape:
        _count(length,code,limit=r.DIMENSION_LENGTH_LIMIT)
        if not length: raise Refusal(code)
        product=_checked_mul(product,length,limit=r.SHAPE_PRODUCT_LIMIT,code=code)
    return product


def _ceil_log2_ge2(length):
    _count(length,limit=r.DIMENSION_LENGTH_LIMIT)
    if not length: raise Refusal('invalid_source')
    return (max(2,length)-1).bit_length()


def _utf8(text, *, maximum=r.COUNT_MAX, code='invalid_source'):
    if type(text) is not str: raise Refusal(code)
    _count(maximum,code)
    n=0
    for char in text:
        c=ord(char)
        if 0xD800<=c<=0xDFFF: raise Refusal(code)
        n=_checked_add(n,1 if c<128 else 2 if c<2048 else 3 if c<65536 else 4,
                       limit=maximum,code=code)
    return n


@dataclass(frozen=True,slots=True)
class _JP:
    def __init_subclass__(cls,**kwargs):raise TypeError('Private resource records are final')
    json_bytes: int
    object_bytes: int
    def __post_init__(self):
        _count(self.json_bytes); _count(self.object_bytes)


@dataclass(frozen=True,slots=True)
class _FieldCost:
    def __init_subclass__(cls,**kwargs):raise TypeError('Private resource records are final')
    field_name: str
    pair: _JP
    def __post_init__(self):
        _utf8(self.field_name)
        if type(self.pair) is not _JP: raise Refusal('invalid_source')


@dataclass(frozen=True,slots=True)
class _RepeatBlock:
    def __init_subclass__(cls,**kwargs):raise TypeError('Private resource records are final')
    count: int
    element: _JP
    def __post_init__(self):
        _count(self.count)
        if type(self.element) is not _JP: raise Refusal('invalid_source')


def _literal_cost(value):
    kind=type(value)
    if value is None: return _JP(4,128)
    if kind is bool: return _JP(5,128)
    if kind is int:
        if not r.JSON_INTEGER_MIN<=value<=r.JSON_INTEGER_MAX: raise Refusal('invalid_source')
        return _JP(32,128)
    if kind is float:
        if not math.isfinite(value): raise Refusal('invalid_source')
        return _JP(32,128)
    if kind is str:
        n=_utf8(value)
        return _JP(_checked_add(_checked_mul(6,n),2),_checked_add(128,_checked_mul(4,n)))
    raise Refusal('invalid_source')


def _container_cost(count, j, p):
    _count(count); _count(j); _count(p)
    return _JP(_sum_counts((2,max(0,count-1),j)),
               _sum_counts((512,_checked_mul(128,count),p)))


def _list_cost(items):
    if type(items) is not tuple: raise Refusal('invalid_source')
    j=p=0
    for cost in items:
        if type(cost) is not _JP: raise Refusal('invalid_source')
        j=_checked_add(j,cost.json_bytes); p=_checked_add(p,cost.object_bytes)
    return _container_cost(len(items),j,p)


def _map_cost(fields):
    if type(fields) is not tuple: raise Refusal('invalid_source')
    j=p=0
    for i,field in enumerate(fields):
        if type(field) is not _FieldCost: raise Refusal('invalid_source')
        # Finite schema field tuples, never unbounded caller maps.
        j_previous=0
        while j_previous<i:
            if fields[j_previous].field_name==field.field_name:raise Refusal('invalid_source')
            j_previous+=1
        key=_literal_cost(field.field_name)
        j=_sum_counts((j,key.json_bytes,1,field.pair.json_bytes))
        p=_sum_counts((p,key.object_bytes,field.pair.object_bytes))
    return _container_cost(len(fields),j,p)


def _repeat_cost(count, element):
    _count(count)
    if type(element) is not _JP: raise Refusal('invalid_source')
    return _container_cost(count,_checked_mul(count,element.json_bytes),
                           _checked_mul(count,element.object_bytes))


def _concat_repeats_cost(blocks):
    if type(blocks) is not tuple: raise Refusal('invalid_source')
    count=j=p=0
    for block in blocks:
        if type(block) is not _RepeatBlock: raise Refusal('invalid_source')
        count=_checked_add(count,block.count)
        j=_checked_add(j,_checked_mul(block.count,block.element.json_bytes))
        p=_checked_add(p,_checked_mul(block.count,block.element.object_bytes))
    return _container_cost(count,j,p)


# One shallow fold frame; no retained per-member cost or copied model forest.
@dataclass(slots=True)
class _Fold:
    index: int = 0
    entries: int = 0
    j: int = 0
    p: int = 0
    phase: int = 0
    container: tuple | None = None
    field_name: str | None = None
    template: str | None = None
    def add(self, pair, name=None, count=1):
        if type(pair) is not _JP: raise Refusal('invalid_source')
        _count(count)
        if name is not None:
            if count!=1: raise Refusal('invalid_source')
            key=_literal_cost(name)
            self.j=_sum_counts((self.j,key.json_bytes,1))
            self.p=_checked_add(self.p,key.object_bytes)
        self.entries=_checked_add(self.entries,count)
        self.j=_checked_add(self.j,_checked_mul(count,pair.json_bytes))
        self.p=_checked_add(self.p,_checked_mul(count,pair.object_bytes))
    def finish(self):
        return _container_cost(self.entries,self.j,self.p)


NUMBER=_JP(32,128)
NULL=_JP(4,128)
BOOL=_JP(5,128)
EMPTY=_JP(2,512)
DIGEST=_JP(386,384)
ESTIMATE_KEYS=('formula_version','source_base_bytes','selected_numeric_bytes',
 'coordinate_raw_bytes','coordinate_canonical_bytes','coordinate_label_utf8_bytes',
 'coordinate_objects_bytes','descriptor_objects_bytes','plan_objects_bytes',
 'recipe_json_bytes','plan_json_bytes','result_json_bytes','result_objects_bytes',
 'table_csv_bytes','stage_csv_bytes','schema_json_bytes','report_bytes',
 'manifest_json_bytes','bundle_bytes','output_rows','support_records',
 'work_cell_visits','numerical_scratch_bytes','trace_objects_bytes','trace_bytes',
 'transport_reserve_bytes','common_bytes','build_bytes','verify_bytes','explain_bytes',
 'estimated_memory_bytes')
_f=_Fold()
for _name in ESTIMATE_KEYS: _f.add(NUMBER,_name)
ESTIMATE_COST=_f.finish()
del _f,_name
QUERY_ENVELOPE_BYTES=512+128*16+16*((128+4*128)+128+4*4096)+5*r.KEY_BYTES_LIMIT

_CAPS={
 'source_file':(r.SOURCE_FILE_BYTES_LIMIT,'source_bytes_limit'),
 'source_base':(r.SOURCE_MEMORY_BASE_LIMIT,'source_bytes_limit'),
 'selected':(r.SELECTED_NUMERIC_BYTES_LIMIT,'selected_numeric_bytes_limit'),
 'coordinate_raw':(r.COORDINATE_RAW_BYTES_LIMIT,'coordinate_bytes_limit'),
 'coordinate_canonical':(r.COORDINATE_CANONICAL_BYTES_LIMIT,'coordinate_bytes_limit'),
 'coordinate_utf8':(r.COORDINATE_LABEL_UTF8_BYTES_LIMIT,'coordinate_bytes_limit'),
 'label':(r.LABEL_UTF8_BYTES_LIMIT,'label_bytes_limit'),
 'rows':(r.OUTPUT_ROWS_LIMIT,'output_rows_limit'),
 'support':(r.SUPPORT_RECORDS_LIMIT,'support_records_limit'),
 'work':(r.WORK_CELL_LIMIT,'work_cell_limit'),
 'recipe':(r.RECIPE_BYTES_LIMIT,'recipe_bytes_limit'),
 'key':(r.KEY_BYTES_LIMIT,'key_bytes_limit'),
 'metadata':(r.METADATA_BYTES_LIMIT,'metadata_bytes_limit'),
 'runtime':(r.RUNTIME_JSON_BYTES_LIMIT,'runtime_identity_limit'),
 'report':(r.REPORT_BYTES_LIMIT,'report_bytes_limit'),
 'trace':(r.EXPLANATION_BYTES_LIMIT,'explanation_bytes_limit'),
 'bundle':(r.BUNDLE_BYTES_LIMIT,'bundle_bytes_limit'),
 'journey':(r.LOGICAL_JOURNEY_LIMIT,'estimated_memory_limit'),
}

def _check_cap(kind, value):
    if type(kind) is not str or kind not in _CAPS: raise Refusal('invalid_source')
    limit,code=_CAPS[kind]
    return _count(value,code,limit=limit)
