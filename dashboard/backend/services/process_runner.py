"""
Dashboard — Process Runner Service
Manages subprocess execution with PTY for terminal streaming via WebSocket.

Architecture:
  - A background asyncio task (_pty_reader_loop) continuously reads from the
    PTY master fd and writes to an OutputBuffer.
  - WebSocket clients subscribe to the buffer for live streaming.
  - When no WebSocket is connected, the reader loop keeps draining the PTY
    so the pipeline process never blocks on a full buffer.
  - On reconnect, the buffer contents are replayed to the client.
"""
from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path
from typing import Optional

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Discover the right python3 — prefer the one running the dashboard server,
# then the one that has the pipeline dependencies installed.
def _find_python() -> str:
    """Return the best python3 path for running pipeline scripts."""
    # 1. The python that is running this server (has fastapi, etc.)
    server_python = sys.executable

    # 2. Check if the pipeline's own python 3.11 exists (known working path)
    known_paths = [
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11",
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
    ]
    for p in known_paths:
        if os.path.isfile(p):
            return p

    # 3. Fall back to the server's python
    return server_python

PYTHON_BIN = _find_python()

# Command templates
COMMANDS = {
    "extraction": {
        "base": [PYTHON_BIN, "main.py"],
        "flags": {
            "dry_run": "--dry-run",
            "paper": "--paper",
            "skip_sheets": "--skip-sheets",
            "reprocess": "--reprocess",
            "backfill_summary": "--backfill-summary",
            "backfill_abstracts": "--backfill-abstracts",
        },
    },
    "gap_analysis": {
        "base": [PYTHON_BIN, "gap_coverage_analyzer.py"],
        "flags": {
            "dry_run": "--dry-run",
            "paper": "--paper",
            "paper_id": "--paper-id",
        },
    },
    "discovery": {
        "base": [PYTHON_BIN, "discover.py", "search"],
        "flags": {
            "query": "--query",
            "dry_run": "--dry-run",
            "max_results": "--max-results",
        },
    },
    "discovery_full": {
        "base": [PYTHON_BIN, "discover.py", "--run"],
        "flags": {
            "gap_limit": "--gap-limit",
            "dry_run": "--dry-run",
            "min_citations": "--min-citations",
            "skip_extraction": "--skip-extraction",
        },
    },
    "discovery_analyze": {
        "base": [PYTHON_BIN, "discover.py", "--novelty"],
        "flags": {
            "dry_run": "--dry-run",
        },
    },
}


# ── Output Buffer ──────────────────────────────────────────────────────────
# Decouples PTY reading from WebSocket connections.  The background reader
# always drains the PTY; subscribers (WebSockets) get live chunks and can
# also replay everything buffered so far on (re)connect.

MAX_BUFFER_SIZE = 256 * 1024  # 256 KB circular buffer


class OutputBuffer:
    """Thread-safe circular byte buffer with pub/sub for live streaming."""

    def __init__(self, max_size: int = MAX_BUFFER_SIZE):
        self._max_size = max_size
        self._buffer = bytearray()
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def write(self, data: bytes) -> None:
        """Append data to buffer and push to all subscribers."""
        async with self._lock:
            self._buffer.extend(data)
            # Trim from the front if over max size (circular)
            if len(self._buffer) > self._max_size:
                excess = len(self._buffer) - self._max_size
                del self._buffer[:excess]

        # Fan out to all live subscribers (non-blocking)
        dead: list[asyncio.Queue] = []
        for q in self._subscribers:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                # Subscriber is slow — drop for this chunk
                pass
            except Exception:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    def subscribe(self) -> asyncio.Queue:
        """Create a new subscriber queue for live chunks."""
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def get_buffer(self) -> bytes:
        """Return all buffered output for replay."""
        async with self._lock:
            return bytes(self._buffer)

    async def clear(self) -> None:
        async with self._lock:
            self._buffer.clear()


# Module-level singleton
_output_buffer = OutputBuffer()


def get_output_buffer() -> OutputBuffer:
    """Public accessor for the output buffer (used by terminal.py)."""
    return _output_buffer


# ── Background PTY Reader ─────────────────────────────────────────────────

_reader_task: Optional[asyncio.Task] = None


async def _pty_reader_loop(master_fd: int, process: subprocess.Popen) -> None:
    """
    Background task that continuously reads from the PTY master fd and
    writes to the output buffer.  Runs until the process exits and the
    PTY is drained.
    """
    loop = asyncio.get_event_loop()
    try:
        while True:
            # Check if data is available (non-blocking, 0.1s timeout)
            try:
                readable, _, _ = await loop.run_in_executor(
                    None, lambda: select.select([master_fd], [], [], 0.1)
                )
            except (OSError, ValueError):
                break

            if readable:
                try:
                    data = await loop.run_in_executor(
                        None, lambda: os.read(master_fd, 4096)
                    )
                except OSError:
                    break
                if not data:
                    break  # EOF
                await _output_buffer.write(data)
            else:
                # No data — check if process exited
                if process.poll() is not None:
                    # Drain any remaining bytes
                    try:
                        while True:
                            r, _, _ = select.select([master_fd], [], [], 0.05)
                            if not r:
                                break
                            data = os.read(master_fd, 4096)
                            if not data:
                                break
                            await _output_buffer.write(data)
                    except OSError:
                        pass
                    break
    finally:
        # Send exit sentinel
        exit_code = process.returncode if process.returncode is not None else process.wait()
        sentinel = f"\x00CTRL:EXIT:{exit_code}\x00".encode()
        await _output_buffer.write(sentinel)

        # Cleanup the active process
        active_process.cleanup()


