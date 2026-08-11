"""SIGPIPE / BrokenPipeError handling (#84)."""

from __future__ import annotations

import os
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
    """execute() must re-raise BrokenPipeError after redirecting stdout.

    Patch os.open/os.dup2 so the real pytest capture descriptors are not
    replaced with /dev/null (that would break the rest of the suite).
    """
    args = MagicMock()
    args.format = "id"
    args.output = None
    args.delimiter = " "

    def _raise(**_kwargs):
        raise BrokenPipeError()

    with (
        patch("ssky.main.import_module") as imp,
        patch("ssky.main.os.open", return_value=99) as open_mock,
        patch("ssky.main.os.dup2") as dup2_mock,
    ):
        mod = MagicMock()
        mod.get = _raise
        imp.return_value = mod
        with pytest.raises(BrokenPipeError):
            main_mod.execute("get", args)
        open_mock.assert_called_once_with(os.devnull, os.O_WRONLY)
        dup2_mock.assert_called_once()


def test_main_broken_pipe_returns_sigpipe_code():
    """main() returns 128+SIGPIPE without closing pytest's captured stdout.

    Patch dup2/open/close so teardown does not destroy capture FDs.
    """
    expected = 128 + int(getattr(signal, "SIGPIPE", 13))
    with (
        patch("ssky.main.parse", return_value=("get", MagicMock())),
        patch("ssky.main.execute", side_effect=BrokenPipeError()),
        patch("ssky.main.setup"),
        patch("ssky.main.os.open", return_value=99),
        patch("ssky.main.os.dup2"),
        patch.object(sys.stdout, "close"),
    ):
        assert main_mod.main() == expected


def test_pipe_to_early_consumer_has_empty_stderr():
    """Regression: early pipe close through ssky setup must exit 141, no stderr."""
    if not hasattr(signal, "SIGPIPE"):
        pytest.skip("SIGPIPE not available on this platform")

    # Drive real setup() (SIG_DFL + TextIOWrapper) and write past a typical
    # pipe buffer so the writer hits the closed reader after head-style exit.
    code = (
        "from ssky.main import setup\n"
        "import sys\n"
        "setup()\n"
        "chunk = ('x' * 4096) + '\\n'\n"
        "for _ in range(256):\n"
        "    sys.stdout.write(chunk)\n"
        "    sys.stdout.flush()\n"
    )
    env = os.environ.copy()
    # Ensure the subprocess can import the in-tree package the same way pytest does.
    src = os.path.join(os.path.dirname(__file__), os.pardir, "src")
    src = os.path.abspath(src)
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    assert proc.stdout is not None and proc.stderr is not None
    _ = proc.stdout.readline()
    proc.stdout.close()
    stderr = proc.stderr.read()
    proc.wait(timeout=10)
    # Popen reports -SIGPIPE when the child is killed by the signal; a shell
    # would surface that as 128 + SIGPIPE (typically 141).
    rc = proc.returncode
    if rc is not None and rc < 0:
        rc = 128 + (-rc)
    assert rc == 128 + int(signal.SIGPIPE), (
        f"expected 141, got {proc.returncode}; stderr={stderr!r}"
    )
    assert stderr == b"", f"stderr not empty: {stderr!r}"