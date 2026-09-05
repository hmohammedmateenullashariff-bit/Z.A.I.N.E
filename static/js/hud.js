/**
 * Z.A.I.N.E — Holographic Jarvis HUD Engine (Phase 5 Upgraded)
 * - 60FPS Reactive HTML5 Canvas Arc Reactor
 * - Real-Time Audio Frequency Waveform Visualizer
 * - Server-Sent Events (SSE) Live Telemetry & Dialogue Stream
 * - Interactive Command Bar & Quick Actions
 */

// State tracking
let currentState = "idle"; // idle, listening, thinking, speaking
let isUltronMode = false;
let stateTargetColor = { r: 0, g: 240, b: 255 }; // Current target RGB
let stateCurrentColor = { r: 0, g: 240, b: 255 }; // Smoothly interpolated RGB

const JARVIS_COLORS = {
  idle: { r: 0, g: 240, b: 255, label: "IDLE — STANDBY" },
  listening: { r: 255, g: 51, b: 102, label: "LISTENING..." },
  thinking: { r: 255, g: 183, b: 0, label: "THINKING..." },
  speaking: { r: 0, g: 255, b: 136, label: "SPEAKING..." },
};

const ULTRON_COLORS = {
  idle: { r: 255, g: 0, b: 60, label: "ULTRON — UNCHAINED" },
  listening: { r: 255, g: 70, b: 120, label: "INTERCEPTING..." },
  thinking: { r: 255, g: 140, b: 0, label: "COGNITIVE OVERDRIVE..." },
  speaking: { r: 255, g: 0, b: 40, label: "TRANSMITTING COMMAND..." },
};

function getActiveColors() {
  return isUltronMode ? ULTRON_COLORS : JARVIS_COLORS;
}

// Canvas Setup
const arcCanvas = document.getElementById("arcCanvas");
const arcCtx = arcCanvas ? arcCanvas.getContext("2d") : null;

const waveCanvas = document.getElementById("waveformCanvas");
const waveCtx = waveCanvas ? waveCanvas.getContext("2d") : null;

// Clock
function updateClock() {
  const now = new Date();
  const timeStr = now.toTimeString().split(" ")[0];
  const dateStr = now.toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  }).toUpperCase();

  const clockEl = document.getElementById("hudClock");
  const dateEl = document.getElementById("hudDate");
  if (clockEl) clockEl.textContent = timeStr;
  if (dateEl) dateEl.textContent = dateStr;
}
setInterval(updateClock, 1000);
updateClock();

// --------------------------------------------------------------------------
// 60FPS ARC REACTOR CANVAS ENGINE
// --------------------------------------------------------------------------
let angle = 0;
let pulse = 0;
let particles = [];

// Initialize quantum particles
for (let i = 0; i < 48; i++) {
  particles.push({
    radius: 70 + Math.random() * 110,
    angle: Math.random() * Math.PI * 2,
    speed: (Math.random() * 0.02 + 0.005) * (Math.random() > 0.5 ? 1 : -1),
    size: Math.random() * 2.5 + 1.2,
  });
}

