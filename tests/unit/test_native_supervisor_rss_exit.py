"""An absent RSS sample is not terminal status or permanent wait loss."""
import time
import unittest
from unittest.mock import patch

from replicatetable._native_budget_state import _CancellationState, _inherited_deadline
from replicatetable.errors import Refusal
from tests.unit import test_native_supervisor_child as child_fixture


class MissingRSSExitTests(unittest.TestCase):
    def setUp(self):
        self.fixture = child_fixture.AdoptedChildTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.m = self.fixture.m

    def test_transient_missing_sample_keeps_owned_child_until_actual_reap(self):
        owner, _ = self.fixture.child('import time; time.sleep(0.06)')
        actual = self.m._read_child_rss
        observations = []
        def temporarily_missing(child, deadline):
            observations.append(child.pid)
            return None if len(observations) == 1 else actual(child, deadline)
        with patch.object(self.m, '_read_child_rss', temporarily_missing):
            status = self.m._wait_child(owner, self.fixture.budget)
        self.assertEqual(status, 0)
        self.assertEqual(owner.state, 'REAPED')
        self.assertGreater(len(observations), 1)
        self.assertTrue(all(pid == owner.pid for pid in observations))

    def test_persistent_absence_fails_after_one_target_sample_interval(self):
        owner, _ = self.fixture.child()
        with patch.object(self.m, '_read_child_rss', return_value=None) as observation:
            with self.assertRaises(Refusal) as caught:
                self.m._wait_child(owner, self.fixture.budget)
        self.assertEqual(caught.exception.code, 'supervision_unavailable')
        self.assertEqual(caught.exception.exit_code, 2)
        self.assertGreater(observation.call_count, 1)
        self.assertEqual(owner.state, 'REAPED')

    def test_earlier_original_deadline_remains_primary_and_reaps(self):
        owner, _ = self.fixture.child()
        original = time.monotonic_ns() + 5000000
        deadline = _inherited_deadline(original, _CancellationState())
        with patch.object(self.m, '_read_child_rss', return_value=None) as observation:
            with self.assertRaises(Refusal) as caught:
                self.m._wait_child(owner, deadline)
        self.assertEqual(caught.exception.code, 'operation_timeout')
        self.assertEqual(caught.exception.exit_code, 3)
        self.assertGreaterEqual(observation.call_count, 1)
        self.assertEqual(deadline.deadline_ns, original)
        self.assertEqual(owner.state, 'REAPED')


if __name__ == '__main__':
    unittest.main()
