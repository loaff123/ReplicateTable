"""Source-bound eager-memory tables and experimental bundle transactions."""
from .model import ArrayBuffer, BoundPlan, ComputationError, Coordinate, Recipe, Refusal, SourceIdentity, SourceSnapshot, parse_recipe

from .source import snapshot_dataset, prepare_source, materialize_source
from .plan import compile_plan, load_plan
from .admission import CallAdmission, inspect_call_admission
from .reduce import execute, load_result, RowRecord, SupportRecord, ComputationResult

__version__ = '0.1.0a1'
__all__ = ['snapshot_dataset', 'prepare_source', 'compile_plan', 'load_plan', 'materialize_source', 'execute', 'load_result', 'RowRecord', 'SupportRecord', 'ComputationResult', 'inspect_call_admission', 'CallAdmission', 'BoundPlan', 'parse_recipe', 'Recipe', 'SourceIdentity', 'SourceSnapshot', 'Coordinate', 'ArrayBuffer', 'Refusal', 'ComputationError']

from .bundle import write_bundle, verify_bundle
from .report import render_report
from .explain import explain_row, RowExplanation
from ._bundle_models import BundleReceipt, BundleVerification

__all__ += ["write_bundle", "verify_bundle", "render_report", "explain_row",
            "RowExplanation", "BundleReceipt", "BundleVerification"]
