const stateLabel = document.getElementById("stateLabel");
const attentionValue = document.getElementById("attentionValue");
const styleDescription = document.getElementById("styleDescription");
const engineDescription = document.getElementById("engineDescription");
const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const submitButton = chatForm.querySelector("button[type='submit']");

const STYLE_BY_STATE = {
  focused: "Formal, concise, structured",
  distracted: "Casual, friendly, chatty",
};

const AVATAR_BY_STATE = {
  focused: "/static/icons/icon_formal.png",
  distracted: "/static/icons/icon_casual.png",
};

let isSending = false;
let currentStateLabel = "distracted";

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.message || payload.error || "Request failed");
  }
  return payload;
}

function renderState(state) {
  currentStateLabel = state.label;
  attentionValue.textContent = state.attention.toFixed(2);
  stateLabel.textContent = state.label.replace("_", " ");
  stateLabel.className = `state-pill ${state.label}`;
  styleDescription.textContent = STYLE_BY_STATE[state.label] || STYLE_BY_STATE.distracted;
}

function formatTime(timestamp) {
  return new Date(timestamp * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function buildAssistantBubble(message, meta, body) {
  const row = document.createElement("div");
  row.className = "assistant-row";

  const avatar = document.createElement("img");
  avatar.className = "assistant-avatar";
  avatar.alt = message.state_label === "focused" ? "Formal AI icon" : "Casual AI icon";
  avatar.src = message.avatar_path || AVATAR_BY_STATE[message.state_label] || AVATAR_BY_STATE.distracted;

  const contentWrap = document.createElement("div");
  contentWrap.className = "assistant-content";
  contentWrap.append(meta, body);

  row.append(avatar, contentWrap);
  return row;
}

function createMessageBubble(message) {
  const bubble = document.createElement("article");
  bubble.className = `message-bubble ${message.role}`;

  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = `${message.role === "assistant" ? "AI Companion" : "You"} | ${formatTime(message.timestamp)}`;

  const body = document.createElement("div");
  body.className = "message-content";
  body.textContent = message.content;

  if (message.role === "assistant") {
    bubble.append(buildAssistantBubble(message, meta, body));
  } else {
    bubble.append(meta, body);
  }

  return bubble;
}

function renderMessages(messages) {
  chatMessages.innerHTML = "";
  messages.forEach((message) => {
    chatMessages.appendChild(createMessageBubble(message));
  });
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function refreshState() {
  const state = await fetchJson("/api/state");
  renderState(state);
}

async function refreshMeta() {
  const payload = await fetchJson("/api/meta");
  engineDescription.textContent = payload.llm_enabled
    ? `OpenAI ${payload.model}`
    : "Rule-based fallback (set OPENAI_API_KEY in .env to enable LLM)";
}

async function refreshHistory() {
  const payload = await fetchJson("/api/chat/history");
  renderMessages(payload.messages);
}

async function setDummyState(label) {
  const state = await fetchJson("/api/state", {
    method: "POST",
    body: JSON.stringify({ label }),
  });
  renderState(state);
}

function setSendingState(sending) {
  isSending = sending;
  submitButton.disabled = sending;
  messageInput.disabled = sending;
}

function appendOptimisticMessage(role, content) {
  const message = {
    role,
    content,
    timestamp: Date.now() / 1000,
    state_label: role === "assistant" ? currentStateLabel : null,
    avatar_path: role === "assistant" ? AVATAR_BY_STATE[currentStateLabel] : null,
  };
  const bubble = createMessageBubble(message);
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

function appendAssistantPendingBubble() {
  const bubble = appendOptimisticMessage("assistant", "");
  bubble.classList.add("pending");

  const content = bubble.querySelector(".message-content");
  const spinner = document.createElement("div");
  spinner.className = "message-spinner";
  spinner.innerHTML = `
    <span class="spinner-dot"></span>
    <span class="spinner-dot"></span>
    <span class="spinner-dot"></span>
  `;
  content.appendChild(spinner);
  return bubble;
}

function parseSseBuffer(buffer, onEvent) {
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() || "";

  parts.forEach((part) => {
    const lines = part.split("\n");
    let eventName = "message";
    let data = "";

    lines.forEach((line) => {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        data += line.slice(5).trim();
      }
    });

    if (data) {
      onEvent(eventName, JSON.parse(data));
    }
  });

  return remainder;
}

async function sendMessage(event) {
  event.preventDefault();
  if (isSending) {
    return;
  }

  const message = messageInput.value.trim();
  if (!message) {
    return;
  }

  appendOptimisticMessage("user", message);
  const pendingBubble = appendAssistantPendingBubble();
  const pendingContent = pendingBubble.querySelector(".message-content");
  const pendingSpinner = pendingBubble.querySelector(".message-spinner");

  messageInput.value = "";
  messageInput.style.height = "auto";
  setSendingState(true);

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    if (!response.ok || !response.body) {
      throw new Error("Streaming request failed");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let accumulated = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      buffer = parseSseBuffer(buffer, (eventName, payload) => {
        if (eventName === "meta" && payload.state) {
          renderState(payload.state);
        }

        if (eventName === "delta") {
          pendingSpinner?.remove();
          pendingBubble.classList.remove("pending");
          accumulated += payload.content;
          pendingContent.textContent = accumulated;
          chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        if (eventName === "done") {
          pendingSpinner?.remove();
          pendingBubble.classList.remove("pending");
          pendingContent.textContent = accumulated || payload.assistant_message.content;
          const avatar = pendingBubble.querySelector(".assistant-avatar");
          if (avatar && payload.assistant_message.avatar_path) {
            avatar.src = payload.assistant_message.avatar_path;
          }
        }
      });
    }
  } catch (error) {
    pendingBubble.classList.remove("pending");
    pendingContent.textContent = `Error: ${error.message}`;
  } finally {
    setSendingState(false);
    messageInput.focus();
    await Promise.all([refreshState(), refreshMeta()]);
  }
}

async function resetSession() {
  await fetchJson("/api/reset", { method: "POST" });
  await Promise.all([refreshState(), refreshHistory(), refreshMeta()]);
}

function attachAutosize() {
  messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 220)}px`;
  });
}

function attachKeyboardShortcut() {
  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.ctrlKey) {
      event.preventDefault();
      chatForm.requestSubmit();
    }
  });
}

async function bootstrap() {
  document.querySelectorAll("[data-state]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await setDummyState(button.dataset.state);
      } catch (error) {
        window.alert(error.message);
      }
    });
  });

  document.getElementById("refreshStateButton").addEventListener("click", async () => {
    try {
      await refreshState();
    } catch (error) {
      window.alert(error.message);
    }
  });

  document.getElementById("resetButton").addEventListener("click", async () => {
    try {
      await resetSession();
    } catch (error) {
      window.alert(error.message);
    }
  });

  chatForm.addEventListener("submit", async (event) => {
    try {
      await sendMessage(event);
    } catch (error) {
      window.alert(error.message);
    }
  });

  attachAutosize();
  attachKeyboardShortcut();
  await Promise.all([refreshState(), refreshHistory(), refreshMeta()]);
}

bootstrap().catch((error) => {
  console.error(error);
  window.alert("Initialization failed.");
});
