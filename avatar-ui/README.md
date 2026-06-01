# Neuroadaptive Avatar UI

React + Vite + TypeScript prototype for the VRM avatar companion interface.

This UI is intentionally thin: prompt generation, AI response generation, EEG acquisition, preprocessing, feature extraction, and concentration estimation are expected to run on the Python side. The React app receives avatar updates over WebSocket and updates the avatar, chat display, and text-to-speech output.

## Setup

Install dependencies from this directory:

```bash
cd avatar-ui
npm install
```

The active VRM file is:

```text
public/avatars/avatar.vrm
```

Replace that file if you want to use a different avatar.

## Run

Use two terminal windows: one for the React UI, and one for the Python WebSocket backend.

Terminal 1, start the React development server:

```bash
npm run dev
```

Vite usually opens on:

```text
http://127.0.0.1:5173/
```

To use the same port as the current verification script and local browser session:

```bash
npm run dev -- --host 127.0.0.1 --port 5174
```

Then open:

```text
http://127.0.0.1:5174/
```

Terminal 2, start the local Python WebSocket backend:

```bash
npm run ws
```

This runs:

```bash
python3 backend/avatar_ws_server.py
```

The backend always provides the WebSocket channel used for avatar updates and future AI replies. It also tries to connect to a Muse EEG LSL stream. When Muse is connected, concentration state updates come from the realtime EEG estimator. When Muse is not connected, the React UI stays in manual mode and the `集中` / `散漫` buttons are used for state switching.

To run the WebSocket backend without trying to connect to Muse:

```bash
npm run ws -- --no-muse
```

The backend terminal also accepts `say` commands for sending a reply message over the WebSocket:

```text
say 任意の返答テキストを読み上げます。
```

## OpenAI AI Replies And TTS

When WebSocket is connected, chat input is sent to the Python backend as `user_message`. The backend uses OpenAI for:

- Text generation: `OPENAI_TEXT_MODEL`, default `gpt-4o-mini`
- Speech generation: `OPENAI_TTS_MODEL`, default `gpt-4o-mini-tts`
- Voice: `OPENAI_TTS_VOICE`, default `alloy`

Install backend dependencies in the Python environment used by `npm run ws`:

```bash
pip install -r backend/requirements.txt
```

Set `OPENAI_API_KEY` in your shell or in one of these `.env` locations:

```text
avatar-ui/backend/.env
avatar-ui/.env
../.env
```

The backend returns `replyText` and, when TTS succeeds, base64 MP3 audio in `audio.data`. The React app plays that OpenAI-generated audio and uses the existing lip-sync while it is playing.

The voice heard in the UI is AI-generated.

## WebSocket Input

By default, the UI connects to:

```text
ws://127.0.0.1:8765
```

Override this with a Vite environment variable:

```bash
VITE_AVATAR_WS_URL=ws://127.0.0.1:9000 npm run dev
```

The Python side should send JSON messages shaped like this:

```json
{
  "type": "avatar_update",
  "state": "focused",
  "concentration": 0.82,
  "replyText": "了解しました。要点を整理して進めましょう。",
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

Supported `state` values are only:

```text
focused
distracted
```

`concentration` is displayed in the sidebar. Values are clamped to `0.0` through `1.0`.

`replyText` is optional. When present and non-empty, it is appended to the chat as an assistant message. When `audio.data` is present, the React app plays that backend-generated OpenAI TTS audio.

`source` indicates where the concentration state came from. The React UI only applies automatic state changes from WebSocket messages when `source` is `muse` and `muse.status` is `connected`.

`muse.status` is displayed separately from the WebSocket status. Expected values are `searching`, `connected`, `error`, and `unavailable`. Muse does not use `disconnected`; while no LSL stream is available, the backend keeps searching.

`style` is optional:

- `expression`: applied to the VRM expression manager when that expression exists on the model
- `speechRate`: displayed as the current speech style hint
- `pitch`: displayed as the current speech style hint

## Behavior

- `focused` uses the existing focused expression path and focused TTS defaults.
- `distracted` uses the existing distracted expression path and distracted TTS defaults.
- While TTS is active, `isSpeaking` is true and the simple lip-sync opens and closes the VRM mouth expression periodically.
- When TTS ends or is stopped, the mouth expression is closed.
- WebSocket status is shown as `connected`, `disconnected`, or `error`.
- Muse status is shown separately.
- If the WebSocket disconnects, the UI automatically retries the connection.
- When Muse is connected, realtime EEG estimation drives the avatar state.
- When Muse is not connected, the manual `集中` / `散漫` buttons drive the avatar state.

## Verification

Build the app:

```bash
npm run build
```

Run the avatar canvas verification:

```bash
npm run verify:avatar
```

`verify:avatar` expects the app to be reachable at:

```text
http://127.0.0.1:5174/
```

Start the dev server on that port before running it:

```bash
npm run dev -- --host 127.0.0.1 --port 5174
```

If the Python WebSocket server is not running, browser console logs may show connection refused errors for `ws://127.0.0.1:8765`. That is expected during UI-only verification.

## Python Backend

The local backend lives in:

```text
backend/avatar_ws_server.py
```

The WebSocket implementation itself is dependency-free and uses only the Python standard library. Muse/LSL estimation uses optional Python packages such as `pylsl`, `numpy`, and `scipy` when they are installed. If those packages or the Muse LSL stream are unavailable, the backend reports Muse as disconnected and the UI remains manually switchable.

## Production Build

```bash
npm run build
npm run preview
```

The build may warn that the Three.js/VRM bundle is larger than 500 kB. That is currently expected; a future improvement is to dynamically import `AvatarViewer`.
