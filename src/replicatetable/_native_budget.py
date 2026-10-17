"""Private, scalar native-route worksheets; no IO, parser or admission authority.

These helpers express the reviewed v3/v4/corrected-verify equations. A future
owning boundary must obtain its own actual observations and preserve every
frame barrier. Supplying numbers here establishes no source, plan or worker
trust. Generic strict JSON decoding is unchanged.
"""
from . import resources as r
from .errors import Refusal
from ._resource_bounds import (NUMBER, NULL, BOOL, EMPTY, DIGEST, _JP, _Fold,
    _literal_cost, _repeat_cost, _container_cost, _count, _check_cap,
    _checked_add, _checked_mul, _sum_counts)
from ._resource_inputs import _check_source_base


def _text_cost(length):
    _count(length)
    return _JP(_checked_add(2,_checked_mul(6,length)),
               _checked_add(128,_checked_mul(4,length)))


def _fields_cost(names,value):
    # Only fixed module-owned field tuples use this import-time helper.
    f=_Fold()
    for name in names:f.add(value,name)
    return f.finish()


_FILE_WITNESS=_fields_cost(('device','inode','mode','nlink','size','mtime_ns','ctime_ns'),NUMBER)
_IDENTITY=_fields_cost(('device','inode','mode'),NUMBER)
_CHECKS=_fields_cost(('structure','source_binding','runtime_binding','replay','report'),_literal_cost('not_attempted'))


def _fixed_shapes():
    f=_Fold();f.add(NUMBER,'size_bytes');f.add(DIGEST,'sha256');digest=f.finish()
    f=_Fold();f.add(_text_cost(6),'kind');f.add(DIGEST,'sha256');f.add(NUMBER,'size_bytes');source=f.finish()
    f=_Fold();f.add(_text_cost(128),'code');f.add(_text_cost(512),'message');f.add(NUMBER,'exit_code');finding=f.finish()
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost('bundle'),'kind');f.add(source,'source')
    for name in ('recipe_sha256','plan_sha256','result_sha256','runtime_sha256','manifest_sha256'):f.add(DIGEST,name)
    f.add(NUMBER,'output_bytes');prepared=f.finish()
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost('committed'),'status');f.add(source,'source')
    for name in ('recipe_sha256','plan_sha256','result_sha256','runtime_sha256','manifest_sha256'):f.add(DIGEST,name)
    f.add(NUMBER,'bundle_bytes');f.add(BOOL,'interrupted_after_commit');receipt=f.finish()
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost('cancelled'),'status')
    f.add(_text_cost(128),'code');f.add(_text_cost(512),'message');f.add(_CHECKS,'checks')
    f.add(BOOL,'committed');f.add(receipt,'receipt');error=f.finish()
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost('api_write_bundle'),'operation')
    for name in ('input_fd','recipe_fd','plan_fd','bundle_fd','key_fd','stage_fd','control_fd',
                 'result_fd','payload_fd','limit','deadline_ns'):f.add(NUMBER,name)
    f.add(_text_cost(32),'witness_id');request=f.finish()
    f=_Fold();f.add(NUMBER,'version');f.add(source,'source')
    for name in ('recipe_bytes','plan_bytes','result_bytes','key_bytes'):f.add(NUMBER,name)
    for name in ('recipe_sha256','plan_sha256','result_sha256','key_sha256'):f.add(DIGEST,name)
    f.add(NUMBER,'limit');f.add(_literal_cost('bundle_receipt'),'return_kind');api=f.finish()
    f=_Fold();f.add(NUMBER,'version');f.add(digest,'recipe');f.add(digest,'plan')
    f.add(NULL,'result');f.add(digest,'key');cli=f.finish()
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost('cancelled'),'status');f.add(_CHECKS,'checks')
    f.add(source,'source')
    for name in ('plan_sha256','result_sha256','manifest_sha256'):f.add(DIGEST,name)
    f.add(finding,'finding');f.add(BOOL,'committed');verification=f.finish()
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost('verification'),'kind')
    f.add(verification,'model');f.add(EMPTY,'arrays');metadata=f.finish()
    return digest,source,finding,prepared,receipt,error,request,api,cli,verification,metadata


(_DIGEST_SIZE,_SOURCE,_FINDING,_PREPARED_RECEIPT,_BUNDLE_RECEIPT,
 _ERROR_ENVELOPE,_WORKER_REQUEST,_API_BINDINGS,_CLI_BINDINGS,
 _VERIFY_MODEL,_VERIFY_METADATA)=_fixed_shapes()