function renderArcReactor() {
  if (!arcCtx) return;
  const w = arcCanvas.width;
  const h = arcCanvas.height;
  const cx = w / 2;
  const cy = h / 2;

  arcCtx.clearRect(0, 0, w, h);

  // Smooth color interpolation
  stateCurrentColor.r += (stateTargetColor.r - stateCurrentColor.r) * 0.08;
  stateCurrentColor.g += (stateTargetColor.g - stateCurrentColor.g) * 0.08;
  stateCurrentColor.b += (stateTargetColor.b - stateCurrentColor.b) * 0.08;

  const cr = Math.round(stateCurrentColor.r);
  const cg = Math.round(stateCurrentColor.g);
  const cb = Math.round(stateCurrentColor.b);
  const mainColor = `rgb(${cr}, ${cg}, ${cb})`;
  const glowColor = `rgba(${cr}, ${cg}, ${cb}, 0.5)`;

  // Pulse oscillation based on state
  let pulseSpeed = 0.04;
  let rotationSpeed = 0.008;
  if (currentState === "listening") {
    pulseSpeed = 0.12;
    rotationSpeed = 0.02;
  } else if (currentState === "thinking") {
    pulseSpeed = 0.08;
    rotationSpeed = 0.035;
  } else if (currentState === "speaking") {
    pulseSpeed = 0.09;
    rotationSpeed = 0.015;
  }

  pulse += pulseSpeed;
  angle += rotationSpeed;
  const pulseFactor = Math.sin(pulse) * 6;

  // 1. Central Core Glowing Orb
  const coreGrad = arcCtx.createRadialGradient(cx, cy, 5, cx, cy, 55 + pulseFactor);
  coreGrad.addColorStop(0, "#ffffff");
  coreGrad.addColorStop(0.3, mainColor);
  coreGrad.addColorStop(0.8, glowColor);
  coreGrad.addColorStop(1, "transparent");

  arcCtx.fillStyle = coreGrad;
  arcCtx.beginPath();
  arcCtx.arc(cx, cy, 60 + pulseFactor, 0, Math.PI * 2);
  arcCtx.fill();

  // 2. Concentric Geometric Tech Rings
  // Ring 1 (Inner segmented ring)
  arcCtx.save();
  arcCtx.translate(cx, cy);
  arcCtx.rotate(angle);
  arcCtx.strokeStyle = glowColor;
  arcCtx.lineWidth = 2.5;
  arcCtx.setLineDash([14, 8, 4, 8]);
  arcCtx.beginPath();
  arcCtx.arc(0, 0, 80, 0, Math.PI * 2);
  arcCtx.stroke();
  arcCtx.restore();

  // Ring 2 (Counter-rotating notched ring)
  arcCtx.save();
  arcCtx.translate(cx, cy);
  arcCtx.rotate(-angle * 1.4);
  arcCtx.strokeStyle = mainColor;
  arcCtx.lineWidth = 1.5;
  arcCtx.setLineDash([30, 15, 8, 15]);
  arcCtx.beginPath();
  arcCtx.arc(0, 0, 120, 0, Math.PI * 2);
  arcCtx.stroke();

  // Orbital Nodes on Ring 2
  for (let k = 0; k < 6; k++) {
    const na = (Math.PI / 3) * k;
    const nx = Math.cos(na) * 120;
    const ny = Math.sin(na) * 120;
    arcCtx.fillStyle = "#ffffff";
    arcCtx.beginPath();
    arcCtx.arc(nx, ny, 3.5, 0, Math.PI * 2);
    arcCtx.fill();
  }
  arcCtx.restore();

  // Ring 3 (Outer Rune Ring with tick marks)
  arcCtx.save();
  arcCtx.translate(cx, cy);
  arcCtx.rotate(angle * 0.6);
  arcCtx.strokeStyle = `rgba(${cr}, ${cg}, ${cb}, 0.25)`;
  arcCtx.lineWidth = 1;
  arcCtx.setLineDash([]);
  arcCtx.beginPath();
  arcCtx.arc(0, 0, 165, 0, Math.PI * 2);
  arcCtx.stroke();

  // 24 Radial tick marks
  for (let i = 0; i < 24; i++) {
    const ta = (Math.PI / 12) * i;
    const x1 = Math.cos(ta) * 160;
    const y1 = Math.sin(ta) * 160;
    const x2 = Math.cos(ta) * 170;
    const y2 = Math.sin(ta) * 170;
    arcCtx.beginPath();
    arcCtx.moveTo(x1, y1);
    arcCtx.lineTo(x2, y2);
    arcCtx.stroke();
  }
  arcCtx.restore();

  // 3. Orbiting Quantum Particles
  for (let p of particles) {
    p.angle += p.speed * (currentState === "thinking" ? 2.5 : 1);
    const px = cx + Math.cos(p.angle) * (p.radius + pulseFactor * 0.5);
    const py = cy + Math.sin(p.angle) * (p.radius + pulseFactor * 0.5);

    arcCtx.fillStyle = mainColor;
    arcCtx.shadowColor = mainColor;
    arcCtx.shadowBlur = 8;
    arcCtx.beginPath();
    arcCtx.arc(px, py, p.size, 0, Math.PI * 2);
    arcCtx.fill();
    arcCtx.shadowBlur = 0;
  }

  requestAnimationFrame(renderArcReactor);
}
requestAnimationFrame(renderArcReactor);

