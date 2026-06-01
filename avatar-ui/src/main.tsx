import React from "react";
import type { Root } from "react-dom/client";
import ReactDOM from "react-dom/client";
import {
  Activity,
  Brain,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  RotateCcw,
  Send,
  SlidersHorizontal,
  VolumeX,
} from "lucide-react";
import { AvatarViewer } from "./components/AvatarViewer";
import "./styles.css";

type ConcentrationState = "focused" | "distracted";
type WebSocketStatus = "connected" | "disconnected" | "error";
type MuseConnectionStatus = "connected" | "searching" | "error" | "unavailable" | "unknown";
type Role = "assistant" | "user";

type ChatMessage = {
  id: number;
  role: Role;
  content: string;
  timestamp: Date;
  state?: ConcentrationState;
};

type AvatarUpdateMessage = {
  type: "avatar_update";
  state: ConcentrationState;
  concentration: number;
  source?: "muse" | "manual" | "status" | "ai";
  replyText?: string;
  style?: {
    expression?: string;
    speechRate?: number;
    pitch?: number;
  };
  muse?: {
    status?: MuseConnectionStatus;
    phase?: string;
    message?: string;
  };
  audio?: {
    mimeType?: string;
    data?: string;
  };
};

type SpeechSettings = {
  rate: number;
  pitch: number;
};

const AVATAR_WS_URL = import.meta.env.VITE_AVATAR_WS_URL ?? "ws://127.0.0.1:8765";
const DEFAULT_MUSE_STATUS: Required<NonNullable<AvatarUpdateMessage["muse"]>> = {
  status: "unknown",
  phase: "unknown",
  message: "Muse status has not been received yet.",
};

const stateCopy: Record<ConcentrationState, { label: string; style: string; caption: string; attention: number }> = {
  focused: {
    label: "集中",
    style: "丁寧で簡潔、構造的",
    caption: "情報密度を高め、短く整理して返答します。",
    attention: 0.82,
  },
  distracted: {
    label: "散漫",
    style: "親しみやすく、会話的",
    caption: "安心感のある言葉で、ゆっくり伴走します。",
    attention: 0.38,
  },
};

const initialMessages: ChatMessage[] = [
  {
    id: 1,
    role: "assistant",
    content: "こんにちは。Python側から届く avatar_update を待機しています。",
    timestamp: new Date(),
    state: "distracted",
  },
];

const SPEECH_SETTINGS_BY_STATE: Record<ConcentrationState, { rate: number; pitch: number }> = {
  focused: {
    rate: 0.95,
    pitch: 0.9,
  },
  distracted: {
    rate: 1.05,
    pitch: 1.15,
  },
};

function isConcentrationState(value: unknown): value is ConcentrationState {
  return value === "focused" || value === "distracted";
}

function clampConcentration(value: number) {
  return Math.min(1, Math.max(0, value));
}

function normalizeAvatarUpdate(value: unknown): AvatarUpdateMessage | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const candidate = value as Partial<AvatarUpdateMessage>;
  if (candidate.type !== "avatar_update" || !isConcentrationState(candidate.state)) {
    return null;
  }

  return {
    type: "avatar_update",
    state: candidate.state,
    concentration: typeof candidate.concentration === "number" ? clampConcentration(candidate.concentration) : stateCopy[candidate.state].attention,
    source: candidate.source,
    replyText: typeof candidate.replyText === "string" ? candidate.replyText : undefined,
    style: {
      expression: typeof candidate.style?.expression === "string" ? candidate.style.expression : undefined,
      speechRate: typeof candidate.style?.speechRate === "number" ? candidate.style.speechRate : undefined,
      pitch: typeof candidate.style?.pitch === "number" ? candidate.style.pitch : undefined,
    },
    muse: {
      status: candidate.muse?.status,
      phase: typeof candidate.muse?.phase === "string" ? candidate.muse.phase : undefined,
      message: typeof candidate.muse?.message === "string" ? candidate.muse.message : undefined,
    },
    audio: {
      mimeType: typeof candidate.audio?.mimeType === "string" ? candidate.audio.mimeType : undefined,
      data: typeof candidate.audio?.data === "string" ? candidate.audio.data : undefined,
    },
  };
}

