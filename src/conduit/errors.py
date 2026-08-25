"""Error types conduit raises deliberately at the user.

Every error in this module marks a condition conduit *expected* to be possible and
wrote a message for: a malformed config, a variable the input file does not contain,
a contract mismatch, an unwritable output path. The CLI catches `ConduitError` and
prints the message alone, with no traceback, because the frames say nothing a user
can act on. Anything else propagates with its traceback intact, which is what you
want when the cause is a bug rather than a bad input.

The concrete classes each inherit the stdlib type a library caller would naturally
catch, so `except ValueError` and `except FileNotFoundError` keep working; the
`ConduitError` base exists only so the CLI can distinguish "we meant this" from
"something went wrong".

This module imports nothing, from conduit or elsewhere, so any module may raise
from it without risking an import cycle.
"""


class ConduitError(Exception):
    """Base for every error conduit raises deliberately. Never raised directly."""


class ConduitValueError(ConduitError, ValueError):
    """A bad value: config, wiring, contracts, or anything else conduit validates."""


class ConduitFileNotFoundError(ConduitError, FileNotFoundError):
    """A file or store conduit was told to read or write is not there."""


class ConduitPermissionError(ConduitError, PermissionError):
    """A path conduit was told to write to exists but is not writable."""