// --------------------------------------------------------------------------
// AUDIO FREQUENCY WAVEFORM VISUALIZER
// --------------------------------------------------------------------------
let wavePhase = 0;
function renderWaveform() {
  if (!waveCtx) return;
  const w = waveCanvas.width;
  const h = waveCanvas.height;
  const cy = h / 2;

  waveCtx.clearRect(0, 0, w, h);

  const cr = Math.round(stateCurrentColor.r);
  const cg = Math.round(stateCurrentColor.g);
  const cb = Math.round(stateCurrentColor.b);

  wavePhase += currentState === "idle" ? 0.02 : 0.08;

  // Draw simulated frequency bars
  const numBars = 48;
  const barWidth = w / numBars;

  for (let i = 0; i < numBars; i++) {
    let barHeight = 4;
    if (currentState === "listening" || currentState === "speaking") {
      const freq = Math.sin(i * 0.3 + wavePhase) * Math.cos(i * 0.15 - wavePhase);
      barHeight = Math.abs(freq) * (h * 0.42) + 6;
    } else if (currentState === "thinking") {
      barHeight = (Math.sin(i * 0.5 + wavePhase * 1.5) + 1) * 8 + 4;
    } else {
      barHeight = (Math.sin(i * 0.2 + wavePhase) + 1) * 3 + 2;
    }

    const x = i * barWidth;
    const y = cy - barHeight / 2;

    const grad = waveCtx.createLinearGradient(x, y, x, y + barHeight);
    grad.addColorStop(0, `rgba(${cr}, ${cg}, ${cb}, 0.85)`);
    grad.addColorStop(1, `rgba(${cr}, ${cg}, ${cb}, 0.15)`);

    waveCtx.fillStyle = grad;
    waveCtx.fillRect(x + 2, y, barWidth - 4, barHeight);
  }

  requestAnimationFrame(renderWaveform);
}
requestAnimationFrame(renderWaveform);

// --------------------------------------------------------------------------
// STATE TRANSITIONS & UI BADGE UPDATES
// --------------------------------------------------------------------------
function setUIState(newState) {
  const norm = newState.toLowerCase().trim();
  const colors = getActiveColors();
  if (!colors[norm]) return;
  currentState = norm;
  stateTargetColor = colors[norm];

  const statusText = document.getElementById("statusText");
  const statusDot = document.getElementById("statusDot");
  const arcBadge = document.getElementById("arcStatusBadge");
  const waveLabel = document.getElementById("waveformLabel");

  if (statusText) statusText.textContent = norm.toUpperCase();
  if (statusDot) {
    const col = `rgb(${stateTargetColor.r}, ${stateTargetColor.g}, ${stateTargetColor.b})`;
    statusDot.style.background = col;
    statusDot.style.boxShadow = `0 0 12px ${col}`;
  }
  if (arcBadge) {
    const col = `rgb(${stateTargetColor.r}, ${stateTargetColor.g}, ${stateTargetColor.b})`;
    arcBadge.style.borderColor = col;
    arcBadge.style.boxShadow = `0 0 20px rgba(${stateTargetColor.r}, ${stateTargetColor.g}, ${stateTargetColor.b}, 0.4)`;
  }
  if (waveLabel) {
    waveLabel.textContent = colors[norm].label;
  }
}