function formatTime(date: Date) {
  return date.toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function App() {
  const [concentrationState, setConcentrationState] = React.useState<ConcentrationState>("distracted");
  const [concentration, setConcentration] = React.useState(stateCopy.distracted.attention);
  const [expressionOverride, setExpressionOverride] = React.useState<string | undefined>();
  const [speechSettings, setSpeechSettings] = React.useState<SpeechSettings | undefined>();
  const [webSocketStatus, setWebSocketStatus] = React.useState<WebSocketStatus>("disconnected");
  const [museStatus, setMuseStatus] = React.useState(DEFAULT_MUSE_STATUS);
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(true);
  const [isSpeaking, setIsSpeaking] = React.useState(false);
  const [messages, setMessages] = React.useState<ChatMessage[]>(initialMessages);
  const [draft, setDraft] = React.useState("");
  const socketRef = React.useRef<WebSocket | null>(null);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = React.useRef<string | null>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const current = stateCopy[concentrationState];
  const isMuseConnected = museStatus.status === "connected";

  React.useEffect(() => {
    return () => {
      stopSpeaking();
    };
  }, []);

  React.useEffect(() => {
    if (!textareaRef.current) {
      return;
    }
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
  }, [draft]);

  React.useEffect(() => {
    let reconnectTimer = 0;
    let socket: WebSocket | null = null;
    let isActive = true;

    const connect = () => {
      if (!isActive) {
        return;
      }

      socket = new WebSocket(AVATAR_WS_URL);
      socketRef.current = socket;

      socket.onopen = () => {
        setWebSocketStatus("connected");
      };

      socket.onmessage = (event) => {
        try {
          const update = normalizeAvatarUpdate(JSON.parse(event.data));
          if (!update) {
            return;
          }

          setMuseStatus({
            status: update.muse?.status ?? "unknown",
            phase: update.muse?.phase ?? "unknown",
            message: update.muse?.message ?? "",
          });

          const nextSpeechSettings = {
            rate: update.style?.speechRate ?? SPEECH_SETTINGS_BY_STATE[update.state].rate,
            pitch: update.style?.pitch ?? SPEECH_SETTINGS_BY_STATE[update.state].pitch,
          };

          if (update.muse?.status === "connected" && update.source === "muse") {
            setConcentrationState(update.state);
            setConcentration(update.concentration);
            setExpressionOverride(update.style?.expression);
            setSpeechSettings(nextSpeechSettings);
          }

          const replyText = update.replyText?.trim();
          if (replyText) {
            const now = Date.now();
            setMessages((currentMessages) => [
              ...currentMessages,
              {
                id: now,
                role: "assistant",
                content: replyText,
                timestamp: new Date(now),
                state: update.state,
              },
            ]);
            playAssistantAudio(update.audio);
          }
        } catch (error) {
          console.error("Failed to parse avatar update:", error);
          setWebSocketStatus("error");
        }
      };

      socket.onerror = () => {
        setWebSocketStatus("error");
      };

      socket.onclose = () => {
        if (!isActive) {
          return;
        }
        setWebSocketStatus("disconnected");
        reconnectTimer = window.setTimeout(connect, 1500);
      };
    };

    connect();

    return () => {
      isActive = false;
      window.clearTimeout(reconnectTimer);
      socket?.close();
      socketRef.current = null;
    };
  }, []);

  function resetChat() {
    stopSpeaking();
    setMessages(initialMessages.map((message) => ({ ...message, timestamp: new Date() })));
  }

  function stopSpeaking() {
    audioRef.current?.pause();
    audioRef.current = null;
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
    setIsSpeaking(false);
  }

  function playAssistantAudio(audio?: AvatarUpdateMessage["audio"]) {
    stopSpeaking();
    if (!audio?.data) {
      return;
    }

    const binary = atob(audio.data);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }

    const blob = new Blob([bytes], { type: audio.mimeType ?? "audio/mpeg" });
    const audioUrl = URL.createObjectURL(blob);
    const element = new Audio(audioUrl);
    audioRef.current = element;
    audioUrlRef.current = audioUrl;
    element.onended = stopSpeaking;
    element.onerror = stopSpeaking;
    setIsSpeaking(true);
    element.play().catch((error) => {
      console.error("Failed to play assistant audio:", error);
      stopSpeaking();
    });
  }

  function submitMessage(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content) {
      return;
    }

    const now = Date.now();
    const userMessage: ChatMessage = {
      id: now,
      role: "user",
      content,
      timestamp: new Date(now),
    };

    setMessages((currentMessages) => [...currentMessages, userMessage]);
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(
        JSON.stringify({
          type: "user_message",
          text: content,
        }),
      );
    }
    setDraft("");
  }

  function setDebugState(nextState: ConcentrationState) {
    stopSpeaking();
    setConcentrationState(nextState);
    setConcentration(stateCopy[nextState].attention);
    setExpressionOverride(undefined);
    setSpeechSettings(undefined);
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(
        JSON.stringify({
          type: "manual_state",
          state: nextState,
        }),
      );
    }
  }

  return (
    <div className={`app-shell ${concentrationState} ${isSidebarOpen ? "sidebar-open" : "sidebar-closed"}`}>
      <button
        className="sidebar-toggle"
        type="button"
        onClick={() => setIsSidebarOpen((open) => !open)}
        aria-label={isSidebarOpen ? "サイドパネルを閉じる" : "サイドパネルを開く"}
        aria-expanded={isSidebarOpen}
        title={isSidebarOpen ? "サイドパネルを閉じる" : "サイドパネルを開く"}
      >
        {isSidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
      </button>

      {isSidebarOpen && (
        <aside className="sidebar" aria-label="状態と設定">
          <section className="sidebar-card brand-card">
            <p className="eyebrow">デモパネル</p>
            <h1>Neuroadaptive AI Companion</h1>
            <p className="sidebar-copy">
              脳波から推定した集中度に応じて、AI Companionの見た目や口調を切り替えるためのフロントエンドです。
            </p>
          </section>

          <section className="sidebar-card">
            <div className="section-head">
              <h2>現在の状態</h2>
              <button className="icon-button" type="button" aria-label="状態を更新" title="状態を更新">
                <RefreshCw size={18} />
              </button>
            </div>
            <div className="state-grid">
              <div className="state-metric">
                <span>集中度</span>
                <strong>{concentration.toFixed(2)}</strong>
              </div>
              <div className="state-metric">
                <span>推定</span>
                <strong>{current.label}</strong>
              </div>
            </div>
            <div className={`state-pill ${concentrationState}`}>{current.label}</div>
            <p className="style-note">応答スタイル: {current.style}</p>
            <p className="style-note">表情: {expressionOverride ?? "状態に応じた既定表情"}</p>
            <p className="style-note">
              TTS: rate {(speechSettings?.rate ?? SPEECH_SETTINGS_BY_STATE[concentrationState].rate).toFixed(2)} / pitch{" "}
              {(speechSettings?.pitch ?? SPEECH_SETTINGS_BY_STATE[concentrationState].pitch).toFixed(2)}
            </p>
            <p className="style-note">音声: OpenAI gpt-4o-mini-tts / alloy によるAI生成音声</p>
            <p className="style-note">表示モード: Three.js</p>
          </section>

          <section className="sidebar-card">
            <div className="section-head">
              <h2>接続</h2>
            </div>
            <div className="connection-list">
              <div className="connection-row">
                <span>WebSocket</span>
                <div className={`connection-status ${webSocketStatus}`} aria-live="polite">
                  {webSocketStatus}
                </div>
              </div>
              <div className="connection-row">
                <span>Muse</span>
                <div className={`connection-status ${museStatus.status}`} aria-live="polite">
                  {museStatus.status}
                </div>
              </div>
            </div>
            <p className="style-note">{AVATAR_WS_URL}</p>
            <p className="style-note">Muse: {museStatus.phase} / {museStatus.message}</p>
          </section>

          <section className="sidebar-card">
            <div className="section-head">
              <h2>手動状態入力</h2>
              <div className={`connection-status ${isMuseConnected ? "connected" : "disconnected"}`}>
                {isMuseConnected ? "自動" : "手動"}
              </div>
            </div>
            <div className="section-title">
              <SlidersHorizontal size={18} />
              <p className="style-note manual-mode-note">
                {isMuseConnected ? "Muse接続中は脳波推定を優先します。" : "Muse未接続時はボタンで状態を切り替えます。"}
              </p>
            </div>
            <div className="segmented-control" aria-label="集中状態を切り替え">
              <button
                className={concentrationState === "focused" ? "active" : ""}
                type="button"
                onClick={() => setDebugState("focused")}
                disabled={isMuseConnected}
              >
                集中
              </button>
              <button
                className={concentrationState === "distracted" ? "active" : ""}
                type="button"
                onClick={() => setDebugState("distracted")}
                disabled={isMuseConnected}
              >
                散漫
              </button>
            </div>
          </section>

          <section className="sidebar-card">
            <div className="section-title">
              <Brain size={18} />
              <h2>脳波指標</h2>
            </div>
            <div className="signal-list">
              <SignalRow label="Alpha" value={concentrationState === "focused" ? 42 : 61} />
              <SignalRow label="Beta" value={Math.round(concentration * 100)} />
              <SignalRow label="Theta" value={concentrationState === "focused" ? 28 : 57} />
            </div>
          </section>
        </aside>
      )}

      <main className="main-layout">
        <section className="avatar-panel" aria-label="アバタ表示">
          <div className="avatar-stage">
            <div className="avatar-status">
              <span className="live-dot" />
              <span>{current.label}モード</span>
            </div>
            <AvatarViewer concentrationState={concentrationState} expressionOverride={expressionOverride} isSpeaking={isSpeaking} />
          </div>
        </section>

        <section className="chat-panel" aria-label="チャット">
          <header className="chat-header">
            <div>
              <p className="eyebrow">適応型会話</p>
              <h2>チャット</h2>
            </div>
            <div className="chat-actions">
              <div className={`speech-status ${isSpeaking ? "active" : ""}`} aria-live="polite">
                {isSpeaking ? "読み上げ中" : "待機中"}
              </div>
              <button
                className="icon-button"
                type="button"
                onClick={stopSpeaking}
                disabled={!isSpeaking}
                aria-label="読み上げ停止"
                title="読み上げ停止"
              >
                <VolumeX size={18} />
              </button>
              <button className="icon-button" type="button" onClick={resetChat} aria-label="リセット" title="リセット">
                <RotateCcw size={18} />
              </button>
            </div>
          </header>

          <div className="chat-messages">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </div>

          <form className="composer" onSubmit={submitMessage}>
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={1}
              placeholder="AI Companionにメッセージを送信..."
            />
            <button className="send-button" type="submit" aria-label="送信" title="送信">
              <Send size={20} />
            </button>
          </form>
        </section>
      </main>
    </div>
  );
}

function SignalRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="signal-row">
      <span>{label}</span>
      <div className="signal-track">
        <span style={{ width: `${value}%` }} />
      </div>
      <strong>{value}</strong>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isAssistant = message.role === "assistant";
  return (
    <article className={`message-bubble ${message.role}`}>
      {isAssistant ? (
        <div className="assistant-row">
          <div className={`assistant-avatar ${message.state ?? "distracted"}`}>
            <Activity size={20} />
          </div>
          <div className="assistant-content">
            <div className="message-meta">AIコンパニオン | {formatTime(message.timestamp)}</div>
            <div className="message-content">{message.content}</div>
          </div>
        </div>
      ) : (
        <>
          <div className="message-meta">あなた | {formatTime(message.timestamp)}</div>
          <div className="message-content">{message.content}</div>
        </>
      )}
    </article>
  );
}

declare global {
  interface Window {
    __neuroadaptiveAvatarRoot?: Root;
  }
}

const rootElement = document.getElementById("root") as HTMLElement;
const root = window.__neuroadaptiveAvatarRoot ?? ReactDOM.createRoot(rootElement);
window.__neuroadaptiveAvatarRoot = root;

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
