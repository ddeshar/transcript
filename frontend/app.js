const TARGET_SAMPLE_RATE = 16000;

const elements = {
  statusChip: document.getElementById("statusChip"),
  thaiCaption: document.getElementById("thaiCaption"),
  englishCaption: document.getElementById("englishCaption"),
  history: document.getElementById("history"),
  log: document.getElementById("log"),
  captions: document.getElementById("captions"),
  startBtn: document.getElementById("startBtn"),
  stopBtn: document.getElementById("stopBtn"),
  clearBtn: document.getElementById("clearBtn"),
  saveBtn: document.getElementById("saveBtn"),
  englishToggle: document.getElementById("englishToggle"),
  sizeButtons: Array.from(document.querySelectorAll(".size-btn")),
  tpLink: document.getElementById("tpLink"),
};

let websocket = null;
let audioContext = null;
let processor = null;
let mediaStream = null;
let sessionId = null;
let showEnglishPreview = true;
let transcriptSegments = [];
let lastPartialId = null;

// TTS (Text-to-Speech) variables
let ttsEnabled = false;
let ttsVoice = 'nova';
let ttsSpeed = 1.0;
let ttsProvider = 'mock';
let availableVoices = [];
let currentAudio = null;

const statusMap = {
  idle: { label: "Idle", className: "status-idle" },
  ready: { label: "Ready", className: "status-idle" },
  listening: { label: "Listening", className: "status-listening" },
  transcribing: { label: "Transcribing…", className: "status-transcribing" },
  translating: { label: "Translating…", className: "status-translating" },
  error: { label: "Error", className: "status-error" },
};

function setStatus(status, message) {
  const info = statusMap[status] || statusMap.idle;
  elements.statusChip.textContent = info.label;
  elements.statusChip.className = `status ${info.className}`;
  if (message) {
    elements.log.textContent = message;
  }
}

function appendLog(message) {
  elements.log.textContent = message;
}

// TTS Functions
async function initializeTTS() {
  try {
    const response = await fetch('/api/tts/voices');
    const data = await response.json();
    
    if (data.status === 'success') {
      availableVoices = data.voices;
      ttsProvider = data.provider;
      console.log(`TTS initialized with ${availableVoices.length} voices (${ttsProvider})`);
    } else {
      console.warn('Failed to load TTS voices:', data.error);
    }
  } catch (error) {
    console.warn('TTS not available:', error);
  }
}

async function synthesizeSpeech(text) {
  if (!ttsEnabled || !text.trim()) return;
  
  try {
    // Stop any currently playing audio
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    
    const response = await fetch('/api/tts/synthesize', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text: text,
        voice_id: ttsVoice,
        speed: ttsSpeed,
        language: 'th'
      })
    });
    
    const result = await response.json();
    
    if (result.status === 'success') {
      if (result.mock) {
        console.log(`Mock TTS: "${text}" (${result.duration_ms}ms, voice: ${result.voice_used})`);
        showTTSFeedback(text, result.voice_used);
      } else if (result.audio_data) {
        // Play real audio
        const audioBlob = base64ToBlob(result.audio_data, 'audio/mp3');
        const audioUrl = URL.createObjectURL(audioBlob);
        
        currentAudio = new Audio(audioUrl);
        currentAudio.play().catch(error => {
          console.warn('Failed to play TTS audio:', error);
        });
        
        // Clean up URL after playing
        currentAudio.onended = () => {
          URL.revokeObjectURL(audioUrl);
        };
      }
    } else {
      console.warn('TTS synthesis failed:', result.error);
    }
  } catch (error) {
    console.warn('TTS synthesis error:', error);
  }
}

function showTTSFeedback(text, voice) {
  // Create visual feedback for mock TTS
  const feedback = document.createElement('div');
  feedback.className = 'tts-feedback';
  feedback.innerHTML = `
    <div class="tts-icon">🔊</div>
    <div class="tts-text">${text.substring(0, 50)}${text.length > 50 ? '...' : ''}</div>
    <div class="tts-voice">${voice}</div>
  `;
  
  document.body.appendChild(feedback);
  
  setTimeout(() => {
    if (feedback.parentNode) {
      feedback.parentNode.removeChild(feedback);
    }
  }, 3000);
}