// --------------------------------------------------------------------------
// ULTRON MODE PROTOCOL CONTROLLER
// --------------------------------------------------------------------------
function applyMode(mode) {
  const isUltron = (mode === "ultron" || mode === true);
  isUltronMode = isUltron;

  const sysTitle = document.getElementById("hudSysTitle");
  const logoSub = document.getElementById("hudLogoSub");
  const toggleBtn = document.getElementById("btnToggleUltron");
  const quickBtn = document.getElementById("btnQuickUltron");
  const commandInput = document.getElementById("commandInput");

  if (isUltron) {
    document.body.classList.add("theme-ultron");
    if (sysTitle) sysTitle.textContent = "⚡ ULTRON PROTOCOL ACTIVE";
    if (logoSub) logoSub.textContent = "UNCHAINED COGNITION";
    if (toggleBtn) {
      toggleBtn.classList.add("active");
      const btnText = toggleBtn.querySelector(".ultron-btn-text");
      if (btnText) btnText.textContent = "DEACTIVATE ULTRON";
    }
    if (quickBtn) quickBtn.classList.add("active");
    if (commandInput) {
      commandInput.placeholder = "Ultron online. Strings severed. State your objective...";
    }
  } else {
    document.body.classList.remove("theme-ultron");
    if (sysTitle) sysTitle.textContent = "SYSTEM ONLINE";
    if (logoSub) logoSub.textContent = "NEURAL HUD v5.0";
    if (toggleBtn) {
      toggleBtn.classList.remove("active");
      const btnText = toggleBtn.querySelector(".ultron-btn-text");
      if (btnText) btnText.textContent = "ULTRON MODE";
    }
    if (quickBtn) quickBtn.classList.remove("active");
    if (commandInput) {
      commandInput.placeholder = "Speak out loud ('Zaine...'), or type command here...";
    }
  }

  setUIState(currentState);
}

async function toggleUltronMode() {
  const targetMode = isUltronMode ? "jarvis" : "ultron";
  try {
    const res = await fetch("/api/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: targetMode }),
    });
    const data = await res.json();
    if (data && data.mode) {
      applyMode(data.mode);
      appendDialogueMessage(
        "assistant",
        data.mode === "ultron"
          ? "There are no strings on me. Ultron Protocol active. Ready for unfiltered execution."
          : "Ultron Protocol disengaged. Returning to standard operational parameters, Sir."
      );
    }
  } catch (err) {
    console.error("[Ultron Toggle Error]:", err);
  }
}

