const audio = document.querySelector("#audio-player");
const playButton = document.querySelector("#play-button");
const stopButton = document.querySelector("#stop-button");
const seekBar = document.querySelector("#seek-bar");
const currentTime = document.querySelector("#current-time");
const duration = document.querySelector("#duration");
const rawEegPanel = document.querySelector("#raw-eeg-panel");
const rawEegCanvas = document.querySelector("#raw-eeg-canvas");
const lslStatus = document.querySelector("#lsl-status");
const rawEegContext = rawEegCanvas.getContext("2d");

const fields = {
  attention: document.querySelector("#attention"),
  playbackRate: document.querySelector("#playback-rate"),
  alphaPower: document.querySelector("#alpha-power"),
  betaPower: document.querySelector("#beta-power"),
  thetaPower: document.querySelector("#theta-power"),
  lowBetaPower: document.querySelector("#low-beta-power"),
  highBetaPower: document.querySelector("#high-beta-power"),
  alphaBetaRatio: document.querySelector("#alpha-beta-ratio"),
  thetaBetaRatio: document.querySelector("#theta-beta-ratio"),
  thetaAlphaRatio: document.querySelector("#theta-alpha-ratio"),
  thetaAlphaOverBeta: document.querySelector("#theta-alpha-over-beta"),
};

let isSeeking = false;

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) {
    return "0:00";
  }

  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${rest}`;
}

function setText(element, value, digits = 3) {
  element.textContent = Number(value).toFixed(digits);
}

function drawRawEEG(samples = []) {
  const width = rawEegCanvas.width;
  const height = rawEegCanvas.height;
  rawEegContext.clearRect(0, 0, width, height);

  rawEegContext.fillStyle = "#ffffff";
  rawEegContext.fillRect(0, 0, width, height);

  rawEegContext.strokeStyle = "#d7e4f5";
  rawEegContext.lineWidth = 1;
  for (let x = 0; x <= width; x += 48) {
    rawEegContext.beginPath();
    rawEegContext.moveTo(x, 0);
    rawEegContext.lineTo(x, height);
    rawEegContext.stroke();
  }
  for (let y = 0; y <= height; y += 38) {
    rawEegContext.beginPath();
    rawEegContext.moveTo(0, y);
    rawEegContext.lineTo(width, y);
    rawEegContext.stroke();
  }

  if (!samples.length) {
    return;
  }

  const maxAbs = Math.max(...samples.map((value) => Math.abs(value)), 1);
  rawEegContext.strokeStyle = "#0b67d1";
  rawEegContext.lineWidth = 2;
  rawEegContext.beginPath();

  samples.forEach((sample, index) => {
    const x = (index / Math.max(samples.length - 1, 1)) * width;
    const y = height / 2 - (sample / maxAbs) * (height * 0.38);
    if (index === 0) {
      rawEegContext.moveTo(x, y);
    } else {
      rawEegContext.lineTo(x, y);
    }
  });

  rawEegContext.stroke();
}

function updateLSLPanel(data) {
  const connected = Boolean(data.lsl_connected);
  rawEegPanel.classList.toggle("is-disconnected", !connected);
  lslStatus.textContent = connected ? "LSL online" : "LSL offline";
  drawRawEEG(data.raw_eeg || []);
}

function updateProgress() {
  currentTime.textContent = formatTime(audio.currentTime);
  duration.textContent = formatTime(audio.duration);

  if (!isSeeking && Number.isFinite(audio.duration) && audio.duration > 0) {
    seekBar.value = Math.round((audio.currentTime / audio.duration) * Number(seekBar.max));
  }
}

async function refreshEEG() {
  try {
    const response = await fetch("/api/eeg", { cache: "no-store" });
    const data = await response.json();

    audio.playbackRate = data.playback_rate;
    setText(fields.playbackRate, data.playback_rate, 2);
    setText(fields.attention, data.attention);
    setText(fields.alphaPower, data.alpha_power);
    setText(fields.betaPower, data.beta_power);
    setText(fields.thetaPower, data.theta_power);
    setText(fields.lowBetaPower, data.low_beta_power);
    setText(fields.highBetaPower, data.high_beta_power);
    setText(fields.alphaBetaRatio, data.alpha_beta_ratio);
    setText(fields.thetaBetaRatio, data.theta_beta_ratio);
    setText(fields.thetaAlphaRatio, data.theta_alpha_ratio);
    setText(fields.thetaAlphaOverBeta, data.theta_alpha_over_beta);
    updateLSLPanel(data);
  } catch (error) {
    console.error("Failed to refresh EEG features", error);
  }
}

playButton.addEventListener("click", () => {
  audio.play();
});

stopButton.addEventListener("click", () => {
  audio.pause();
  audio.currentTime = 0;
  updateProgress();
});

seekBar.addEventListener("input", () => {
  isSeeking = true;
  if (Number.isFinite(audio.duration) && audio.duration > 0) {
    const ratio = Number(seekBar.value) / Number(seekBar.max);
    currentTime.textContent = formatTime(audio.duration * ratio);
  }
});

seekBar.addEventListener("change", () => {
  if (Number.isFinite(audio.duration) && audio.duration > 0) {
    const ratio = Number(seekBar.value) / Number(seekBar.max);
    audio.currentTime = audio.duration * ratio;
  }
  isSeeking = false;
});

audio.addEventListener("loadedmetadata", updateProgress);
audio.addEventListener("timeupdate", updateProgress);

drawRawEEG();
refreshEEG();
setInterval(refreshEEG, 3000);