# Componentwise envelopes dominate exact nullable/operation/status alternatives.
# Worker errors also have an independently enforced whole-document 4096 cap.
_WORKER_ERROR=_JP(min(_ERROR_ENVELOPE.json_bytes,4095),_ERROR_ENVELOPE.object_bytes)


def _parent_fixed_bytes():
    f=_Fold();f.add(NUMBER,'fd');f.add(NUMBER,'parent_fd');f.add(_text_cost(4095),'name')
    f.add(_FILE_WITNESS,'fd_witness');f.add(_FILE_WITNESS,'entry_witness');f.add(_IDENTITY,'parent_identity')
    f.add(_SOURCE,'source');f.add(BOOL,'retired');source_owner=f.finish()
    f=_Fold();f.add(NUMBER,'fd');f.add(NUMBER,'parent_fd');f.add(_text_cost(4095),'name')
    f.add(_FILE_WITNESS,'fd_witness');f.add(_FILE_WITNESS,'entry_witness');f.add(_IDENTITY,'parent_identity')
    f.add(_DIGEST_SIZE,'digest');f.add(BOOL,'retired');input_owner=f.finish()
    f=_Fold();f.add(BOOL,'exists');f.add(NUMBER,'fd');f.add(NUMBER,'flags');f.add(_FILE_WITNESS,'witness');stream=f.finish()
    f=_Fold();f.add(_repeat_cost(2,NUMBER),'handlers');f.add(_repeat_cost(64,NUMBER),'main_mask')
    f.add(_repeat_cost(2,_JP(0,128+152)),'action_bytes');f.add(NUMBER,'latched');f.add(NUMBER,'token');signal=f.finish()
    f=_Fold();f.add(NUMBER,'fd');f.add(NUMBER,'parent_fd');f.add(_text_cost(32),'name')
    f.add(_IDENTITY,'created_identity');f.add(_FILE_WITNESS,'witness');f.add(BOOL,'retired');workfile=f.finish()
    f=_Fold();f.add(NUMBER,'fd');f.add(NUMBER,'parent_fd');f.add(_text_cost(4095),'name')
    f.add(_IDENTITY,'created_identity');f.add(_FILE_WITNESS,'sealed_witness');f.add(_text_cost(11),'kind')
    f.add(BOOL,'committed');f.add(BOOL,'retired');root=f.finish()
    f=_Fold();f.add(_repeat_cost(3,source_owner),'source_references');f.add(source_owner,'source_lease')
    f.add(_repeat_cost(4,input_owner),'inputs');f.add(_repeat_cost(4,workfile),'workspace_files')
    f.add(_repeat_cost(2,root),'root_owners');f.add(_repeat_cost(2,_FILE_WITNESS),'root_witnesses')
    f.add(_text_cost(4095),'destination_name');f.add(_text_cost(54),'workspace_name')
    f.add(EMPTY,'children_original');f.add(EMPTY,'children_transition')
    f.add(_PREPARED_RECEIPT,'prepared_receipt');f.add(_BUNDLE_RECEIPT,'committed_receipt')
    f.add(_ERROR_ENVELOPE,'error_envelope');f.add(_CHECKS,'checks');f.add(_FINDING,'finding')
    f.add(_WORKER_REQUEST,'request');f.add(_API_BINDINGS,'api_bindings');f.add(_CLI_BINDINGS,'cli_bindings')
    f.add(_repeat_cost(2,stream),'stream_originals');f.add(signal,'signal_originals')
    f.add(_repeat_cost(8,NUMBER),'scientific_reference_slots')
    f.add(_JP(0,965*24),'api_header_reservation')
    f.add(_repeat_cost(9,_JP(0,65536)),'caller_path_arguments')
    f.add(_JP(0,65536),'original_argv_state');f.add(_JP(0,65536),'path_normalization_scratch')
    f.add(_repeat_cost(9,_text_cost(4095)),'normalized_path_texts')
    return _checked_add(f.finish().object_bytes,160*512)


_PARENT_FIXED_BYTES=_parent_fixed_bytes()
_SOURCE_HEADER_BYTES=3*216+3*64*56+3*16*56+3*512+192*128
_COMMON_HEADER_BYTES=16379+3*216+2*64*56+3*16*56+4*6*512+4*(352+112)+128*128+4*128
_SCANNER_COUNTER_BYTES=12664
_CONTROL_PEAK_BYTES=1942940+_SCANNER_COUNTER_BYTES


