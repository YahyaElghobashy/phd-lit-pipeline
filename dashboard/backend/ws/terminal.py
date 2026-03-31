"""
Dashboard — WebSocket Terminal Handler
Streams PTY output to xterm.js in the browser.

Architecture:
  - On connect, replays the entire output buffer (everything since last run started).
  - Subscribes to live output chunks via OutputBuffer.subscribe().
  - Client can connect/disconnect freely; output is never lost.
  - Control sentinels (\x00CTRL:...\x00) are parsed and converted to JSON messages.
"""
from __future__ import annotations

import asyncio
import json
import re

from fastapi import WebSocket, WebSocketDisconnect

from ..services.process_runner import active_process, get_output_buffer

# Regex to find control sentinels in output
_CTRL_RE = re.compile(rb"\x00CTRL:([A-Z]+):([^\x00]*)\x00")


def _parse_sentinels(data: bytes) -> tuple[bytes, list[dict]]:
    """
    Extract control sentinels from raw data.
    Returns (clean_data_without_sentinels, list_of_control_messages).
    """
    messages = []
    for m in _CTRL_RE.finditer(data):
        ctrl_type = m.group(1).decode()
        ctrl_payload = m.group(2).decode()
        if ctrl_type == "STARTED":
            messages.append({"type": "started", "command": ctrl_payload})
        elif ctrl_type == "EXIT":
            try:
                code = int(ctrl_payload)
            except ValueError:
                code = -1
            messages.append({"type": "exit", "code": code, "command": active_process.command or ""})
    # Remove sentinels from the data
    clean = _CTRL_RE.sub(b"", data)
    return clean, messages


async def terminal_ws(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for terminal streaming.

    Server → Client: raw bytes (ANSI terminal output) + JSON control messages
    Client → Server: JSON messages for resize events
    """
    await websocket.accept()

    buf = get_output_buffer()
    sub_queue: asyncio.Queue | None = None

    try:
        # 1. Replay buffered output
        replay = await buf.get_buffer()
        if replay:
            clean, ctrl_msgs = _parse_sentinels(replay)
            # Send the "started" message if present
            for msg in ctrl_msgs:
                if msg["type"] == "started":
                    await websocket.send_json(msg)
            # Send the clean terminal data
            if clean:
                await websocket.send_bytes(clean)
            # Send exit messages at the end
            for msg in ctrl_msgs:
                if msg["type"] == "exit":
                    await websocket.send_json(msg)

        # 2. Subscribe to live output
        sub_queue = buf.subscribe()

        # 3. Main loop: multiplex subscriber queue + client WebSocket
        while True:
            # Create tasks for both directions
            recv_task = asyncio.create_task(
                _ws_receive(websocket), name="ws_recv"
            )
            queue_task = asyncio.create_task(
                _queue_get(sub_queue), name="queue_get"
            )

            done, pending = await asyncio.wait(
                {recv_task, queue_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel whichever didn't finish
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

            for task in done:
                if task.cancelled():
                    continue
                exc = task.exception()
                if exc:
                    if isinstance(exc, WebSocketDisconnect):
                        return
                    if isinstance(exc, asyncio.TimeoutError):
                        continue  # Queue read timed out — just loop again
                    raise exc

                result = task.result()

                if task.get_name() == "queue_get":
                    # Data from the PTY reader
                    data: bytes = result
                    clean, ctrl_msgs = _parse_sentinels(data)
                    if clean:
                        await websocket.send_bytes(clean)
                    for msg in ctrl_msgs:
                        await websocket.send_json(msg)

                elif task.get_name() == "ws_recv":
                    # Message from the browser client
                    if result is None:
                        return  # Client disconnected
                    _handle_client_message(result)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if sub_queue is not None:
            buf.unsubscribe(sub_queue)


async def _ws_receive(ws: WebSocket) -> str | None:
    """Wait for a text message from the WebSocket client."""
    try:
        return await ws.receive_text()
    except WebSocketDisconnect:
        return None


async def _queue_get(q: asyncio.Queue) -> bytes:
    """Wait for the next chunk from the output buffer subscriber."""
    return await asyncio.wait_for(q.get(), timeout=2.0)


def _handle_client_message(raw: str) -> None:
    """Handle JSON messages from the terminal client."""
    try:
        msg = json.loads(raw)
        if msg.get("type") == "resize":
            cols = msg.get("cols", 160)
            rows = msg.get("rows", 50)
            active_process.resize(cols, rows)
    except (json.JSONDecodeError, KeyError):
        pass