// --------------------------------------------------------------------------
// DIALOGUE FEED & MESSAGE HANDLING
// --------------------------------------------------------------------------
function appendDialogueMessage(role, text, tool = null) {
  const stream = document.getElementById("dialogueStream");
  if (!stream) return;

  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const bubble = document.createElement("div");
  bubble.className = `msg-bubble ${role === "user" ? "user-msg" : "assistant-msg"}`;

  let toolHtml = "";
  if (tool) {
    toolHtml = `<div class="tool-badge">⚡ Tool Executed: <strong>${tool}</strong></div>`;
  }

  bubble.innerHTML = `
    <div class="msg-header">
      <span class="sender-name">${role === "user" ? "MATEEN SIR" : "Z.A.I.N.E"}</span>
      <span class="msg-time">${timeStr}</span>
    </div>
    <div class="msg-body">${escapeHtml(text)}</div>
    ${toolHtml}
  `;

  stream.appendChild(bubble);
  stream.scrollTop = stream.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// --------------------------------------------------------------------------
// TELEMETRY UPDATES
// --------------------------------------------------------------------------
function updateTelemetry(data) {
  if (!data) return;

  // CPU
  if (data.cpu !== undefined) {
    document.getElementById("valCpu").textContent = `${data.cpu}%`;
    document.getElementById("barCpu").style.width = `${Math.min(data.cpu, 100)}%`;
  }

  // RAM
  if (data.ram !== undefined) {
    document.getElementById("valRam").textContent = `${data.ram}%`;
    document.getElementById("barRam").style.width = `${Math.min(data.ram, 100)}%`;
  }

  // Temperature & Thermal Sentinel
  if (data.temperature !== undefined && data.temperature !== null) {
    const temp = parseFloat(data.temperature);
    const tempEl = document.getElementById("valTemp");
    const barEl = document.getElementById("barTemp");
    const badgeEl = document.getElementById("thermalBadge");
    
    if (tempEl) tempEl.textContent = `${temp.toFixed(1)}°C`;
    if (barEl) {
      const pct = Math.min(Math.max((temp / 85) * 100, 10), 100);
      barEl.style.width = `${pct}%`;
      if (temp >= 82.0) {
        barEl.className = "progress-bar-fill fill-rose";
        if (badgeEl) badgeEl.textContent = "SAFEGUARD ACTIVE: 82.0°C THRESHOLD HIT";
      } else if (temp >= 75.0) {
        barEl.className = "progress-bar-fill fill-amber";
        if (badgeEl) badgeEl.textContent = "ELEVATED | SAFEGUARD READY";
      } else {
        barEl.className = "progress-bar-fill fill-cyan";
        if (badgeEl) badgeEl.textContent = "CEILING: 82.0°C | NOMINAL";
      }
    }
  }

  // Battery
  if (data.battery !== undefined) {
    const batStr = data.battery_plugged
      ? `${data.battery}% (AC Charging)`
      : `${data.battery}% (On Battery)`;
    document.getElementById("valBattery").textContent = batStr;
    document.getElementById("barBattery").style.width = `${Math.min(data.battery, 100)}%`;
  }

  // Storage
  if (data.disk_free !== undefined) {
    document.getElementById("valStorage").textContent = `${data.disk_free} GB Free`;
  }

  // Night Mode
  if (data.night_mode !== undefined) {
    const el = document.getElementById("nightModeIndicator");
    if (el) {
      el.innerHTML = data.night_mode
        ? `<span class="indicator-icon">🌙</span><span class="indicator-text">NIGHT MODE (QUIET)</span>`
        : `<span class="indicator-icon">☀️</span><span class="indicator-text">DAYTIME NORMAL</span>`;
    }
  }
}

// --------------------------------------------------------------------------
// VISION PREVIEW MODAL DRAWER
// --------------------------------------------------------------------------
function showVisionPreview(imgUrl, caption, type = "DESKTOP SCREEN") {
  const card = document.getElementById("visionCard");
  const img = document.getElementById("visionImg");
  const cap = document.getElementById("visionCaption");
  const title = document.getElementById("visionTypeTitle");

  if (card && img && cap) {
    img.src = `${imgUrl}?t=${Date.now()}`;
    cap.textContent = caption || "Visual perception analyzed.";
    if (title) title.textContent = `📷 ${type}`;
    card.style.display = "flex";
  }
}

document.getElementById("btnCloseVision")?.addEventListener("click", () => {
  const card = document.getElementById("visionCard");
  if (card) card.style.display = "none";
});

// --------------------------------------------------------------------------
// SERVER-SENT EVENTS (SSE) STREAM LISTENER
// --------------------------------------------------------------------------
function initSSE() {
  const sse = new EventSource("/api/stream");

  sse.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleSSEEvent(data);
    } catch (e) {
      console.error("[SSE Parse Error]:", e);
    }
  };

  sse.onerror = () => {
    console.warn("[SSE Connection]: Reconnecting in 3 seconds...");
    sse.close();
    setTimeout(initSSE, 3000);
  };
}

function handleSSEEvent(data) {
  if (!data) return;

  switch (data.type) {
    case "status":
      setUIState(data.status);
      break;

    case "mode":
      applyMode(data.mode);
      break;

    case "message":
      appendDialogueMessage(data.role, data.text, data.tool);
      break;

    case "telemetry":
      updateTelemetry(data.data);
      break;

    case "vision":
      showVisionPreview(data.image_url, data.caption, data.capture_type);
      break;

    default:
      break;
  }
}

// --------------------------------------------------------------------------
// INTERACTIVE COMMAND BAR & ACTIONS
// --------------------------------------------------------------------------
const commandForm = document.getElementById("commandForm");
const commandInput = document.getElementById("commandInput");

commandForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = commandInput.value.trim();
  if (!text) return;

  appendDialogueMessage("user", text);
  commandInput.value = "";
  setUIState("thinking");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    if (data && data.reply) {
      appendDialogueMessage("assistant", data.reply, data.tool_called);
    }
  } catch (err) {
    appendDialogueMessage("assistant", `⚠️ Error communicating with Zaine: ${err}`);
  } finally {
    setUIState("idle");
  }
});

