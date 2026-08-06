"""SIGPIPE / BrokenPipeError handling (#84)."""

from __future__ import annotations

import signal
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from ssky import main as main_mod


def test_setup_restores_sigpipe_default():
    """Run setup() in a subprocess so it cannot swap this process's stdio."""
    if not hasattr(signal, "SIGPIPE"):
        pytest.skip("SIGPIPE not available on this platform")

    code = (
        "import signal\n"
        "from ssky.main import setup\n"
        "signal.signal(signal.SIGPIPE, signal.SIG_IGN)\n"
        "setup()\n"
        "assert signal.getsignal(signal.SIGPIPE) == signal.SIG_DFL\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_execute_broken_pipe_reraise_after_dup2():
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
        with pytest.raises(BrokenPipeError):
            main_mod.execute("get", args)


def test_main_broken_pipe_returns_sigpipe_code():
    expected = 128 + int(getattr(signal, "SIGPIPE", 13))
    with (
        patch("ssky.main.parse", return_value=("get", MagicMock())),
        patch("ssky.main.execute", side_effect=BrokenPipeError()),
        patch("ssky.main.setup"),
    ):
        assert main_mod.main() == expected


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
