from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from agent.companion import AICompanionAgent
from eeg.dummy_receiver import DummyEEGReceiver
from models.chat import ChatMessage

load_dotenv(Path(__file__).with_name(".env"))


class CompanionSession:
    def __init__(self) -> None:
        self._lock = Lock()
        self.state_source = DummyEEGReceiver()
        self.agent = AICompanionAgent()
        self.chat_history: list[ChatMessage] = []
        self._append_message(
            "assistant",
            "Hello. I am your neuroadaptive AI companion. Tell me how you are feeling, and I will adjust my tone to your current state.",
            state_label=self.state_source.get_state().label,
        )

    def _avatar_path_for_state(self, state_label: str | None) -> str | None:
        if state_label == "focused":
            return "/static/icons/icon_formal.png"
        if state_label == "distracted":
            return "/static/icons/icon_casual.png"
        return None

    def _append_message(self, role: str, content: str, state_label: str | None = None) -> ChatMessage:
        message = ChatMessage.create(
            role=role,
            content=content,
            state_label=state_label,
            avatar_path=self._avatar_path_for_state(state_label) if role == "assistant" else None,
        )
        self.chat_history.append(message)
        return message

    def get_state(self):
        with self._lock:
            return self.state_source.get_state()

    def set_state_label(self, label: str):
        with self._lock:
            return self.state_source.set_state(label)

    def get_history(self) -> list[dict[str, object]]:
        with self._lock:
            return [asdict(message) for message in self.chat_history]

    def get_meta(self) -> dict[str, object]:
        return self.agent.meta()

    def _prepare_turn(self, content: str):
        normalized = content.strip()
        if not normalized:
            raise ValueError("Message must not be empty.")

        with self._lock:
            state = self.state_source.get_state()
            user_message = self._append_message("user", normalized)
            history_snapshot = list(self.chat_history)
            return normalized, state, history_snapshot, user_message

    def _finalize_assistant_message(self, content: str) -> ChatMessage:
        with self._lock:
            state = self.state_source.get_state()
            return self._append_message("assistant", content, state_label=state.label)

    def send_user_message(self, content: str) -> dict[str, object]:
        normalized, state, history_snapshot, user_message = self._prepare_turn(content)
        assistant_text = self.agent.respond(
            user_message=normalized,
            user_state=state,
            history=history_snapshot,
        )
        assistant_message = self._finalize_assistant_message(assistant_text)
        return {
            "response": assistant_text,
            "user_message": asdict(user_message),
            "assistant_message": asdict(assistant_message),
            "state": asdict(state),
        }

    def stream_user_message(self, content: str):
        normalized, state, history_snapshot, user_message = self._prepare_turn(content)

        def generate():
            collected: list[str] = []
            yield _sse("meta", {"state": asdict(state), "user_message": asdict(user_message)})
            for chunk in self.agent.stream_response(
                user_message=normalized,
                user_state=state,
                history=history_snapshot,
            ):
                collected.append(chunk)
                yield _sse("delta", {"content": chunk})

            assistant_text = "".join(collected).strip()
            if not assistant_text:
                assistant_text = self.agent.respond(
                    user_message=normalized,
                    user_state=state,
                    history=history_snapshot,
                )
            assistant_message = self._finalize_assistant_message(assistant_text)
            yield _sse("done", {"assistant_message": asdict(assistant_message), "state": asdict(state)})

        return generate

    def reset(self) -> None:
        with self._lock:
            self.state_source = DummyEEGReceiver()
            self.chat_history = []
            self._append_message(
                "assistant",
                "The session has been reset. Start a new conversation whenever you are ready.",
                state_label=self.state_source.get_state().label,
            )


def _sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    session = CompanionSession()

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/state")
    def api_state():
        return jsonify(asdict(session.get_state()))

    @app.post("/api/state")
    def api_set_state():
        payload = request.get_json(silent=True) or {}
        label = payload.get("label", "")
        try:
            state = session.set_state_label(label)
        except ValueError as exc:
            return jsonify({"error": "invalid_state", "message": str(exc)}), 400
        return jsonify(asdict(state))

    @app.get("/api/meta")
    def api_meta():
        return jsonify(session.get_meta())

    @app.get("/api/chat/history")
    def api_chat_history():
        return jsonify({"messages": session.get_history()})

    @app.post("/api/chat")
    def api_chat():
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", ""))
        try:
            result = session.send_user_message(message)
        except ValueError as exc:
            return jsonify({"error": "invalid_message", "message": str(exc)}), 400
        return jsonify(result)

    @app.post("/api/chat/stream")
    def api_chat_stream():
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", ""))
        try:
            generator = session.stream_user_message(message)
        except ValueError as exc:
            return jsonify({"error": "invalid_message", "message": str(exc)}), 400

        return Response(
            stream_with_context(generator()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/reset")
    def api_reset():
        session.reset()
        return jsonify({"ok": True})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