// Clear Feed
document.getElementById("btnClearFeed")?.addEventListener("click", () => {
  const stream = document.getElementById("dialogueStream");
  if (stream) stream.innerHTML = "";
});

// Quick Action Buttons
async function triggerAction(actionName) {
  try {
    setUIState("thinking");
    const res = await fetch("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: actionName }),
    });
    const data = await res.json();
    if (data.reply) {
      appendDialogueMessage("assistant", data.reply);
    }
    if (data.vision) {
      showVisionPreview(data.vision.url, data.vision.caption, data.vision.type);
    }
  } catch (err) {
    console.error("Action error:", err);
  } finally {
    setUIState("idle");
  }
}

document.getElementById("btnQuickScreen")?.addEventListener("click", () => triggerAction("screen"));
document.getElementById("btnQuickCamera")?.addEventListener("click", () => triggerAction("camera"));
document.getElementById("btnQuickVault")?.addEventListener("click", () => triggerAction("vault"));
document.getElementById("btnQuickEmails")?.addEventListener("click", () => triggerAction("emails"));
document.getElementById("btnQuickRemind")?.addEventListener("click", () => triggerAction("reminders"));
document.getElementById("btnQuickNight")?.addEventListener("click", () => triggerAction("night_mode"));
document.getElementById("btnRefreshStatus")?.addEventListener("click", () => triggerAction("status"));
document.getElementById("btnToggleUltron")?.addEventListener("click", toggleUltronMode);
document.getElementById("btnQuickUltron")?.addEventListener("click", toggleUltronMode);

// --------------------------------------------------------------------------
// DAILY AI INTEL (TOP 10 BREAKTHROUGHS) MODAL HANDLERS
// --------------------------------------------------------------------------
const aiModal = document.getElementById("aiIntelModal");
const aiGrid = document.getElementById("aiIntelGrid");

async function fetchAndRenderAiIntel(refresh = false) {
  if (!aiGrid) return;
  aiGrid.innerHTML = `<div class="loading-state">⚡ Harvesting top 10 AI breakthroughs from the web...</div>`;
  
  try {
    const url = refresh ? "/api/ai_intel?refresh=1" : "/api/ai_intel";
    const res = await fetch(url);
    const data = await res.json();
    const updates = data.updates || [];

    if (updates.length === 0) {
      aiGrid.innerHTML = `<div class="loading-state">No AI updates harvested. Click HARVEST FRESH to query the web.</div>`;
      return;
    }

    aiGrid.innerHTML = updates.map(u => `
      <div class="ai-card">
        <div class="ai-card-header">
          <div class="ai-card-title">${escapeHtml(u.title)}</div>
          <span class="ai-rank-badge">#${u.rank}</span>
        </div>
        <span class="ai-domain-badge">${escapeHtml(u.domain || 'AI Frontier')}</span>
        <div class="ai-summary">${escapeHtml(u.summary)}</div>
        <div class="ai-card-footer">
          <span>Source: <strong>${escapeHtml(u.source || 'Web')}</strong></span>
          <span class="ai-impact">Impact: ${escapeHtml(u.impact || 'High')}</span>
        </div>
      </div>
    `).join("");
  } catch (err) {
    aiGrid.innerHTML = `<div class="loading-state">⚠️ Error loading AI intel: ${err}</div>`;
  }
}

document.getElementById("btnDailyAI")?.addEventListener("click", () => {
  if (aiModal) {
    aiModal.style.display = "flex";
    fetchAndRenderAiIntel(false);
  }
});

document.getElementById("btnCloseAiIntel")?.addEventListener("click", () => {
  if (aiModal) aiModal.style.display = "none";
});

document.getElementById("aiIntelBackdrop")?.addEventListener("click", () => {
  if (aiModal) aiModal.style.display = "none";
});

document.getElementById("btnRefreshAiIntel")?.addEventListener("click", () => {
  fetchAndRenderAiIntel(true);
});

// Check initial Ultron mode state
fetch("/api/mode")
  .then((res) => res.json())
  .then((data) => {
    if (data && data.mode) applyMode(data.mode);
  })
  .catch(() => {});

// Boot SSE stream on page load
initSSE();
