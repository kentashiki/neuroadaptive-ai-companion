from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import signal
import struct
from dataclasses import asdict, dataclass
from typing import Any

from agent import AICompanionAgent
from eeg import MuseFocusReceiver
from models import ChatMessage, UserState


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
VALID_STATES = {"focused", "distracted"}


@dataclass
class AvatarStyle:
    expression: str
    speechRate: float
    pitch: float


@dataclass
class AvatarUpdate:
    type: str
    state: str
    concentration: float
    replyText: str
    style: AvatarStyle
    source: str
    muse: dict[str, Any]
    audio: dict[str, str] | None = None


STATE_PRESETS = {
    "focused": {
        "concentration": 0.84,
        "style": AvatarStyle(expression="neutral", speechRate=0.95, pitch=0.9),
    },
    "distracted": {
        "concentration": 0.32,
        "style": AvatarStyle(expression="happy", speechRate=1.05, pitch=1.15),
    },
}


class AvatarUpdateHub:
    def __init__(self, muse_receiver: MuseFocusReceiver | None = None) -> None:
        self._clients: set[asyncio.StreamWriter] = set()
        self._state = UserState.create(
            attention=float(STATE_PRESETS["distracted"]["concentration"]),
            label="distracted",
        )
        self._muse_receiver = muse_receiver
        self._agent = AICompanionAgent()
        self._chat_history: list[ChatMessage] = []

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def add_client(self, writer: asyncio.StreamWriter) -> None:
        self._clients.add(writer)

    def remove_client(self, writer: asyncio.StreamWriter) -> None:
        self._clients.discard(writer)

    def get_muse_status(self) -> dict[str, Any]:
        if self._muse_receiver is None:
            return {
                "status": "unavailable",
                "phase": "disabled",
                "message": "Muse receiver is disabled.",
            }
        return self._muse_receiver.snapshot()["muse"]

    def get_effective_state(self) -> UserState:
        muse_status = self.get_muse_status()
        if self._muse_receiver is not None and muse_status.get("status") == "connected":
            state = self._muse_receiver.snapshot()["state"]
            if isinstance(state, UserState) and state.label in VALID_STATES:
                self._state = state
        return self._state

    def set_manual_state(self, state: str) -> UserState:
        normalized = state.strip().lower()
        if normalized not in VALID_STATES:
            valid = ", ".join(sorted(VALID_STATES))
            raise ValueError(f"Unsupported state '{state}'. Valid states: {valid}.")

        if self.get_muse_status().get("status") == "connected":
            return self.get_effective_state()

        self._state = UserState.create(
            attention=float(STATE_PRESETS[normalized]["concentration"]),
            label=normalized,
        )
        return self._state

    def create_update(
        self,
        *,
        reply_text: str = "",
        source: str = "status",
        audio: dict[str, str] | None = None,
    ) -> AvatarUpdate:
        state = self.get_effective_state()
        preset = STATE_PRESETS[state.label]
        return AvatarUpdate(
            type="avatar_update",
            state=state.label,
            concentration=state.attention,
            replyText=reply_text,
            style=preset["style"],
            source=source,
            muse=self.get_muse_status(),
            audio=audio,
        )

    def create_ai_reply_update(self, user_text: str) -> AvatarUpdate:
        normalized = user_text.strip()
        if not normalized:
            return self.create_update(source="ai")

        state = self.get_effective_state()
        user_message = ChatMessage.create(role="user", content=normalized)
        self._chat_history.append(user_message)
        reply = self._agent.respond(
            user_message=normalized,
            user_state=state,
            history=list(self._chat_history),
        )
        self._chat_history.append(ChatMessage.create(role="assistant", content=reply, state_label=state.label))
        audio_bytes = self._agent.synthesize_speech(text=reply, state=state)
        audio = None
        if audio_bytes:
            audio = {
                "mimeType": "audio/mpeg",
                "data": base64.b64encode(audio_bytes).decode("ascii"),
            }
        return self.create_update(reply_text=reply, source="ai", audio=audio)

    async def broadcast(self, update: AvatarUpdate) -> None:
        if not self._clients:
            return

        payload = json.dumps(asdict(update), ensure_ascii=False)
        frame = _encode_text_frame(payload)
        stale_clients: list[asyncio.StreamWriter] = []

        for writer in self._clients:
            try:
                writer.write(frame)
                await writer.drain()
            except (ConnectionError, OSError):
                stale_clients.append(writer)

        for writer in stale_clients:
            self.remove_client(writer)
            writer.close()


def _encode_text_frame(message: str) -> bytes:
    payload = message.encode("utf-8")
    length = len(payload)
    header = bytearray([0x81])

    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", length))

    return bytes(header) + payload


def _decode_client_frame(data: bytes) -> str | None:
    if len(data) < 2:
        return None

    opcode = data[0] & 0x0F
    if opcode == 0x8:
        return None

    masked = bool(data[1] & 0x80)
    payload_length = data[1] & 0x7F
    offset = 2

    if payload_length == 126:
        payload_length = struct.unpack("!H", data[offset : offset + 2])[0]
        offset += 2
    elif payload_length == 127:
        payload_length = struct.unpack("!Q", data[offset : offset + 8])[0]
        offset += 8

    mask = data[offset : offset + 4] if masked else b""
    offset += 4 if masked else 0
    payload = data[offset : offset + payload_length]

    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))

    if opcode != 0x1:
        return None

    return payload.decode("utf-8", errors="replace")