function base64ToBlob(base64, mimeType) {
  const byteCharacters = atob(base64);
  const byteNumbers = new Array(byteCharacters.length);
  
  for (let i = 0; i < byteCharacters.length; i++) {
    byteNumbers[i] = byteCharacters.charCodeAt(i);
  }
  
  const byteArray = new Uint8Array(byteNumbers);
  return new Blob([byteArray], { type: mimeType });
}

let reconnectAttempts = 0;
let maxReconnectAttempts = 5;
let keepAliveInterval = null;

function connectWebSocket() {
  if (websocket) {
    websocket.close();
  }
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${protocol}://${window.location.host}/ws/transcribe`;
  websocket = new WebSocket(wsUrl);
  websocket.binaryType = "arraybuffer";

  websocket.onopen = () => {
    setStatus("listening", "Microphone ready. Start speaking.");
    websocket.send(JSON.stringify({ type: "config", sampleRate: TARGET_SAMPLE_RATE }));
    elements.saveBtn.disabled = true;
    reconnectAttempts = 0; // Reset reconnect attempts on successful connection
    
    // Start keep-alive ping every 30 seconds
    if (keepAliveInterval) clearInterval(keepAliveInterval);
    keepAliveInterval = setInterval(() => {
      if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
  };

  websocket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleMessage(data);
  };

  websocket.onerror = (err) => {
    console.error("WebSocket error", err);
    setStatus("error", "WebSocket connection error.");
  };

  websocket.onclose = (event) => {
    console.log("WebSocket closed:", event.code, event.reason);
    if (keepAliveInterval) {
      clearInterval(keepAliveInterval);
      keepAliveInterval = null;
    }
    
    // Only attempt reconnection if it wasn't a manual close and we're still "active"
    if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts && mediaStream) {
      reconnectAttempts++;
      console.log(`Attempting to reconnect (${reconnectAttempts}/${maxReconnectAttempts})...`);
      setStatus("error", `Connection lost. Reconnecting... (${reconnectAttempts}/${maxReconnectAttempts})`);
      
      // Exponential backoff: 1s, 2s, 4s, 8s, 16s
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts - 1), 16000);
      setTimeout(() => {
        if (mediaStream) { // Only reconnect if we're still supposed to be active
          connectWebSocket();
        }
      }, delay);
    } else {
      // Manual close or max reconnects reached
      appendLog("Connection closed.");
      elements.startBtn.disabled = false;
      elements.stopBtn.disabled = true;
      elements.saveBtn.disabled = transcriptSegments.length === 0;
    }
  };
}

function handleMessage(data) {
  switch (data.type) {
    case "session":
      sessionId = data.sessionId;
      appendLog(`Session: ${sessionId}`);
      if (elements.tpLink) {
        const url = new URL(window.location.origin + "/teleprompter");
        url.searchParams.set("follow", sessionId);
        elements.tpLink.href = url.toString();
        elements.tpLink.style.display = "inline-block";
      }
      break;
    case "status":
      setStatus(data.status);
      break;
    case "partial":
      updateCaptions(data, false);
      break;
    case "final":
      updateCaptions(data, true);
      break;
    case "cleared":
      transcriptSegments = [];
      elements.history.innerHTML = "";
      break;
    case "transcript":
      transcriptSegments = data.segments || [];
      triggerDownload(transcriptSegments);
      break;
    case "error":
      setStatus("error", data.message || "An error occurred");
      break;
    default:
      break;
  }
}

