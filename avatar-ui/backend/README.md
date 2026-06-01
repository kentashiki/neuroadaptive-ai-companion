# Avatar WebSocket Backend

This directory contains the Python WebSocket backend for the avatar UI.

Run it from `avatar-ui/`:

```bash
python3 backend/avatar_ws_server.py
```

It listens on:

```text
ws://127.0.0.1:8765
```

The server sends JSON messages in the shape expected by the React app:

```json
{
  "type": "avatar_update",
  "state": "focused",
  "concentration": 0.84,
  "replyText": "集中状態です。要点を整理して、次の作業を短く確認しましょう。",
  "source": "muse",
  "style": {
    "expression": "neutral",
    "speechRate": 0.95,
    "pitch": 0.9
  },
  "muse": {
    "status": "connected",
    "phase": "estimating",
    "message": "Estimating concentration from Muse EEG."
  }
}
```

Supported states are `focused` and `distracted`.

## OpenAI

Chat messages from the React UI are sent to this backend as `user_message`. The backend generates the reply text with OpenAI and synthesizes speech with `gpt-4o-mini-tts` using the `alloy` voice.

Environment variables:

```text
OPENAI_API_KEY=...
OPENAI_TEXT_MODEL=gpt-4o-mini
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=alloy
```

Install dependencies:

```bash
pip install -r backend/requirements.txt
```

The backend also reads `.env` from `backend/.env`, `../.env`, or the repository root `.env`.

## Muse Behavior

By default the backend keeps searching for a Muse EEG stream exposed through LSL. If no EEG stream is found, Muse remains in `searching`. If `pylsl`, `numpy`, or `scipy` are unavailable, Muse is reported as `unavailable`. WebSocket stays available in both cases.

Run without Muse detection:

```bash
python3 backend/avatar_ws_server.py --no-muse
```

When Muse is connected, `source: "muse"` updates drive the React avatar state. When Muse is not connected, React uses its own manual `集中` / `散漫` buttons for state switching.

## Interactive Commands

Without `--no-stdin`, the server accepts commands from the terminal:

```text
say 任意の返答テキストだけを送ります。
```
