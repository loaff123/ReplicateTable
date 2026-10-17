"""NEW v11 expectations after workspace loss; synthetic metadata only.

This test is newly assembled from the recovered visible test template and a
fresh v11 derivation. It is not byte-exact recovery of the lost sealed test.
Expected old values and unchanged projections use the hash-pinned old B2
baseline; new transport/control/route arithmetic is independent of candidate
product helpers. No actual source/runtime/native capacity is established.
New derivation SHA256: c303a12e17d45a129dd8c93683e457bc53b9431af75a2c7407c48c5659f30d62
New expectation JSON SHA256: 0bc58765eb8121b806a13b71e4c86bcd6ee3c9049577d5052e1593f4b62d6cf1
"""
import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from replicatetable import _resource_estimates as e, _resource_inputs as i
from replicatetable.codec import freeze, primitive_bounds, canonical_bytes, json_prepass
from replicatetable.model import Coordinate, Recipe
from replicatetable.errors import Refusal
from tests.resource_helpers import synthetic_input, descriptor, inspection, operation, runtime_example, recipe, stage
from tests.unit.test_resource_estimates import hand_input
from tests.unit.test_resource_coverage import maximum_input
from tests.frozen_tools import adapt_legacy_recipe

# Literal new expectation values frozen before candidate validation.
EXPECTED = json.loads(r'''{
  "F1.json": {
    "new": {
      "build_bytes": 175604954,
      "bundle_bytes": 260372,
      "common_bytes": 175390962,
      "coordinate_canonical_bytes": 1218,
      "coordinate_label_utf8_bytes": 10,
      "coordinate_objects_bytes": 16464,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 85524,
      "estimated_memory_bytes": 181793099,
      "explain_bytes": 181793099,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 4352,
      "output_rows": 4,
      "plan_json_bytes": 45395,
      "plan_objects_bytes": 239352,
      "recipe_json_bytes": 2303,
      "report_bytes": 122255,
      "result_json_bytes": 22344,
      "result_objects_bytes": 146960,
      "schema_json_bytes": 14084,
      "selected_numeric_bytes": 224,
      "source_base_bytes": 151572,
      "stage_csv_bytes": 9453,
      "support_records": 12,
      "table_csv_bytes": 7068,
      "trace_bytes": 26687,
      "trace_objects_bytes": 5747132,
      "transport_reserve_bytes": 37722826,
      "verify_bytes": 175965906,
      "work_cell_visits": 757
    },
    "old": {
      "build_bytes": 155265746,
      "bundle_bytes": 260372,
      "common_bytes": 155051754,
      "coordinate_canonical_bytes": 1218,
      "coordinate_label_utf8_bytes": 10,
      "coordinate_objects_bytes": 16464,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 85524,
      "estimated_memory_bytes": 161453891,
      "explain_bytes": 161453891,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 4352,
      "output_rows": 4,
      "plan_json_bytes": 45395,
      "plan_objects_bytes": 239352,
      "recipe_json_bytes": 2303,
      "report_bytes": 122255,
      "result_json_bytes": 22344,
      "result_objects_bytes": 146960,
      "schema_json_bytes": 14084,
      "selected_numeric_bytes": 224,
      "source_base_bytes": 151572,
      "stage_csv_bytes": 9453,
      "support_records": 12,
      "table_csv_bytes": 7068,
      "trace_bytes": 26687,
      "trace_objects_bytes": 5747132,
      "transport_reserve_bytes": 17383618,
      "verify_bytes": 155626698,
      "work_cell_visits": 757
    }
  },
  "F2.json": {
    "new": {
      "build_bytes": 176971362,
      "bundle_bytes": 272013,
      "common_bytes": 176723428,
      "coordinate_canonical_bytes": 1218,
      "coordinate_label_utf8_bytes": 10,
      "coordinate_objects_bytes": 16464,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 85524,
      "estimated_memory_bytes": 183265345,
      "explain_bytes": 183265345,
      "formula_version": 2,
      "manifest_json_bytes": 38800,
      "numerical_scratch_bytes": 4352,
      "output_rows": 4,
      "plan_json_bytes": 45542,
      "plan_objects_bytes": 239896,
      "recipe_json_bytes": 2263,
      "report_bytes": 124245,
      "result_json_bytes": 25990,
      "result_objects_bytes": 169964,
      "schema_json_bytes": 17789,
      "selected_numeric_bytes": 192,
      "source_base_bytes": 151572,
      "stage_csv_bytes": 12646,
      "support_records": 16,
      "table_csv_bytes": 4738,
      "trace_bytes": 31239,
      "trace_objects_bytes": 5782368,
      "transport_reserve_bytes": 39028036,
      "verify_bytes": 177389260,
      "work_cell_visits": 1173
    },
    "old": {
      "build_bytes": 155455380,
      "bundle_bytes": 272013,
      "common_bytes": 155207446,
      "coordinate_canonical_bytes": 1218,
      "coordinate_label_utf8_bytes": 10,
      "coordinate_objects_bytes": 16464,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 85524,
      "estimated_memory_bytes": 161749363,
      "explain_bytes": 161749363,
      "formula_version": 2,
      "manifest_json_bytes": 38800,
      "numerical_scratch_bytes": 4352,
      "output_rows": 4,
      "plan_json_bytes": 45542,
      "plan_objects_bytes": 239896,
      "recipe_json_bytes": 2263,
      "report_bytes": 124245,
      "result_json_bytes": 25990,
      "result_objects_bytes": 169964,
      "schema_json_bytes": 17789,
      "selected_numeric_bytes": 192,
      "source_base_bytes": 151572,
      "stage_csv_bytes": 12646,
      "support_records": 16,
      "table_csv_bytes": 4738,
      "trace_bytes": 31239,
      "trace_objects_bytes": 5782368,
      "transport_reserve_bytes": 17512054,
      "verify_bytes": 155873278,
      "work_cell_visits": 1173
    }
  },
  "F3.json": {
    "new": {
      "build_bytes": 177032122,
      "bundle_bytes": 274922,
      "common_bytes": 176784188,
      "coordinate_canonical_bytes": 1218,
      "coordinate_label_utf8_bytes": 10,
      "coordinate_objects_bytes": 16464,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 93716,
      "estimated_memory_bytes": 183338807,
      "explain_bytes": 183338807,
      "formula_version": 2,
      "manifest_json_bytes": 38800,
      "numerical_scratch_bytes": 4400,
      "output_rows": 4,
      "plan_json_bytes": 48015,
      "plan_objects_bytes": 257940,
      "recipe_json_bytes": 2699,
      "report_bytes": 124245,
      "result_json_bytes": 25990,
      "result_objects_bytes": 169964,
      "schema_json_bytes": 17789,
      "selected_numeric_bytes": 216,
      "source_base_bytes": 159764,
      "stage_csv_bytes": 12646,
      "support_records": 16,
      "table_csv_bytes": 4738,
      "trace_bytes": 32777,
      "trace_objects_bytes": 5790456,
      "transport_reserve_bytes": 39028036,
      "verify_bytes": 177450020,
      "work_cell_visits": 1191
    },
    "old": {
      "build_bytes": 155548118,
      "bundle_bytes": 274922,
      "common_bytes": 155300184,
      "coordinate_canonical_bytes": 1218,
      "coordinate_label_utf8_bytes": 10,
      "coordinate_objects_bytes": 16464,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 93716,
      "estimated_memory_bytes": 161854803,
      "explain_bytes": 161854803,
      "formula_version": 2,
      "manifest_json_bytes": 38800,
      "numerical_scratch_bytes": 4400,
      "output_rows": 4,
      "plan_json_bytes": 48015,
      "plan_objects_bytes": 257940,
      "recipe_json_bytes": 2699,
      "report_bytes": 124245,
      "result_json_bytes": 25990,
      "result_objects_bytes": 169964,
      "schema_json_bytes": 17789,
      "selected_numeric_bytes": 216,
      "source_base_bytes": 159764,
      "stage_csv_bytes": 12646,
      "support_records": 16,
      "table_csv_bytes": 4738,
      "trace_bytes": 32777,
      "trace_objects_bytes": 5790456,
      "transport_reserve_bytes": 17544032,
      "verify_bytes": 155966016,
      "work_cell_visits": 1191
    }
  },
  "F3_scaled.json": {
    "new": {
      "build_bytes": 177032122,
      "bundle_bytes": 274922,
      "common_bytes": 176784188,
      "coordinate_canonical_bytes": 1218,
      "coordinate_label_utf8_bytes": 10,
      "coordinate_objects_bytes": 16464,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 93716,
      "estimated_memory_bytes": 183338807,
      "explain_bytes": 183338807,
      "formula_version": 2,
      "manifest_json_bytes": 38800,
      "numerical_scratch_bytes": 4400,
      "output_rows": 4,
      "plan_json_bytes": 48015,
      "plan_objects_bytes": 257940,
      "recipe_json_bytes": 2699,
      "report_bytes": 124245,
      "result_json_bytes": 25990,
      "result_objects_bytes": 169964,
      "schema_json_bytes": 17789,
      "selected_numeric_bytes": 216,
      "source_base_bytes": 159764,
      "stage_csv_bytes": 12646,
      "support_records": 16,
      "table_csv_bytes": 4738,
      "trace_bytes": 32777,
      "trace_objects_bytes": 5790456,
      "transport_reserve_bytes": 39028036,
      "verify_bytes": 177450020,
      "work_cell_visits": 1191
    },
    "old": {
      "build_bytes": 155548118,
      "bundle_bytes": 274922,
      "common_bytes": 155300184,
      "coordinate_canonical_bytes": 1218,
      "coordinate_label_utf8_bytes": 10,
      "coordinate_objects_bytes": 16464,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 93716,
      "estimated_memory_bytes": 161854803,
      "explain_bytes": 161854803,
      "formula_version": 2,
      "manifest_json_bytes": 38800,
      "numerical_scratch_bytes": 4400,
      "output_rows": 4,
      "plan_json_bytes": 48015,
      "plan_objects_bytes": 257940,
      "recipe_json_bytes": 2699,
      "report_bytes": 124245,
      "result_json_bytes": 25990,
      "result_objects_bytes": 169964,
      "schema_json_bytes": 17789,
      "selected_numeric_bytes": 216,
      "source_base_bytes": 159764,
      "stage_csv_bytes": 12646,
      "support_records": 16,
      "table_csv_bytes": 4738,
      "trace_bytes": 32777,
      "trace_objects_bytes": 5790456,
      "transport_reserve_bytes": 17544032,
      "verify_bytes": 155966016,
      "work_cell_visits": 1191
    }
  },
  "F3_support_edges.json": {
    "new": {
      "build_bytes": 175330205,
      "bundle_bytes": 220800,
      "common_bytes": 175190378,
      "coordinate_canonical_bytes": 876,
      "coordinate_label_utf8_bytes": 26,
      "coordinate_objects_bytes": 9844,
      "coordinate_raw_bytes": 56,
      "descriptor_objects_bytes": 42288,
      "estimated_memory_bytes": 181332349,
      "explain_bytes": 181332349,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 1856,
      "output_rows": 4,
      "plan_json_bytes": 44388,
      "plan_objects_bytes": 228460,
      "recipe_json_bytes": 2185,
      "report_bytes": 100239,
      "result_json_bytes": 14193,
      "result_objects_bytes": 97248,
      "schema_json_bytes": 11114,
      "selected_numeric_bytes": 192,
      "source_base_bytes": 108336,
      "stage_csv_bytes": 6444,
      "support_records": 8,
      "table_csv_bytes": 4767,
      "trace_bytes": 21295,
      "trace_objects_bytes": 5701184,
      "transport_reserve_bytes": 37722826,
      "verify_bytes": 175567280,
      "work_cell_visits": 637
    },
    "old": {
      "build_bytes": 154826161,
      "bundle_bytes": 220800,
      "common_bytes": 154686334,
      "coordinate_canonical_bytes": 876,
      "coordinate_label_utf8_bytes": 26,
      "coordinate_objects_bytes": 9844,
      "coordinate_raw_bytes": 56,
      "descriptor_objects_bytes": 42288,
      "estimated_memory_bytes": 160828305,
      "explain_bytes": 160828305,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 1856,
      "output_rows": 4,
      "plan_json_bytes": 44388,
      "plan_objects_bytes": 228460,
      "recipe_json_bytes": 2185,
      "report_bytes": 100239,
      "result_json_bytes": 14193,
      "result_objects_bytes": 97248,
      "schema_json_bytes": 11114,
      "selected_numeric_bytes": 192,
      "source_base_bytes": 108336,
      "stage_csv_bytes": 6444,
      "support_records": 8,
      "table_csv_bytes": 4767,
      "trace_bytes": 21295,
      "trace_objects_bytes": 5701184,
      "transport_reserve_bytes": 17218782,
      "verify_bytes": 155063236,
      "work_cell_visits": 637
    }
  },
  "F5.json": {
    "new": {
      "build_bytes": 175492884,
      "bundle_bytes": 224274,
      "common_bytes": 175305674,
      "coordinate_canonical_bytes": 1254,
      "coordinate_label_utf8_bytes": 6,
      "coordinate_objects_bytes": 16448,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 85524,
      "estimated_memory_bytes": 181574413,
      "explain_bytes": 181574413,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 4352,
      "output_rows": 4,
      "plan_json_bytes": 41417,
      "plan_objects_bytes": 206036,
      "recipe_json_bytes": 1429,
      "report_bytes": 100143,
      "result_json_bytes": 19450,
      "result_objects_bytes": 128860,
      "schema_json_bytes": 12088,
      "selected_numeric_bytes": 192,
      "source_base_bytes": 151572,
      "stage_csv_bytes": 9765,
      "support_records": 12,
      "table_csv_bytes": 2512,
      "trace_bytes": 20877,
      "trace_objects_bytes": 5702828,
      "transport_reserve_bytes": 37722826,
      "verify_bytes": 175808954,
      "work_cell_visits": 709
    },
    "old": {
      "build_bytes": 154991682,
      "bundle_bytes": 224274,
      "common_bytes": 154804472,
      "coordinate_canonical_bytes": 1254,
      "coordinate_label_utf8_bytes": 6,
      "coordinate_objects_bytes": 16448,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 85524,
      "estimated_memory_bytes": 161073211,
      "explain_bytes": 161073211,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 4352,
      "output_rows": 4,
      "plan_json_bytes": 41417,
      "plan_objects_bytes": 206036,
      "recipe_json_bytes": 1429,
      "report_bytes": 100143,
      "result_json_bytes": 19450,
      "result_objects_bytes": 128860,
      "schema_json_bytes": 12088,
      "selected_numeric_bytes": 192,
      "source_base_bytes": 151572,
      "stage_csv_bytes": 9765,
      "support_records": 12,
      "table_csv_bytes": 2512,
      "trace_bytes": 20877,
      "trace_objects_bytes": 5702828,
      "transport_reserve_bytes": 17221624,
      "verify_bytes": 155307752,
      "work_cell_visits": 709
    }
  },
  "F5_permuted.json": {
    "new": {
      "build_bytes": 175492884,
      "bundle_bytes": 224274,
      "common_bytes": 175305674,
      "coordinate_canonical_bytes": 1254,
      "coordinate_label_utf8_bytes": 6,
      "coordinate_objects_bytes": 16448,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 85524,
      "estimated_memory_bytes": 181574413,
      "explain_bytes": 181574413,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 4352,
      "output_rows": 4,
      "plan_json_bytes": 41417,
      "plan_objects_bytes": 206036,
      "recipe_json_bytes": 1429,
      "report_bytes": 100143,
      "result_json_bytes": 19450,
      "result_objects_bytes": 128860,
      "schema_json_bytes": 12088,
      "selected_numeric_bytes": 192,
      "source_base_bytes": 151572,
      "stage_csv_bytes": 9765,
      "support_records": 12,
      "table_csv_bytes": 2512,
      "trace_bytes": 20877,
      "trace_objects_bytes": 5702828,
      "transport_reserve_bytes": 37722826,
      "verify_bytes": 175808954,
      "work_cell_visits": 709
    },
    "old": {
      "build_bytes": 154991682,
      "bundle_bytes": 224274,
      "common_bytes": 154804472,
      "coordinate_canonical_bytes": 1254,
      "coordinate_label_utf8_bytes": 6,
      "coordinate_objects_bytes": 16448,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 85524,
      "estimated_memory_bytes": 161073211,
      "explain_bytes": 161073211,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 4352,
      "output_rows": 4,
      "plan_json_bytes": 41417,
      "plan_objects_bytes": 206036,
      "recipe_json_bytes": 1429,
      "report_bytes": 100143,
      "result_json_bytes": 19450,
      "result_objects_bytes": 128860,
      "schema_json_bytes": 12088,
      "selected_numeric_bytes": 192,
      "source_base_bytes": 151572,
      "stage_csv_bytes": 9765,
      "support_records": 12,
      "table_csv_bytes": 2512,
      "trace_bytes": 20877,
      "trace_objects_bytes": 5702828,
      "transport_reserve_bytes": 17221624,
      "verify_bytes": 155307752,
      "work_cell_visits": 709
    }
  },
  "F6.json": {
    "new": {
      "build_bytes": 175604954,
      "bundle_bytes": 260372,
      "common_bytes": 175390962,
      "coordinate_canonical_bytes": 1218,
      "coordinate_label_utf8_bytes": 10,
      "coordinate_objects_bytes": 16464,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 85524,
      "estimated_memory_bytes": 181793099,
      "explain_bytes": 181793099,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 4352,
      "output_rows": 4,
      "plan_json_bytes": 45395,
      "plan_objects_bytes": 239352,
      "recipe_json_bytes": 2303,
      "report_bytes": 122255,
      "result_json_bytes": 22344,
      "result_objects_bytes": 146960,
      "schema_json_bytes": 14084,
      "selected_numeric_bytes": 224,
      "source_base_bytes": 151572,
      "stage_csv_bytes": 9453,
      "support_records": 12,
      "table_csv_bytes": 7068,
      "trace_bytes": 26687,
      "trace_objects_bytes": 5747132,
      "transport_reserve_bytes": 37722826,
      "verify_bytes": 175965906,
      "work_cell_visits": 757
    },
    "old": {
      "build_bytes": 155265746,
      "bundle_bytes": 260372,
      "common_bytes": 155051754,
      "coordinate_canonical_bytes": 1218,
      "coordinate_label_utf8_bytes": 10,
      "coordinate_objects_bytes": 16464,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 85524,
      "estimated_memory_bytes": 161453891,
      "explain_bytes": 161453891,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 4352,
      "output_rows": 4,
      "plan_json_bytes": 45395,
      "plan_objects_bytes": 239352,
      "recipe_json_bytes": 2303,
      "report_bytes": 122255,
      "result_json_bytes": 22344,
      "result_objects_bytes": 146960,
      "schema_json_bytes": 14084,
      "selected_numeric_bytes": 224,
      "source_base_bytes": 151572,
      "stage_csv_bytes": 9453,
      "support_records": 12,
      "table_csv_bytes": 7068,
      "trace_bytes": 26687,
      "trace_objects_bytes": 5747132,
      "transport_reserve_bytes": 17383618,
      "verify_bytes": 155626698,
      "work_cell_visits": 757
    }
  },
  "hand": {
    "new": {
      "build_bytes": 175363885,
      "bundle_bytes": 206227,
      "common_bytes": 175245826,
      "coordinate_canonical_bytes": 1152,
      "coordinate_label_utf8_bytes": 0,
      "coordinate_objects_bytes": 13532,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 58740,
      "estimated_memory_bytes": 181415937,
      "explain_bytes": 181415937,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 3760,
      "output_rows": 2,
      "plan_json_bytes": 42390,
      "plan_objects_bytes": 223348,
      "recipe_json_bytes": 1680,
      "report_bytes": 92570,
      "result_json_bytes": 11661,
      "result_objects_bytes": 83076,
      "schema_json_bytes": 11266,
      "selected_numeric_bytes": 232,
      "source_base_bytes": 124788,
      "stage_csv_bytes": 6737,
      "support_records": 8,
      "table_csv_bytes": 2453,
      "trace_bytes": 28983,
      "trace_objects_bytes": 5763968,
      "transport_reserve_bytes": 37722826,
      "verify_bytes": 175565020,
      "work_cell_visits": 642
    },
    "old": {
      "build_bytes": 155086673,
      "bundle_bytes": 206227,
      "common_bytes": 154968614,
      "coordinate_canonical_bytes": 1152,
      "coordinate_label_utf8_bytes": 0,
      "coordinate_objects_bytes": 13532,
      "coordinate_raw_bytes": 72,
      "descriptor_objects_bytes": 58740,
      "estimated_memory_bytes": 161138725,
      "explain_bytes": 161138725,
      "formula_version": 2,
      "manifest_json_bytes": 37470,
      "numerical_scratch_bytes": 3760,
      "output_rows": 2,
      "plan_json_bytes": 42390,
      "plan_objects_bytes": 223348,
      "recipe_json_bytes": 1680,
      "report_bytes": 92570,
      "result_json_bytes": 11661,
      "result_objects_bytes": 83076,
      "schema_json_bytes": 11266,
      "selected_numeric_bytes": 232,
      "source_base_bytes": 124788,
      "stage_csv_bytes": 6737,
      "support_records": 8,
      "table_csv_bytes": 2453,
      "trace_bytes": 28983,
      "trace_objects_bytes": 5763968,
      "transport_reserve_bytes": 17445614,
      "verify_bytes": 155287808,
      "work_cell_visits": 642
    }
  },
  "maximum-control": {
    "new": {
      "build_bytes": 269379477,
      "bundle_bytes": 1724787,
      "common_bytes": 268446118,
      "coordinate_canonical_bytes": 4032,
      "coordinate_label_utf8_bytes": 0,
      "coordinate_objects_bytes": 53696,
      "coordinate_raw_bytes": 128,
      "descriptor_objects_bytes": 1169944,
      "estimated_memory_bytes": 280995792,
      "explain_bytes": 280995792,
      "formula_version": 2,
      "manifest_json_bytes": 119930,
      "numerical_scratch_bytes": 432,
      "output_rows": 1,
      "plan_json_bytes": 343056,
      "plan_objects_bytes": 3087204,
      "recipe_json_bytes": 46741,
      "report_bytes": 656566,
      "result_json_bytes": 96653,
      "result_objects_bytes": 643400,
      "schema_json_bytes": 372049,
      "selected_numeric_bytes": 512,
      "source_base_bytes": 1235992,
      "stage_csv_bytes": 70144,
      "support_records": 64,
      "table_csv_bytes": 19648,
      "trace_bytes": 384812,
      "trace_objects_bytes": 8885120,
      "transport_reserve_bytes": 118645846,
      "verify_bytes": 270956236,
      "work_cell_visits": 2176
    },
    "old": {
      "build_bytes": 179322126,
      "bundle_bytes": 1724787,
      "common_bytes": 178388767,
      "coordinate_canonical_bytes": 4032,
      "coordinate_label_utf8_bytes": 0,
      "coordinate_objects_bytes": 53696,
      "coordinate_raw_bytes": 128,
      "descriptor_objects_bytes": 1169944,
      "estimated_memory_bytes": 190938441,
      "explain_bytes": 190938441,
      "formula_version": 2,
      "manifest_json_bytes": 119930,
      "numerical_scratch_bytes": 432,
      "output_rows": 1,
      "plan_json_bytes": 343056,
      "plan_objects_bytes": 3087204,
      "recipe_json_bytes": 46741,
      "report_bytes": 656566,
      "result_json_bytes": 96653,
      "result_objects_bytes": 643400,
      "schema_json_bytes": 372049,
      "selected_numeric_bytes": 512,
      "source_base_bytes": 1235992,
      "stage_csv_bytes": 70144,
      "support_records": 64,
      "table_csv_bytes": 19648,
      "trace_bytes": 384812,
      "trace_objects_bytes": 8885120,
      "transport_reserve_bytes": 28588495,
      "verify_bytes": 180898885,
      "work_cell_visits": 2176
    }
  },
  "tiny-file": {
    "new": {
      "build_bytes": 172229054,
      "bundle_bytes": 130222,
      "common_bytes": 172217094,
      "coordinate_canonical_bytes": 0,
      "coordinate_label_utf8_bytes": 0,
      "coordinate_objects_bytes": 512,
      "coordinate_raw_bytes": 0,
      "descriptor_objects_bytes": 15328,
      "estimated_memory_bytes": 177869056,
      "explain_bytes": 177869056,
      "formula_version": 2,
      "manifest_json_bytes": 34798,
      "numerical_scratch_bytes": 32,
      "output_rows": 1,
      "plan_json_bytes": 35320,
      "plan_objects_bytes": 154152,
      "recipe_json_bytes": 529,
      "report_bytes": 57028,
      "result_json_bytes": 736,
      "result_objects_bytes": 9752,
      "schema_json_bytes": 1197,
      "selected_numeric_bytes": 8,
      "source_base_bytes": 84960,
      "stage_csv_bytes": 0,
      "support_records": 0,
      "table_csv_bytes": 614,
      "trace_bytes": 7258,
      "trace_objects_bytes": 5596516,
      "transport_reserve_bytes": 35090074,
      "verify_bytes": 172250766,
      "work_cell_visits": 8
    },
    "old": {
      "build_bytes": 153973389,
      "bundle_bytes": 130222,
      "common_bytes": 153961429,
      "coordinate_canonical_bytes": 0,
      "coordinate_label_utf8_bytes": 0,
      "coordinate_objects_bytes": 512,
      "coordinate_raw_bytes": 0,
      "descriptor_objects_bytes": 15328,
      "estimated_memory_bytes": 159613391,
      "explain_bytes": 159613391,
      "formula_version": 2,
      "manifest_json_bytes": 34798,
      "numerical_scratch_bytes": 32,
      "output_rows": 1,
      "plan_json_bytes": 35320,
      "plan_objects_bytes": 154152,
      "recipe_json_bytes": 529,
      "report_bytes": 57028,
      "result_json_bytes": 736,
      "result_objects_bytes": 9752,
      "schema_json_bytes": 1197,
      "selected_numeric_bytes": 8,
      "source_base_bytes": 84960,
      "stage_csv_bytes": 0,
      "support_records": 0,
      "table_csv_bytes": 614,
      "trace_bytes": 7258,
      "trace_objects_bytes": 5596516,
      "transport_reserve_bytes": 16834409,
      "verify_bytes": 153995101,
      "work_cell_visits": 8
    }
  },
  "tiny-memory": {
    "new": {
      "build_bytes": 172237138,
      "bundle_bytes": 130330,
      "common_bytes": 172225178,
      "coordinate_canonical_bytes": 0,
      "coordinate_label_utf8_bytes": 0,
      "coordinate_objects_bytes": 512,
      "coordinate_raw_bytes": 0,
      "descriptor_objects_bytes": 15336,
      "estimated_memory_bytes": 177877184,
      "explain_bytes": 177877184,
      "formula_version": 2,
      "manifest_json_bytes": 34810,
      "numerical_scratch_bytes": 32,
      "output_rows": 1,
      "plan_json_bytes": 35344,
      "plan_objects_bytes": 154168,
      "recipe_json_bytes": 529,
      "report_bytes": 57100,
      "result_json_bytes": 736,
      "result_objects_bytes": 9752,
      "schema_json_bytes": 1197,
      "selected_numeric_bytes": 8,
      "source_base_bytes": 81384,
      "stage_csv_bytes": 0,
      "support_records": 0,
      "table_csv_bytes": 614,
      "trace_bytes": 7270,
      "trace_objects_bytes": 5596524,
      "transport_reserve_bytes": 35101654,
      "verify_bytes": 172258850,
      "work_cell_visits": 8
    },
    "old": {
      "build_bytes": 153969977,
      "bundle_bytes": 130330,
      "common_bytes": 153958017,
      "coordinate_canonical_bytes": 0,
      "coordinate_label_utf8_bytes": 0,
      "coordinate_objects_bytes": 512,
      "coordinate_raw_bytes": 0,
      "descriptor_objects_bytes": 15336,
      "estimated_memory_bytes": 159610023,
      "explain_bytes": 159610023,
      "formula_version": 2,
      "manifest_json_bytes": 34810,
      "numerical_scratch_bytes": 32,
      "output_rows": 1,
      "plan_json_bytes": 35344,
      "plan_objects_bytes": 154168,
      "recipe_json_bytes": 529,
      "report_bytes": 57100,
      "result_json_bytes": 736,
      "result_objects_bytes": 9752,
      "schema_json_bytes": 1197,
      "selected_numeric_bytes": 8,
      "source_base_bytes": 81384,
      "stage_csv_bytes": 0,
      "support_records": 0,
      "table_csv_bytes": 614,
      "trace_bytes": 7270,
      "trace_objects_bytes": 5596524,
      "transport_reserve_bytes": 16834493,
      "verify_bytes": 153991689,
      "work_cell_visits": 8
    }
  }
}''')
CHANGED = {'transport_reserve_bytes','common_bytes','build_bytes','verify_bytes','explain_bytes','estimated_memory_bytes'}