def _child_shell(digest=False):
    f=_Fold();f.add(_JP(0,0),'path');f.add(_FILE_WITNESS,'witness')
    if digest:f.add(DIGEST,'sha256')
    return f.finish()


_CHILD_SHELL=_child_shell()
_LEDGER_CHILD_SHELL=_child_shell(True)


def _child_counts(children,path_objects):
    _count(children,limit=136)
    _count(path_objects,limit=_checked_mul(children,236))
    if path_objects<_checked_mul(children,128):raise Refusal('invalid_source')


def _parent_bytes(children,path_objects):
    """Two original/transition ledgers; only scalar path sums, no child list."""
    _child_counts(children,path_objects)
    extra=_checked_add(_checked_mul(children,128+_LEDGER_CHILD_SHELL.object_bytes),path_objects)
    return _checked_add(_PARENT_FIXED_BYTES,_checked_mul(2,extra))


def _stage_witness_cost(children,path_json,path_objects):
    _child_counts(children,path_objects)
    _count(path_json,limit=_checked_mul(children,164))
    if path_json<_checked_mul(children,2):raise Refusal('invalid_source')
    entries=_container_cost(children,
        _checked_add(_checked_mul(children,_CHILD_SHELL.json_bytes),path_json),
        _checked_add(_checked_mul(children,_CHILD_SHELL.object_bytes),path_objects))
    f=_Fold();f.add(_FILE_WITNESS,'directory');f.add(entries,'entries');return f.finish()


def _completion_cost(stage):
    if type(stage) is not _JP:raise Refusal('invalid_source')
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost('api_write_bundle'),'operation')
    f.add(_literal_cost('cancelled'),'status');f.add(_text_cost(32),'witness_id');f.add(_CHECKS,'checks')
    f.add(_FILE_WITNESS,'source_stat');f.add(stage,'stage');f.add(_DIGEST_SIZE,'payload')
    f.add(_PREPARED_RECEIPT,'receipt');f.add(_WORKER_ERROR,'error');return f.finish()


def _control_ceiling(children,path_json,path_objects,manifest_bytes):
    _check_cap('metadata',manifest_bytes)
    completion=_completion_cost(_stage_witness_cost(children,path_json,path_objects))
    return max(_WORKER_REQUEST.json_bytes+1,_API_BINDINGS.json_bytes+1,
        _CLI_BINDINGS.json_bytes+1,completion.json_bytes+1,4096,
        _ERROR_ENVELOPE.json_bytes+1,manifest_bytes)


def _decoder_bytes(raw_bytes,scan_objects):
    """Unchanged generic 5N+3Pscan; observations must precede any decode."""
    _count(raw_bytes);_count(scan_objects)
    return _checked_add(_checked_mul(5,raw_bytes),_checked_mul(3,scan_objects))


def _wire_bytes(projected_bytes,projected_objects):
    """Pscan <= Pmodel+4N: semantic projections need 17N+3Pmodel."""
    _count(projected_bytes);_count(projected_objects)
    return _checked_add(_checked_mul(17,projected_bytes),_checked_mul(3,projected_objects))


def _transport_bytes(selected_bytes,model_wire,control_bytes,parent_bytes):
    """control_bytes is the maximum whole raw JSON N, not its 965N cost."""
    _check_cap('selected',selected_bytes);_count(model_wire);_count(parent_bytes)
    _count(control_bytes,'metadata_bytes_limit',limit=r.PARENT_ENVELOPE_BYTES_LIMIT)
    return _checked_add(parent_bytes,max(_checked_add(selected_bytes,model_wire),_checked_mul(965,control_bytes)))


def _combined_guard(baseline,additional):
    return _checked_add(baseline,additional,limit=r.LOGICAL_JOURNEY_LIMIT)


def _standalone_control_bytes():
    """Return the complete 965N0 reserve, with every finite control shape."""
    # Initial inspect/prepare/compile and source-only verify have no proposed
    # staged receipt. Full parent error is larger than this completion.
    return _checked_mul(965,max(_WORKER_REQUEST.json_bytes+1,_API_BINDINGS.json_bytes+1,
        _CLI_BINDINGS.json_bytes+1,_standalone_completion_cost().json_bytes+1,
        4096,_ERROR_ENVELOPE.json_bytes+1))


def _standalone_completion_cost():
    f=_Fold();f.add(NUMBER,'version');f.add(_literal_cost('api_prepare'),'operation')
    f.add(_literal_cost('cancelled'),'status');f.add(_text_cost(32),'witness_id');f.add(_CHECKS,'checks')
    f.add(_FILE_WITNESS,'source_stat');f.add(NULL,'stage');f.add(_DIGEST_SIZE,'payload')
    f.add(NULL,'receipt');f.add(_WORKER_ERROR,'error');return f.finish()