async def _read_http_headers(reader: asyncio.StreamReader) -> dict[str, str]:
    raw = await reader.readuntil(b"\r\n\r\n")
    lines = raw.decode("utf-8", errors="replace").split("\r\n")
    headers: dict[str, str] = {}

    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    return headers


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, hub: AvatarUpdateHub) -> None:
    peer = writer.get_extra_info("peername")
    try:
        headers = await _read_http_headers(reader)
        key = headers.get("sec-websocket-key")
        if not key:
            writer.close()
            await writer.wait_closed()
            return

        accept = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            "\r\n"
        )
        writer.write(response.encode("ascii"))
        await writer.drain()

        hub.add_client(writer)
        print(f"[connect] {peer} clients={hub.client_count}", flush=True)
        await hub.broadcast(hub.create_update(source="status"))

        while not reader.at_eof():
            data = await reader.read(4096)
            if not data:
                break
            message = _decode_client_frame(data)
            if message:
                await _handle_client_message(message, hub)
    except (asyncio.IncompleteReadError, ConnectionError, OSError):
        pass
    finally:
        hub.remove_client(writer)
        writer.close()
        print(f"[disconnect] {peer} clients={hub.client_count}", flush=True)


async def _handle_client_message(message: str, hub: AvatarUpdateHub) -> None:
    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return

    if not isinstance(payload, dict):
        return

    message_type = payload.get("type")

    if message_type == "manual_state":
        state = payload.get("state")
        if isinstance(state, str) and state in VALID_STATES:
            hub.set_manual_state(state)
            await hub.broadcast(hub.create_update(source="manual"))
            print(f"[manual] state={state}", flush=True)
        return

    if message_type == "user_message":
        text = payload.get("text")
        if isinstance(text, str):
            update = await asyncio.to_thread(hub.create_ai_reply_update, text)
            await hub.broadcast(update)
            print(f"[ai] state={update.state} reply_len={len(update.replyText)}", flush=True)
        return

    if message_type == "ai_reply":
        reply_text = payload.get("replyText")
        if isinstance(reply_text, str):
            await hub.broadcast(hub.create_update(reply_text=reply_text, source="ai"))


async def _status_loop(hub: AvatarUpdateHub, interval: float) -> None:
    last_payload = ""
    while True:
        update = hub.create_update(source="muse" if hub.get_muse_status().get("status") == "connected" else "status")
        payload = json.dumps(asdict(update), ensure_ascii=False, sort_keys=True)
        if payload != last_payload:
            await hub.broadcast(update)
            last_payload = payload
            muse_status = update.muse.get("status", "unknown")
            muse_phase = update.muse.get("phase", "unknown")
            print(
                f"[status] muse={muse_status}/{muse_phase} "
                f"state={update.state} concentration={update.concentration:.2f} clients={hub.client_count}",
                flush=True,
            )
        await asyncio.sleep(interval)


async def _stdin_loop(hub: AvatarUpdateHub) -> None:
    help_text = "stdin commands: say <reply>, blank line to show this help. Use the UI buttons for manual state switching."
    print(help_text, flush=True)

    while True:
        line = await asyncio.to_thread(input, "> ")
        command = line.strip()
        if not command:
            print(help_text, flush=True)
            continue

        head, _, tail = command.partition(" ")
        if head.lower() != "say":
            print(f"Unknown command: {head}", flush=True)
            continue

        await hub.broadcast(hub.create_update(reply_text=tail.strip(), source="ai"))
        print(f"[sent] reply_len={len(tail.strip())} clients={hub.client_count}", flush=True)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Avatar UI WebSocket update server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-muse", action="store_true", help="disable Muse/LSL EEG receiver")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between status broadcasts")
    parser.add_argument("--no-stdin", action="store_true", help="disable interactive stdin commands")
    args = parser.parse_args()

    muse_receiver = None if args.no_muse else MuseFocusReceiver()
    hub = AvatarUpdateHub(muse_receiver)
    server = await asyncio.start_server(lambda r, w: _handle_client(r, w, hub), args.host, args.port)
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    print(f"Avatar WebSocket server listening on {sockets}", flush=True)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signame in ("SIGINT", "SIGTERM"):
        if hasattr(signal, signame):
            loop.add_signal_handler(getattr(signal, signame), stop_event.set)

    tasks: list[asyncio.Task[Any]] = [asyncio.create_task(_status_loop(hub, args.interval))]
    if not args.no_stdin:
        tasks.append(asyncio.create_task(_stdin_loop(hub)))

    async with server:
        server_task = asyncio.create_task(server.serve_forever())
        await stop_event.wait()
        server_task.cancel()

    for task in tasks:
        task.cancel()
    if muse_receiver is not None:
        muse_receiver.stop()


if __name__ == "__main__":
    asyncio.run(main())
