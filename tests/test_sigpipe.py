"""SIGPIPE / BrokenPipeError handling (#84)."""

from __future__ import annotations

import signal
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from ssky import main as main_mod


def test_setup_restores_sigpipe_default():
    if not hasattr(signal, "SIGPIPE"):
        pytest.skip("SIGPIPE not available on this platform")
    main_mod.setup()
    assert signal.getsignal(signal.SIGPIPE) == signal.SIG_DFL


def test_execute_broken_pipe_exits_with_sigpipe_code():
    args = MagicMock()
    args.format = "id"
    args.output = None
    args.delimiter = " "

    def _raise(**_kwargs):
        raise BrokenPipeError()

    with patch("ssky.main.import_module") as imp:
        mod = MagicMock()
        mod.get = _raise
        imp.return_value = mod
        with pytest.raises(SystemExit) as ei:
            main_mod.execute("get", args)
    expected = 128 + int(getattr(signal, "SIGPIPE", 13))
    assert ei.value.code == expected


def test_pipe_to_early_consumer_has_empty_stderr():
    """Regression: early pipe close must not dump a traceback on stderr."""
    code = (
        "import signal, sys\n"
        "if hasattr(signal, 'SIGPIPE'):\n"
        "    signal.signal(signal.SIGPIPE, signal.SIG_DFL)\n"
        "sys.stdout.write('line1\\n')\n"
        "sys.stdout.flush()\n"
        "sys.stdout.write('line2\\n')\n"
        "sys.stdout.flush()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None
    _ = proc.stdout.readline()
    proc.stdout.close()
    stderr = proc.stderr.read()
    proc.wait(timeout=5)
    assert b"BrokenPipeError" not in stderr
    assert b"Traceback" not in stderr