def _route_base(source_base,selected_bytes,coordinate_objects,*,source_kind='file',verify=False):
    """K(W): both source-base and common MODEL_FIXED are paid separately."""
    _check_source_base(source_kind,source_base);_check_cap('selected',selected_bytes)
    _count(coordinate_objects,limit=r.LOGICAL_JOURNEY_LIMIT)
    if type(verify) is not bool:raise Refusal('invalid_source')
    # Exact maximum generated-path sum: six root payloads + manifest + support
    # plus 64 CSV/schema pairs. This is a scalar frozen topology, no path list.
    w=_parent_bytes(136,1352+64*((128+4*19)+(128+4*27))) if verify else _PARENT_FIXED_BYTES
    return _combined_guard(0,_sum_counts((r.RUNTIME_ALLOWANCE,source_base,
        _checked_mul(2,selected_bytes),coordinate_objects,r.CONTROL_STATE_BYTES,
        3*r.SERIAL_BUFFER_BYTES,r.MODEL_FIXED_BYTES,w)))


def _standalone_guard(source_base,metadata_bytes,scan_objects,selected_bytes,*,
        source_kind='file',held_coordinates=0,recipe_objects=0):
    _check_cap('metadata',metadata_bytes);_count(scan_objects)
    _count(recipe_objects,limit=r.LOGICAL_JOURNEY_LIMIT)
    base=_route_base(source_base,selected_bytes,held_coordinates,source_kind=source_kind)
    phase=max(_standalone_control_bytes(),_decoder_bytes(metadata_bytes,scan_objects))
    return _combined_guard(base,_checked_add(recipe_objects,phase))


def _saved_plan_parse_guard(base,raw_bytes,scan_objects,*,recipe_objects=0):
    _check_cap('journey',base);_check_cap('metadata',raw_bytes);_count(scan_objects)
    _count(recipe_objects,limit=r.LOGICAL_JOURNEY_LIMIT)
    return _combined_guard(base,_sum_counts((raw_bytes,_decoder_bytes(raw_bytes,scan_objects),recipe_objects)))


def _load_plan_guard(base,raw_bytes,saved_objects,recipe_objects,metadata_bytes,scan_objects):
    _check_cap('journey',base);_check_cap('metadata',raw_bytes);_check_cap('metadata',metadata_bytes)
    _count(scan_objects)
    _count(saved_objects,limit=r.LOGICAL_JOURNEY_LIMIT);_count(recipe_objects,limit=r.LOGICAL_JOURNEY_LIMIT)
    phase=max(_standalone_control_bytes(),_decoder_bytes(metadata_bytes,scan_objects))
    return _combined_guard(base,_sum_counts((raw_bytes,saved_objects,recipe_objects,phase)))


def _canonical_route_guard(complete_call_total,*,raw_bytes=0,saved_objects=0,recipe_objects=0):
    _check_cap('journey',complete_call_total);_check_cap('metadata',raw_bytes)
    _count(saved_objects,limit=r.LOGICAL_JOURNEY_LIMIT);_count(recipe_objects,limit=r.LOGICAL_JOURNEY_LIMIT)
    return _combined_guard(complete_call_total,_sum_counts((raw_bytes,saved_objects,recipe_objects)))


def _verify_summary_objects():
    f=_Fold();f.add(_SOURCE,'source');f.add(_repeat_cost(64,_text_cost(128)),'variables')
    f.add(_repeat_cost(16,_text_cost(128)),'dimensions');f.add(_repeat_cost(16,_text_cost(128)),'row_dims')
    f.add(DIGEST,'plan_sha256');return f.finish().object_bytes


def _verify_route_guard(base,plan_bytes,plan_scan_objects,recipe_objects,report_bytes,report_scan_objects):
    _check_cap('journey',base);_check_cap('metadata',plan_bytes)
    _count(report_bytes,'metadata_bytes_limit',limit=_VERIFY_METADATA.json_bytes+1)
    _count(plan_scan_objects);_count(report_scan_objects)
    _count(recipe_objects,limit=r.LOGICAL_JOURNEY_LIMIT)
    plan_phase=_sum_counts((_decoder_bytes(plan_bytes,plan_scan_objects),recipe_objects,
                           _checked_mul(2,_verify_summary_objects())))
    return _combined_guard(base,max(plan_phase,_standalone_control_bytes(),
        _decoder_bytes(report_bytes,report_scan_objects)))