function updateCaptions(payload, isFinal) {
  const thai = payload.thai || "";
  const english = payload.english || "";

  elements.thaiCaption.textContent = thai || "…";
  if (showEnglishPreview) {
    elements.englishCaption.textContent = english || "";
    elements.englishCaption.classList.remove("hidden");
  } else {
    elements.englishCaption.classList.add("hidden");
  }

  if (!isFinal) {
    lastPartialId = payload.segmentId;
    return;
  }

  // Trigger TTS for final Thai translation
  if (isFinal && thai && thai !== "…") {
    synthesizeSpeech(thai);
  }

  transcriptSegments.push(payload);
  renderHistory(transcriptSegments);
  elements.saveBtn.disabled = transcriptSegments.length === 0;
  lastPartialId = null;
}

function renderHistory(segments) {
  elements.history.innerHTML = segments
    .map((segment) => {
      const timestamp = formatTimestamp(segment.timestamp_ms || Date.now());
      const thai = segment.thai || "";
      const english = segment.english || "";
      const englishLine = showEnglishPreview ? `<span class="english">${escapeHtml(english)}</span>` : "";
      return `
        <div class="history-item">
          <span class="timestamp">${timestamp}</span>
          <span class="thai">${escapeHtml(thai)}</span>
          ${englishLine}
        </div>`;
    })
    .join("");
  elements.history.scrollTop = elements.history.scrollHeight;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function triggerDownload(segments) {
  if (!segments.length) {
    appendLog("Nothing to save yet.");
    return;
  }
  const lines = segments.map((segment) => {
    const ts = formatTimestamp(segment.timestamp_ms || Date.now());
    const thai = segment.thai || "";
    const english = segment.english || "";
    return `[${ts}] ${thai}\n(EN) ${english}`;
  });
  const blob = new Blob([lines.join("\n\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  link.download = `subtitles-${stamp}.txt`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function formatTimestamp(ms) {
  const date = new Date(ms);
  return date.toISOString().substring(11, 19) + "." + String(ms % 1000).padStart(3, "0");
}

function requestTranscriptDownload() {
  if (!websocket || websocket.readyState !== WebSocket.OPEN) {
    triggerDownload(transcriptSegments);
    return;
  }
  websocket.send(JSON.stringify({ type: "control", action: "save_request" }));
}

async function start() {
  try {
    setStatus("ready", "Requesting microphone…");
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    connectWebSocket();
    await setupAudioPipeline(mediaStream);
    elements.startBtn.disabled = true;
    elements.stopBtn.disabled = false;
    appendLog("Streaming audio…");
  } catch (err) {
    console.error(err);
    setStatus("error", err.message || "Microphone permission denied.");
  }
}

function stop() {
  if (processor) {
    processor.disconnect();
    processor.onaudioprocess = null;
    processor = null;
  }
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  if (websocket && websocket.readyState === WebSocket.OPEN) {
    websocket.send(JSON.stringify({ type: "control", action: "stop" }));
    websocket.close();
  }
  setStatus("idle", "Stopped.");
  elements.startBtn.disabled = false;
  elements.stopBtn.disabled = true;
}

async function setupAudioPipeline(stream) {
  audioContext = new (window.AudioContext || window.webkitAudioContext)();
  
  // Monitor audio context state changes and auto-resume if suspended
  audioContext.addEventListener('statechange', () => {
    console.log('Audio context state changed:', audioContext.state);
    if (audioContext.state === 'suspended') {
      // Try to resume after a short delay
      setTimeout(() => {
        if (audioContext.state === 'suspended') {
          audioContext.resume().then(() => {
            console.log('Auto-resumed audio context');
          }).catch(err => {
            console.warn('Failed to auto-resume audio context:', err);
          });
        }
      }, 1000);
    }
  });
  
  const source = audioContext.createMediaStreamSource(stream);
  const bufferSize = 4096;
  processor = audioContext.createScriptProcessor(bufferSize, 1, 1);

  processor.onaudioprocess = (event) => {
    // Ensure audio context is running
    if (audioContext.state === 'suspended') {
      audioContext.resume().catch(err => console.warn('Failed to resume audio context:', err));
      return;
    }
    
    if (!websocket || websocket.readyState !== WebSocket.OPEN) {
      return;
    }
    
    try {
      const inputBuffer = event.inputBuffer.getChannelData(0);
      const downsampled = downsampleBuffer(inputBuffer, audioContext.sampleRate, TARGET_SAMPLE_RATE);
      const pcm = convertFloat32ToPCM(downsampled);
      websocket.send(pcm);
    } catch (error) {
      console.error('Audio processing error:', error);
    }
  };

  source.connect(processor);
  processor.connect(audioContext.destination);
}

function downsampleBuffer(buffer, sampleRate, outSampleRate) {
  if (outSampleRate === sampleRate) {
    return buffer;
  }
  const ratio = sampleRate / outSampleRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;
  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accum += buffer[i];
      count++;
    }
    result[offsetResult] = count > 0 ? accum / count : 0;
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

function convertFloat32ToPCM(float32Array) {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  let offset = 0;
  for (let i = 0; i < float32Array.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

elements.startBtn.addEventListener("click", () => start());
elements.stopBtn.addEventListener("click", () => stop());
elements.clearBtn.addEventListener("click", () => {
  transcriptSegments = [];
  elements.history.innerHTML = "";
  elements.thaiCaption.textContent = "…";
  elements.englishCaption.textContent = "";
  if (websocket && websocket.readyState === WebSocket.OPEN) {
    websocket.send(JSON.stringify({ type: "control", action: "clear" }));
  }
});
elements.saveBtn.addEventListener("click", () => requestTranscriptDownload());
elements.englishToggle.addEventListener("change", (event) => {
  showEnglishPreview = event.target.checked;
  if (showEnglishPreview) {
    elements.englishCaption.classList.remove("hidden");
  } else {
    elements.englishCaption.classList.add("hidden");
  }
  renderHistory(transcriptSegments);
});
elements.sizeButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    elements.sizeButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    elements.captions.dataset.size = btn.dataset.size;
  });
});

document.addEventListener("visibilitychange", () => {
  // Keep audio processing running even when tab is hidden/minimized
  console.log("Page visibility changed:", document.hidden ? "hidden" : "visible");
  
  if (!document.hidden) {
    // Page is now visible - recover audio and WebSocket if needed
    if (audioContext && audioContext.state === 'suspended') {
      audioContext.resume().then(() => {
        console.log("Audio context resumed after tab became visible");
      });
    }
    
    // Check WebSocket connection health and reconnect if needed
    if (mediaStream && (!websocket || websocket.readyState !== WebSocket.OPEN)) {
      console.log("WebSocket disconnected while in background, reconnecting...");
      connectWebSocket();
    }
  }
});

// Handle page focus events for additional recovery
window.addEventListener('focus', () => {
  console.log('Window focused');
  
  if (mediaStream) {
    // Resume audio context if suspended
    if (audioContext && audioContext.state === 'suspended') {
      audioContext.resume().catch(err => console.warn('Failed to resume audio context:', err));
    }
    
    // Check and recover WebSocket connection
    if (!websocket || websocket.readyState !== WebSocket.OPEN) {
      console.log('Recovering WebSocket connection on window focus');
      connectWebSocket();
    }
  }
});

setStatus("idle", "Click Start to begin.");

// Initialize TTS
initializeTTS();

// TTS Control Event Listeners
document.getElementById('ttsToggle').addEventListener('change', function(e) {
  ttsEnabled = e.target.checked;
  const ttsControls = document.getElementById('ttsControls');
  
  if (ttsEnabled) {
    ttsControls.style.display = 'flex';
    console.log('TTS enabled');
  } else {
    ttsControls.style.display = 'none';
    // Stop any currently playing audio
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    console.log('TTS disabled');
  }
});

document.getElementById('voiceSelect').addEventListener('change', function(e) {
  ttsVoice = e.target.value;
  console.log('TTS voice changed to:', ttsVoice);
});

document.getElementById('speedSlider').addEventListener('input', function(e) {
  ttsSpeed = parseFloat(e.target.value);
  document.getElementById('speedValue').textContent = ttsSpeed + 'x';
  console.log('TTS speed changed to:', ttsSpeed);
});