def budget():
    name = 'replicatetable._native_budget'
    assert importlib.util.find_spec(name) is not None, 'Missing private native budget arithmetic'
    return importlib.import_module(name)

def fixture_input(name):
    root=Path(__file__).resolve().parents[1]/'frozen'/'original'/'fixtures'
    fixture=json.loads((root/name).read_text());data=fixture['data']
    rec=Recipe.from_dict(adapt_legacy_recipe(fixture));dims={n:len(v) for n,v in data['coords'].items()}
    variables={n:descriptor(tuple(v['dims']),tuple(dims[d] for d in v['dims']),v['dtype'],v['units']) for n,v in data['variables'].items()}
    selected=set(rec.row_dims)
    for c in rec.columns:
        selected.update(data['variables'][c['source']]['dims'])
        if c['stages'] and c['stages'][0]['op']=='weighted_mean':selected.update(data['variables'][c['stages'][0]['weights']]['dims'])
    coords={}
    for n,labels in data['coords'].items():
        dtype='<U'+str(max(1,max(map(len,labels)))) if type(labels[0]) is str else '<f8' if type(labels[0]) is float else '<i8'
        coords[n]=Coordinate(dtype,labels,sorted(range(len(labels)),key=labels.__getitem__))
    source=inspection(dims,variables,{n:descriptor((n,),(len(c.values),),c.dtype) for n,c in coords.items()})
    facts=tuple(i._coordinate_facts(n,coords[n],raw_bytes=len(coords[n].values)*8,preselection_j=i._owned_cost(coords[n].values).json_bytes) for n in sorted(selected))
    units=tuple((operation(c['source_unit'],c['target_unit']),operation(weight=True) if c['stages'] and c['stages'][0]['op']=='weighted_mean' else None) for c in rec.columns)
    return i._CompilationInput(source,i._memory_binding(source,(),512),rec,facts,freeze(runtime_example()),units)

