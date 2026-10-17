"""Closed control schemas independently instantiated in tests only."""
import unittest
from replicatetable import _resource_estimates as e
from replicatetable.codec import primitive_bounds
from replicatetable.errors import Refusal
from tests.resource_helpers import synthetic_input
from tests.unit.test_resource_estimates import hand_input
from tests.unit.test_resource_coverage import maximum_input
from tests.unit.test_native_budget_estimates import budget

DIGEST='a'*64
FW={k:0 for k in ('device','inode','mode','nlink','size','mtime_ns','ctime_ns')}
SOURCE={'kind':'memory','sha256':DIGEST,'size_bytes':0}
CHECKS={k:'not_attempted' for k in ('structure','source_binding','runtime_binding','replay','report')}
FINDING={'code':'c'*128,'message':'m'*512,'exit_code':3}
PREP={'version':2,'kind':'bundle','source':SOURCE,'recipe_sha256':DIGEST,'plan_sha256':DIGEST,
      'result_sha256':DIGEST,'runtime_sha256':DIGEST,'manifest_sha256':DIGEST,'output_bytes':0}
RECEIPT={'version':2,'status':'committed','source':SOURCE,'recipe_sha256':DIGEST,'plan_sha256':DIGEST,
         'result_sha256':DIGEST,'runtime_sha256':DIGEST,'manifest_sha256':DIGEST,'bundle_bytes':0,'interrupted_after_commit':False}
PLAN_RECEIPT={'version':2,'status':'committed','plan_sha256':DIGEST,'plan_bytes':0,'interrupted_after_commit':False}
ERROR={'version':2,'status':'cancelled','code':'c'*128,'message':'m'*512,'checks':CHECKS,'committed':False,'receipt':RECEIPT}
OPERATIONS={
    'inspect':(), 'plan':('recipe_fd','stage_fd'), 'build':('plan_fd','stage_fd'),
    'explain-row':('bundle_fd','key_fd','limit'), 'verify':('bundle_fd',),
    'api_inspect':(), 'api_prepare':('recipe_fd',), 'api_compile':('recipe_fd',),
    'api_materialize':('plan_fd',), 'api_execute':('plan_fd',),
    'api_write_bundle':('plan_fd','result_fd','stage_fd'), 'api_verify':('bundle_fd',),
    'api_explain':('plan_fd','result_fd','key_fd','limit')}
RETURNS={'api_inspect':'descriptor','api_prepare':'prepared','api_compile':'plan',
         'api_materialize':'materialized','api_execute':'result',
         'api_write_bundle':'bundle_receipt','api_verify':'verification','api_explain':'explanation'}

def children(top):
    # Test-only expected ledger, independent of new product scalar fold.
    result=list(e.ROOT_PAYLOADS)+['manifest.json']
    for ci,c in enumerate(top[1]):
        for si in range(c.stage_count):
            result.extend((f'support/c{ci:02d}-s{si:02d}.csv',f'support/c{ci:02d}-s{si:02d}.schema.json'))
    if top[2]:result.append('support')
    return result

def path_sums(paths):
    return sum(6*len(p.encode())+2 for p in paths),sum(128+4*len(p.encode()) for p in paths)


