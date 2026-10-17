"""Bounded internal errors. Public boundaries supply fixed safe literals."""


class Refusal(ValueError):
    """A stable code and bounded safe message; no input repr is interpolated."""
    exit_code = 2

    def __init__(self, code, message='Input does not satisfy the required contract.'):
        if (type(code) is not str or not 1 <= len(code) <= 128 or
                any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in code)):
            code = 'invalid_source'
            message = 'Invalid error descriptor.'
        if (type(message) is not str or not 1 <= len(message) <= 512 or
                any(ord(c) < 32 or 127 <= ord(c) <= 159 or ord(c) >= 127 for c in message)):
            message = 'Operation did not complete; detailed diagnostics were suppressed.'
        self.code = code
        self.message = message
        super().__init__(message)


class ComputationError(Refusal):
    """Operational computation failure, distinct from input refusal."""
    exit_code = 3
