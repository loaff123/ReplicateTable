"""Small observer-only checks for primitive-bound helper lifetime.

The profile hook watches only this module's bounded visitor calls. It does not
walk the heap; all process settings are restored after each isolated test.
"""
import gc
import sys
import unittest
import weakref

from replicatetable import codec
from replicatetable.errors import Refusal


class PrimitiveBoundsLifetimeTests(unittest.TestCase):
    def _observe(self, *, fail):
        previous_profile = sys.getprofile()
        previously_enabled = gc.isenabled()
        references = []

        def observe(frame, event, argument):
            if (event == 'call' and frame.f_code.co_filename == codec.__file__
                    and frame.f_code.co_name == 'visit'):
                visitor = frame.f_locals.get('visit')
                if visitor is not None:
                    references.append(weakref.ref(visitor))

        gc.disable()
        sys.setprofile(observe)
        try:
            for _ in range(16):
                if fail:
                    try:
                        codec.primitive_bounds({'x': [float('nan')]})
                    except Refusal as error:
                        self.assertEqual(error.code, 'invalid_json')
                    else:
                        self.fail('expected the unchanged nonfinite refusal')
                else:
                    measured = codec.primitive_bounds({'x': [1, 'ok']})
                    self.assertEqual(measured.json_bytes, 60)
                    self.assertEqual(measured.object_bytes, 1804)
            # Stop observing before assertions. Do not collect or re-enable GC
            # until lifetime is checked, which would hide a recursive cycle.
            sys.setprofile(previous_profile)
            self.assertTrue(references, 'observer did not see the private walk')
            self.assertFalse(any(reference() is not None for reference in references),
                             'a discarded primitive walk retained its closure')
        finally:
            sys.setprofile(previous_profile)
            if previously_enabled:
                gc.enable()

    def test_success_releases_recursive_helper_without_cyclic_gc(self):
        self._observe(fail=False)

    def test_refusal_releases_recursive_helper_without_cyclic_gc(self):
        self._observe(fail=True)


if __name__ == '__main__':
    unittest.main()
