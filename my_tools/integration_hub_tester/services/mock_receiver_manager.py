"""MockReceiverManager — spawns and tracks mock receiver processes.

Starts either the MLLP mock receiver (hl7_mock_receiver) or the HTTP/SOAP mock
receiver (http_mock_receiver) in a new visible terminal window so developers can
observe live output while running the tester GUI.

Usage::

    manager = MockReceiverManager()
    manager.start("mllp")   # or "soap"
    # ... run tests ...
    manager.stop()           # also called automatically on app close

Windows note:
    CREATE_NEW_CONSOLE opens a separate cmd/PowerShell window.  The child
    process is independent but its PID is tracked so we can terminate it cleanly.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Absolute paths to each mock receiver's root directory.
_REPO_ROOT = Path(__file__).resolve().parents[3]  # services/ → integration_hub_tester/ → my_tools/ → repo root

_RECEIVER_DIRS: dict[str, Path] = {
    "mllp": _REPO_ROOT / "mock_receivers" / "hl7_mock_receiver",
    "soap": _REPO_ROOT / "mock_receivers" / "http_mock_receiver",
}

# The module entry point for each receiver type.
_RECEIVER_MODULES: dict[str, str] = {
    "mllp": "hl7_mock_receiver.application",
    "soap": "http_mock_receiver",
}

# Human-readable labels used in status messages.
_RECEIVER_LABELS: dict[str, str] = {
    "mllp": "MLLP Mock Receiver  (port 2576)",
    "soap": "SOAP Mock Receiver  (port 8080)",
}


class MockReceiverManager:
    """Manages a single mock receiver subprocess.

    Only one receiver can run at a time.  Calling ``start()`` when a process is
    already running is a no-op (the caller should check ``is_running`` first).
    """

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None
        self._mode: str | None = None

    # ── Public interface ────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """True when the tracked process is alive."""
        if self._process is None:
            return False
        return self._process.poll() is None

    @property
    def mode(self) -> str | None:
        """The currently running mode ("mllp" or "soap"), or None."""
        return self._mode if self.is_running else None

    @property
    def label(self) -> str:
        """Human-readable status string for the UI indicator."""
        if self.is_running and self._mode:
            return f"● Running — {_RECEIVER_LABELS[self._mode]}"
        return "● Stopped"

    def start(self, mode: str) -> tuple[bool, str]:
        """Start the specified mock receiver in a new console window.

        Args:
            mode: "mllp" or "soap"

        Returns:
            (success, message) — success is False when the receiver directory
            does not exist (service not yet built) or the process fails to start.
        """
        if mode not in _RECEIVER_DIRS:
            return False, f"Unknown mode '{mode}' — expected 'mllp' or 'soap'."

        if self.is_running:
            return False, f"A mock receiver is already running ({self.label}).  Stop it first."

        cwd = _RECEIVER_DIRS[mode]
        if not cwd.exists():
            return False, (
                f"Directory not found: {cwd}\n"
                f"The {_RECEIVER_LABELS[mode]} service has not been built yet."
            )

        module = _RECEIVER_MODULES[mode]
        cmd = _build_command(module)

        logger.info("Starting %s in %s", _RECEIVER_LABELS[mode], cwd)

        try:
            kwargs: dict = {
                "cwd": str(cwd),
                "env": {**os.environ},
            }

            if sys.platform == "win32":
                # Open a visible console window so the developer can see live output.
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            else:
                # On Linux/macOS open a new terminal emulator if available.
                cmd = _wrap_terminal(cmd)

            self._process = subprocess.Popen(cmd, **kwargs)
            self._mode = mode
            logger.info("%s started — PID %s", _RECEIVER_LABELS[mode], self._process.pid)
            return True, f"Started {_RECEIVER_LABELS[mode]}  (PID {self._process.pid})"

        except FileNotFoundError as exc:
            missing = getattr(exc, "filename", None) or str(exc)
            return False, (
                f"Could not start {_RECEIVER_LABELS[mode]} — missing executable: {missing}.  "
                "Ensure uv is installed and on your PATH (and a terminal emulator is available on Linux/macOS)."
            )
        except OSError as exc:
            return False, f"Failed to start {_RECEIVER_LABELS[mode]}: {exc}"

    def stop(self) -> tuple[bool, str]:
        """Terminate the running mock receiver process.

        Returns:
            (success, message)
        """
        if not self.is_running or self._process is None:
            self._mode = None
            return True, "No mock receiver is running."

        label = _RECEIVER_LABELS.get(self._mode or "", "Mock receiver")
        pid = self._process.pid
        logger.info("Stopping %s (PID %s)...", label, pid)

        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Process did not terminate — killing PID %s", pid)
                self._process.kill()
                self._process.wait(timeout=3)
        except OSError as exc:
            logger.warning("Error stopping process %s: %s", pid, exc)

        self._process = None
        self._mode = None
        logger.info("%s stopped.", label)
        return True, f"{label} stopped."


# ── Helpers ─────────────────────────────────────────────────────────────────

def _build_command(module: str) -> list[str]:
    """Build the uv run command for the given module entry point."""
    return ["uv", "run", "python", "-m", module]


def _wrap_terminal(cmd: list[str]) -> list[str]:
    """Wrap a command to open in a new terminal on Linux/macOS (best-effort).

    Probes each candidate terminal with ``shutil.which`` before using it so
    we don't attempt to launch an emulator that isn't on PATH.  Falls back to
    running in the current process if none are found.
    """
    import shutil

    for terminal, args in (("gnome-terminal", ["--"]), ("xterm", ["-e"]), ("konsole", ["-e"])):
        if shutil.which(terminal):
            return [terminal, *args, *cmd]

    # Fallback: run in the current process if no terminal emulator is available.
    return cmd