# ── Active Process ─────────────────────────────────────────────────────────

class ActiveProcess:
    """Tracks the currently running pipeline process."""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.command: Optional[str] = None
        self.started_at: Optional[float] = None
        self.master_fd: Optional[int] = None
        self._lock = asyncio.Lock()
        # Listeners waiting to be notified when a process starts
        self._start_listeners: list[asyncio.Queue] = []

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0
        return time.time() - self.started_at

    def status(self) -> dict:
        return {
            "is_running": self.is_running,
            "pid": self.pid,
            "command": self.command,
            "started_at": self.started_at,
            "elapsed_seconds": round(self.elapsed, 1) if self.is_running else 0,
        }

    def add_start_listener(self, q: asyncio.Queue) -> None:
        self._start_listeners.append(q)

    def remove_start_listener(self, q: asyncio.Queue) -> None:
        try:
            self._start_listeners.remove(q)
        except ValueError:
            pass

    async def start(self, command_type: str, flags: dict) -> dict:
        """Start a new pipeline process. Returns status or error."""
        async with self._lock:
            if self.is_running:
                return {"error": "A process is already running", "status": self.status()}

            cmd_config = COMMANDS.get(command_type)
            if not cmd_config:
                return {"error": f"Unknown command: {command_type}"}

            # Build CLI command
            cmd = list(cmd_config["base"])
            flag_map = cmd_config["flags"]

            for key, value in flags.items():
                if key not in flag_map:
                    continue
                flag = flag_map[key]
                if isinstance(value, bool):
                    if value:
                        cmd.append(flag)
                elif value is not None and str(value).strip():
                    cmd.append(flag)
                    cmd.append(str(value))

            # Open PTY
            master_fd, slave_fd = pty.openpty()

            # Set terminal size
            winsize = struct.pack("HHHH", 50, 160, 0, 0)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

            # Set TERM env var so Rich knows it's a terminal
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["FORCE_COLOR"] = "1"
            env["COLUMNS"] = "160"
            env["LINES"] = "50"
            # Ensure PYTHONUNBUFFERED so output streams immediately
            env["PYTHONUNBUFFERED"] = "1"

            proc = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=str(PIPELINE_DIR),
                env=env,
                close_fds=True,
            )

            # Close slave fd in parent
            os.close(slave_fd)

            self.process = proc
            self.pid = proc.pid
            self.command = " ".join(cmd)
            self.started_at = time.time()
            self.master_fd = master_fd

            # Clear output buffer and write started sentinel
            await _output_buffer.clear()
            started_sentinel = f"\x00CTRL:STARTED:{self.command}\x00".encode()
            await _output_buffer.write(started_sentinel)

            # Launch background PTY reader (decoupled from WebSocket)
            global _reader_task
            _reader_task = asyncio.create_task(
                _pty_reader_loop(master_fd, proc)
            )

            # Notify any WebSocket listeners that a process started
            for q in self._start_listeners:
                try:
                    q.put_nowait({"type": "started", "command": self.command, "pid": proc.pid})
                except asyncio.QueueFull:
                    pass

            return {"pid": proc.pid, "command": self.command}

    async def cancel(self) -> dict:
        """Send SIGINT to the running process (triggers graceful shutdown)."""
        async with self._lock:
            if not self.is_running:
                return {"error": "No process running"}
            self.process.send_signal(signal.SIGINT)
            return {"message": "SIGINT sent", "pid": self.pid}

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY window."""
        if self.master_fd is not None:
            try:
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except OSError:
                pass

    def cleanup(self) -> None:
        """Clean up after process exits."""
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
        self.process = None
        self.pid = None
        # Keep self.command for reference in exit messages
        self.started_at = None
        self.master_fd = None


# Singleton active process
active_process = ActiveProcess()


async def read_pty_output(master_fd: int) -> bytes | None:
    """Non-blocking read from PTY master fd. (Legacy — kept for compatibility.)"""
    loop = asyncio.get_event_loop()
    try:
        readable, _, _ = await loop.run_in_executor(
            None, lambda: select.select([master_fd], [], [], 0.1)
        )
        if readable:
            data = await loop.run_in_executor(None, lambda: os.read(master_fd, 4096))
            return data if data else None
    except OSError:
        return None
    return b""
