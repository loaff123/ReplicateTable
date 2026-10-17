"""New joint-invalid regression, authored after exact source recovery.

These cases preserve the earlier standalone helper's source-kind/base checks
before metadata checks. They do not establish a universal cross-route priority.
"""
import unittest
from replicatetable import _resource_estimates as estimates
from replicatetable.errors import Refusal


class StandalonePrecedenceTests(unittest.TestCase):
    def check_code(self, expected, source_base, *, source_kind='memory'):
        with self.assertRaises(Refusal) as caught:
            estimates._standalone_reservation(source_base, 16 * 1024**2 + 1, 0, 0,
                                              source_kind=source_kind)
        self.assertEqual(caught.exception.code, expected)

    def test_unknown_source_kind_before_oversized_metadata(self):
        self.check_code('invalid_source', 0, source_kind='unknown')

    def test_oversized_memory_base_before_oversized_metadata(self):
        self.check_code('source_bytes_limit', 128 * 1024**2 + 1)

    def test_valid_source_reaches_metadata_refusal(self):
        self.check_code('metadata_bytes_limit', 0)


if __name__ == '__main__':
    unittest.main()
