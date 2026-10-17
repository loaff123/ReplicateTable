"""Explicitly SYNTHETIC bounded metadata and owner observations for B2.

No fixture is an xarray/NetCDF source or actual source-admission evidence.
"""
from replicatetable.codec import OwnedMap, freeze
from replicatetable.model import Recipe, Coordinate, MetadataValue
from tests.unit.test_runtime_binding import example as runtime_example


def descriptor(dims=(),shape=(),dtype='float64',unit=None,attributes=None,encoding=None,status=None):
    return {'dims':list(dims),'shape':list(shape),'dtype':dtype,'unit':unit,
            'attributes':MetadataValue({} if attributes is None else attributes)._tagged,
            'encoding':MetadataValue({} if encoding is None else encoding)._tagged,
            'selection_status':status}


def inspection(dimensions=None,variables=None,coordinates=None,kind='memory'):
    dimensions={} if dimensions is None else dimensions
    variables={'v':descriptor()} if variables is None else variables
    coordinates={} if coordinates is None else coordinates
    # Freeze accepts already-owned children and preserves their identities.
    return freeze({'version':2,'source':{'kind':kind,'sha256':'a'*64,'size_bytes':999},
        'dimensions':dimensions,'variables':variables,'coordinate_descriptors':coordinates,
        'attributes':MetadataValue({})._tagged})


def operation(source=None,target=None,weight=False):
    return freeze({'source_unit':source,'target_unit':target,'scale':1.0,'offset':0.0,
        'parsed_source':None,'parsed_target':[] if weight else None,'definition_graph':[]})


def recipe(row_dims=(),columns=None):
    if columns is None:
        columns=[{'name':'out','source':'v','source_unit':None,'target_unit':None,
                  'broadcast':[],'stages':[]}]
    return Recipe(1,list(row_dims),columns)


def stage(name,dims,weighted=False):
    s={'name':name,'dims':list(dims),'op':'weighted_mean' if weighted else 'mean',
       'missing':'skip','min_count':1}
    if weighted: s.update(weights='w',weight_unit=None)
    return s


def synthetic_input(dimensions=None,variables=None,coords=None,rec=None,kind='memory'):
    from replicatetable import _resource_inputs as m
    dimensions={} if dimensions is None else dimensions
    coords={} if coords is None else coords
    descs={n:descriptor((n,),(len(c.values),),c.dtype) for n,c in coords.items()}
    src=inspection(dimensions,variables,descs,kind)
    rec=recipe() if rec is None else rec
    cf=[]
    for name,coord in sorted(coords.items()):
        # Explicit synthetic numeric source route; Unicode/fixed-byte tests
        # supply their own raw prepass facts to the dedicated adapter.
        cf.append(m._coordinate_facts(name,coord,raw_bytes=len(coord.values)*8,
                  preselection_j=m._owned_cost(coord.values).json_bytes))
    if kind=='file': binding=m._file_binding(src,4096)
    else: binding=m._memory_binding(src,(),512)
    units=tuple((operation(c['source_unit'],c['target_unit']),
                 operation(weight=True) if c['stages'] and c['stages'][0]['op']=='weighted_mean' else None)
                for c in rec.columns)
    return m._CompilationInput(src,binding,rec,tuple(cf),freeze(runtime_example()),units)