class NativeBudgetControlTests(unittest.TestCase):
    def pair(self,actual,expected):
        self.assertEqual((actual.json_bytes,actual.object_bytes),expected)

    def dominated(self,value,bound):
        actual=primitive_bounds(value)
        self.assertLessEqual(actual.json_bytes,bound.json_bytes)
        self.assertLessEqual(actual.object_bytes,bound.object_bytes)

    def test_frozen_control_pairs_have_exact_independent_values(self):
        m=budget()
        for name,expected in (
            ('_FILE_WITNESS',(493,3360)),('_SOURCE',(589,2024)),
            ('_PREPARED_RECEIPT',(3228,7548)),('_BUNDLE_RECEIPT',(3411,8048)),
            ('_ERROR_ENVELOPE',(8374,16664)),('_WORKER_REQUEST',(1441,6552)),
            ('_API_BINDINGS',(3174,8572)),('_CLI_BINDINGS',(1782,6952)),
            ('_VERIFY_MODEL',(7087,13928)),('_VERIFY_METADATA',(7344,16368))):
            with self.subTest(name=name):self.pair(getattr(m,name),expected)
        for value,name in ((FW,'_FILE_WITNESS'),(SOURCE,'_SOURCE'),(PREP,'_PREPARED_RECEIPT'),
                           (RECEIPT,'_BUNDLE_RECEIPT'),(ERROR,'_ERROR_ENVELOPE')):
            actual=primitive_bounds(value);self.pair(getattr(m,name),(actual.json_bytes,actual.object_bytes))
        self.assertEqual(m._WORKER_ERROR.json_bytes,4095)
        self.assertEqual(m._WORKER_ERROR.object_bytes,16664)

    def test_all_13_requests_and_all_api_cli_binding_shapes(self):
        m=budget()
        for op,required in OPERATIONS.items():
            request={'version':2,'operation':op,'input_fd':0,'payload_fd':0,'control_fd':0,
                     'deadline_ns':0,'witness_id':'a'*32}
            for field in ('recipe_fd','plan_fd','bundle_fd','key_fd','stage_fd','result_fd','limit'):
                request[field]=0 if field in required else None
            self.dominated(request,m._WORKER_REQUEST)
            if op in RETURNS:
                binding={'version':2,'source':None if op=='api_inspect' else SOURCE,
                         'limit':0 if 'limit' in required else None,'return_kind':RETURNS[op]}
                for kind in ('recipe','plan','result','key'):
                    binding[kind+'_bytes']=0
                    binding[kind+'_sha256']=DIGEST if kind+'_fd' in required else None
                self.dominated(binding,m._API_BINDINGS)
            else:
                binding={'version':2,'result':None}
                for kind in ('recipe','plan','key'):
                    binding[kind]={'size_bytes':0,'sha256':DIGEST} if kind+'_fd' in required else None
                self.dominated(binding,m._CLI_BINDINGS)

    def test_error_receipt_status_checks_and_verification_alternatives(self):
        m=budget()
        for status in ('refused','failed','cancelled'):
            for receipt in (None,PLAN_RECEIPT,RECEIPT):
                for check in ('not_attempted','passed','failed'):
                    value=ERROR|{'status':status,'receipt':receipt,'checks':dict.fromkeys(CHECKS,check)}
                    self.dominated(value,m._ERROR_ENVELOPE)
        plan=PREP|{'kind':'plan','result_sha256':None,'manifest_sha256':None}
        self.dominated(plan,m._PREPARED_RECEIPT)
        for status in ('verified','refused','failed','cancelled'):
            for present in (False,True):
                value={'version':2,'status':status,'checks':CHECKS,'source':SOURCE if present else None,
                       'plan_sha256':DIGEST if present else None,'result_sha256':DIGEST if present else None,
                       'manifest_sha256':DIGEST if present else None,'finding':FINDING if present else None,'committed':False}
                self.dominated(value,m._VERIFY_MODEL)
                self.dominated({'version':2,'kind':'verification','model':value,'arrays':[]},m._VERIFY_METADATA)

    def test_exact_stage_shapes_and_136_children_plus_one(self):
        m=budget()
        for factory,n,w,completion,control in (
            (synthetic_input,7,1510004,14966,34810),
            (hand_input,12,1564276,18415,37470),
            (maximum_input,136,2913396,106331,119930)):
            inp=factory();top=e._derive_topology(inp);paths=children(top);pj,pp=path_sums(paths)
            self.assertEqual(len(paths),n)
            stage={'directory':FW,'entries':[{'path':p,'witness':FW} for p in paths]}
            q=primitive_bounds(stage);projected=m._stage_witness_cost(n,pj,pp)
            self.pair(projected,(q.json_bytes,q.object_bytes))
            self.assertEqual(m._parent_bytes(n,pp),w)
            self.assertEqual(m._completion_cost(projected).json_bytes+1,completion)
            plan=e._project_plan0(inp,top);manifest=e._project_outputs(inp,top,plan).manifest_json
            self.assertEqual(m._control_ceiling(n,pj,pp,manifest),control)
            self.assertEqual(e._project_native_control(top,manifest),(w,control))
        self.assertEqual(m._parent_bytes(0,0),1434532)
        with self.assertRaises(Refusal):m._parent_bytes(137,137*236)
        with self.assertRaises(Refusal):m._stage_witness_cost(137,137*164,137*236)
        with self.assertRaises(Refusal):m._control_ceiling(136,136*164,136*236,16777217)
        for value in (True,1.0,-1,'136'):
            with self.assertRaises(Refusal):m._parent_bytes(value,0)

    def test_completion_alternatives_and_plan_only_stage(self):
        m=budget();pj,pp=path_sums(['plan.json']);stage=m._stage_witness_cost(1,pj,pp)
        bound=m._completion_cost(stage)
        # Non-ready fields are nullable, including semantic api_verify reports.
        # Finite components are checked individually; max envelope can combine
        # non-coincident alternatives without claiming that combination valid.
        for op in OPERATIONS:
            for status in ('ready','refused','failed','cancelled'):
                for present in (False,True):
                    value={'version':2,'operation':op,'status':status,'witness_id':'a'*32,
                           'checks':CHECKS,'source_stat':FW if present else None,
                           'stage':{'directory':FW,'entries':[{'path':'plan.json','witness':FW}]} if present else None,
                           'payload':{'size_bytes':0,'sha256':DIGEST} if present else None,
                           'receipt':PREP if present else None,'error':None}
                    self.dominated(value,bound)
        self.assertEqual(m._standalone_control_bytes(),8081875)

    def test_standalone_completion_is_explicitly_in_control_maximum(self):
        m=budget()
        value={'version':2,'operation':'api_prepare','status':'cancelled','witness_id':'a'*32,
               'checks':CHECKS,'source_stat':FW,'stage':None,
               'payload':{'size_bytes':0,'sha256':DIGEST},'receipt':None,'error':ERROR}
        whole=primitive_bounds(value);error=primitive_bounds(ERROR)
        pair=m._standalone_completion_cost()
        self.pair(pair,(whole.json_bytes-error.json_bytes+4095,whole.object_bytes))
        self.assertLessEqual(pair.json_bytes+1,8375)
        self.assertEqual(m._standalone_control_bytes(),965*max(1442,3175,1783,4096,8375,pair.json_bytes+1))
