"""Same-callable replacement is ambiguous without an observed setter return."""
import signal
import unittest
from unittest.mock import patch

from tests.unit import test_native_supervisor_signals as fixtures


class SameCallableReplacementTests(unittest.TestCase):
    setUp = fixtures.NativeSignalPolicyTests.setUp
    restore_fixture_policy = fixtures.NativeSignalPolicyTests.restore_fixture_policy

    def run_replacement(self, during_int):
        class Marker(BaseException):
            pass
        marker = Marker('caller installed same callable with new action')
        notes = ['caller note remains untouched']
        marker.__notes__ = notes
        def old_int(signum, frame):
            pass
        def old_term(signum, frame):
            pass
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
        signal.siginterrupt(signal.SIGTERM, True)
        policy = self.m._enter_signal_policy(self.deadline)
        actual = signal.signal
        replacement_action = None
        interrupted = False
        def replace_then_raise(sig, handler):
            nonlocal replacement_action, interrupted
            target = signal.SIGINT if during_int else signal.SIGTERM
            if sig == target and not interrupted:
                interrupted = True
                actual(sig, handler)
                actual(signal.SIGTERM, old_term)
                signal.siginterrupt(signal.SIGTERM, False)
                replacement_action = fixtures.action(signal.SIGTERM)
                raise marker
            return actual(sig, handler)
        with patch.object(signal, 'signal', replace_then_raise):
            with self.assertRaises(Marker) as caught:
                self.m._leave_signal_policy(policy)
        self.assertIs(caught.exception, marker)
        self.assertIs(marker.__notes__, notes)
        self.assertIs(signal.getsignal(signal.SIGTERM), old_term)
        # This assertion must reproduce the overwrite independently of later
        # terminal ownership checks before the minimal correction is made.
        self.assertEqual(fixtures.action(signal.SIGTERM), replacement_action)
        self.assertIs(self.m._ACTIVE_POLICY, policy)
        self.assertTrue(policy.active)
        self.assertTrue(policy._touched & 2)
        self.assertTrue(self.m._SIGNAL_POISONED)
        self.assertEqual(policy.restoration_message,
                         'Signal restoration is incomplete; restart this process before native work.')

    def test_same_callable_change_on_raising_term_setter_is_not_overwritten(self):
        self.run_replacement(False)

    def test_same_callable_change_before_term_handoff_is_not_overwritten(self):
        self.run_replacement(True)


if __name__ == '__main__':
    unittest.main()