class NativeBudgetEstimateTests(unittest.TestCase):
    def test_new_twelve_cases_keep_31_keys_25_unchanged_six_move(self):
        factories={'tiny-memory':synthetic_input,'tiny-file':lambda:synthetic_input(kind='file'),
                   'hand':hand_input,'maximum-control':maximum_input}
        self.assertEqual(len(EXPECTED),12)
        self.assertNotIn('F4.json',EXPECTED)
        for label,expected in EXPECTED.items():
            with self.subTest(label=label):
                inp=factories[label]() if label in factories else fixture_input(label)
                actual=dict(e._estimate_compilation(inp).items())
                self.assertEqual(len(actual),31)
                self.assertEqual(actual,expected['new'])
                self.assertEqual({k for k in actual if actual[k]!=expected['old'][k]},CHANGED)
                deltas={actual[k]-expected['old'][k] for k in CHANGED}
                self.assertEqual(len(deltas),1);self.assertGreater(next(iter(deltas)),0)
        self.assertEqual(EXPECTED['tiny-file']['new']['estimated_memory_bytes'],177869056)
        self.assertEqual(EXPECTED['maximum-control']['new']['estimated_memory_bytes'],280995792)

    def test_escape_bound_pays_unchanged_generic_parser(self):
        m=budget();raw=canonical_bytes({'labels':['\x01'*32]});scan=json_prepass(raw)
        semantic=primitive_bounds({'labels':['\x01'*32]}).object_bytes
        self.assertEqual((len(raw),semantic,scan.object_bytes),(208,1688,2328))
        self.assertEqual(m._wire_bytes(len(raw),semantic),8600)
        self.assertEqual(m._decoder_bytes(len(raw),scan.object_bytes),8024)
        self.assertEqual(5*len(raw)+3*semantic,6104)
        live=536870912-6104
        with self.assertRaises(Refusal):m._combined_guard(live,m._wire_bytes(len(raw),semantic))

    def test_all_21_escape_spellings_keep_scanner_inequality(self):
        m=budget()
        values=['a','"','\\','\b','\f','\n','\r','\t','\x00','\x01','/','é','💩','\ud7ff','\ue000','\U0010ffff']
        raws=[canonical_bytes({'x':[s]}) for s in values]
        raws += [('{"x":["'+s+'"]}\n').encode() for s in [r'\u0061',r'\u00e9',r'\ud83d\udca9',r'\/',r'\u0001']]
        self.assertEqual(len(raws),21)
        for raw in raws:
            scan=json_prepass(raw);semantic=primitive_bounds(json.loads(raw)).object_bytes
            self.assertLessEqual(scan.object_bytes,semantic+4*len(raw))
            self.assertLessEqual(m._decoder_bytes(len(raw),scan.object_bytes),m._wire_bytes(len(raw),semantic))

    def test_transport_keeps_persistent_state_outside_maximum(self):
        m=budget()
        self.assertEqual(m._transport_bytes(8,9000,9,100),9108)
        self.assertEqual(m._transport_bytes(8,9000,20,100),19400)
        with self.assertRaises(Refusal):m._combined_guard(536870912-965*20,m._transport_bytes(0,1,20,100))
        # Historical isolated R10 worksheet is NOT complete route admission.
        old=134217728+2097152+3*65536+100000+160*512+965*350000
        self.assertEqual(old,474443408);self.assertLessEqual(old,536870912)
        with self.assertRaises(Refusal):m._combined_guard(old,128*1048576)

    def test_no_serialized_or_output_forest_during_projection(self):
        m=budget();inp=maximum_input()
        with (patch('replicatetable.codec.canonical_bytes',side_effect=AssertionError('serialized')),
              patch('replicatetable.codec.freeze',side_effect=AssertionError('forest')),
              patch('replicatetable.codec.thaw',side_effect=AssertionError('forest')),
              patch.object(e,'_payload_paths',side_effect=AssertionError('path list'))):
            self.assertEqual(e._estimate_compilation(inp)['estimated_memory_bytes'],280995792)

    def test_reviewed_dense_64mib_family_stays_refused(self):
        m=budget()
        # Independently reviewed lower bound, not a populated native dataset
        # or an assertion that all individually maximal shapes can coexist.
        old_lower_bound=606419042
        self.assertGreater(old_lower_bound,536870912)
        with self.assertRaises(Refusal):m._combined_guard(old_lower_bound,0)
        for n,p in ((208,1688),(16777216,500000),(1,128)):
            self.assertGreaterEqual(m._wire_bytes(n,p),5*n+3*p)
            self.assertGreaterEqual(m._transport_bytes(67108864,m._wire_bytes(n,p),1,1434532),
                                    67108864+5*n+3*p)

    def test_previously_admitted_synthetic_transport_boundary_now_refuses(self):
        # Sealed committed estimator admitted this metadata-only shape at
        # 468911985. The reviewed combined transport correction must refuse;
        # all independent raw/shape/work caps remain unchanged.
        rec=recipe((),[{'name':f'c{n}','source':'v','source_unit':None,'target_unit':None,
                       'broadcast':[],'stages':[stage('mean',('d',))]} for n in range(12)])
        inp=synthetic_input({'d':1000},{'v':descriptor(('d',),(1000,))},
            {'d':Coordinate('<i8',list(range(1000)),list(range(1000)))},rec)
        with self.assertRaises(Refusal) as caught:e._estimate_compilation(inp)
        self.assertEqual(caught.exception.code,'estimated_memory_limit')
