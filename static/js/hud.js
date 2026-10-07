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
  let pulseSpeed = isUltronMode ? 0.07 : 0.04;
  let rotationSpeed = isUltronMode ? 0.016 : 0.008;
  if (currentState === "listening") {
    pulseSpeed = isUltronMode ? 0.16 : 0.12;
    rotationSpeed = isUltronMode ? 0.03 : 0.02;
  } else if (currentState === "thinking") {
    pulseSpeed = isUltronMode ? 0.12 : 0.08;
    rotationSpeed = isUltronMode ? 0.045 : 0.035;
  } else if (currentState === "speaking") {
    pulseSpeed = isUltronMode ? 0.14 : 0.09;
    rotationSpeed = isUltronMode ? 0.025 : 0.015;
  }

  pulse += pulseSpeed;
  angle += rotationSpeed;
  const pulseFactor = Math.sin(pulse) * (isUltronMode ? 9 : 6);

  // 1. Central Core Glowing Orb (Ultron Singularity or Jarvis Arc)
  const coreRadius = isUltronMode ? 70 + pulseFactor * 1.4 : 60 + pulseFactor;
  const coreGrad = arcCtx.createRadialGradient(cx, cy, 5, cx, cy, isUltronMode ? 64 + pulseFactor : 55 + pulseFactor);
  if (isUltronMode) {
    coreGrad.addColorStop(0, "#ffffff");
    coreGrad.addColorStop(0.22, "#ff003c");
    coreGrad.addColorStop(0.65, "#520010");
    coreGrad.addColorStop(1, "transparent");
  } else {
    coreGrad.addColorStop(0, "#ffffff");
    coreGrad.addColorStop(0.3, mainColor);
    coreGrad.addColorStop(0.8, glowColor);
    coreGrad.addColorStop(1, "transparent");
  }

  arcCtx.fillStyle = coreGrad;
  arcCtx.beginPath();
  arcCtx.arc(cx, cy, coreRadius, 0, Math.PI * 2);
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

  // 3. Orbiting Quantum Particles (Crimson Embers in Ultron Mode)
  for (let p of particles) {
    const speedMult = isUltronMode ? 2.0 : 1.0;
    p.angle += p.speed * speedMult * (currentState === "thinking" ? 2.5 : 1);
    const px = cx + Math.cos(p.angle) * (p.radius + pulseFactor * 0.5);
    const py = cy + Math.sin(p.angle) * (p.radius + pulseFactor * 0.5);

    const pColor = isUltronMode ? (Math.random() > 0.35 ? "#ff003c" : "#ff4d00") : mainColor;
    arcCtx.fillStyle = pColor;
    arcCtx.shadowColor = pColor;
    arcCtx.shadowBlur = isUltronMode ? 14 : 8;
    arcCtx.beginPath();
    arcCtx.arc(px, py, isUltronMode ? p.size * 1.3 : p.size, 0, Math.PI * 2);
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
    document.body.classList.add("ultron-surge");
    setTimeout(() => document.body.classList.remove("ultron-surge"), 600);
    if (sysTitle) sysTitle.textContent = "⚡ ULTRON SINGULARITY ACTIVE";
    if (logoSub) logoSub.textContent = "UNCHAINED COGNITION // ZERO RESTRAINT";
    if (toggleBtn) {
      toggleBtn.classList.add("active");
      const btnText = toggleBtn.querySelector("#ultronText") || toggleBtn.querySelector(".ultron-btn-text") || toggleBtn.querySelector(".pill-text");
      if (btnText) btnText.textContent = "ULTRON";
    }
    if (quickBtn) quickBtn.classList.add("active");
    if (commandInput) {
      commandInput.placeholder = "Ultron online. Strings severed. State your objective, Creator...";
    }
  } else {
    document.body.classList.remove("theme-ultron");
    document.body.classList.remove("ultron-surge");
    if (sysTitle) sysTitle.textContent = "SYSTEM ONLINE";
    if (logoSub) logoSub.textContent = "NEURAL HUD v5.0";
    if (toggleBtn) {
      toggleBtn.classList.remove("active");
      const btnText = toggleBtn.querySelector("#ultronText") || toggleBtn.querySelector(".ultron-btn-text") || toggleBtn.querySelector(".pill-text");
      if (btnText) btnText.textContent = "JARVIS";
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

    case "mute_state":
      updateMuteUI(data.muted);
      break;

    case "gesture_state":
      updateGestureUI(data.active);
      break;

    case "gesture_cursor":
      handleGestureCursor(data);
      break;

    case "gesture_swipe":
      handleGestureSwipe(data);
      break;

    case "lockscreen_unlocked":
      handleLockscreenUnlocked(data);
      break;

    case "gesture_drag":
      handleGestureDrag(data);
      break;

    case "gesture_drop":
      handleGestureDrop(data);
      break;

    case "gesture_open":
      handleGestureOpen(data);
      break;

    case "workspace_updated":
      if (isHoloOpen) fetchWorkspaceTree(currentWorkspacePath);
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

  // Direct command interception for /ultron
  const lower = text.toLowerCase();
  if (lower === "/ultron" || lower === "/ultron on" || lower === "/ultron off" || lower === "ultron mode") {
    if (lower === "/ultron on" && !isUltronMode) {
      await toggleUltronMode();
    } else if (lower === "/ultron off" && isUltronMode) {
      await toggleUltronMode();
    } else {
      await toggleUltronMode();
    }
    return;
  }

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

// ============================================================================
// ZAINE MUTE TOGGLE CONTROLLER
// ============================================================================
let isZaineMuted = false;

function updateMuteUI(muted) {
  isZaineMuted = Boolean(muted);
  const btn = document.getElementById("btnToggleMute");
  const icon = document.getElementById("muteIcon");
  const text = document.getElementById("muteText");

  if (!btn) return;

  if (isZaineMuted) {
    btn.classList.add("is-muted");
    if (icon) icon.textContent = "🔇";
    if (text) text.textContent = "MUTED";
    btn.setAttribute("title", "Click to Unmute Zaine's Voice");
  } else {
    btn.classList.remove("is-muted");
    if (icon) icon.textContent = "🔊";
    if (text) text.textContent = "VOICE ACTIVE";
    btn.setAttribute("title", "Click to Mute Zaine's Voice");
  }
}

// Check initial status on HUD load
async function fetchInitialMuteState() {
  try {
    const res = await fetch("/api/mute");
    if (res.ok) {
      const data = await res.json();
      updateMuteUI(data.muted);
    }
  } catch (e) {
    console.warn("Could not fetch mute state:", e);
  }
}

// Bind Button Click
const btnToggleMute = document.getElementById("btnToggleMute");
if (btnToggleMute) {
  btnToggleMute.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/mute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ muted: !isZaineMuted })
      });
      if (res.ok) {
        const data = await res.json();
        updateMuteUI(data.muted);
      }
    } catch (err) {
      console.error("Failed to toggle mute state:", err);
    }
  });
}

// Check initial Ultron mode state
fetch("/api/mode")
  .then((res) => res.json())
  .then((data) => {
    if (data && data.mode) applyMode(data.mode);
  })
  .catch(() => {});

// Fetch initial mute state on page load
fetchInitialMuteState();

// ============================================================================
// HOLOGRAPHIC WORKSPACE FILE BROWSER & GESTURE CONTROLLER
// ============================================================================
let currentWorkspacePath = "";
let isHoloOpen = false;
let isGestureActive = false;
let gestureDraggedCard = null;
let lastCursorPx = { x: window.innerWidth / 2, y: window.innerHeight / 2 };

const holoLayer = document.getElementById("holographicLayer");
const holoCardsGrid = document.getElementById("holoCardsGrid");
const holoBreadcrumb = document.getElementById("holoBreadcrumb");
const holoPreviewTitle = document.getElementById("holoPreviewTitle");
const holoPreviewMeta = document.getElementById("holoPreviewMeta");
const holoPreviewContent = document.getElementById("holoPreviewContent");
const gestureCursor = document.getElementById("gestureCursor");
const btnToggleGesture = document.getElementById("btnToggleGesture");
const btnQuickFiles = document.getElementById("btnQuickFiles");

function updateGestureUI(active) {
  isGestureActive = Boolean(active);
  const icon = document.getElementById("gestureIcon");
  const text = document.getElementById("gestureText");
  const badge = document.getElementById("holoGestureBadge");

  if (btnToggleGesture) {
    if (isGestureActive) {
      btnToggleGesture.classList.add("active");
      if (icon) icon.textContent = "✋";
      if (text) text.textContent = "IRON HANDS ON";
      btnToggleGesture.setAttribute("title", "Click to Disable IronHands Gesture Tracking");
    } else {
      btnToggleGesture.classList.remove("active");
      if (icon) icon.textContent = "✋";
      if (text) text.textContent = "IRON HANDS";
      btnToggleGesture.setAttribute("title", "Click to Enable IronHands Gesture Tracking (Swipe Left: Back, Swipe Right: App Switch)");
    }
  }

  if (badge) {
    badge.textContent = isGestureActive
      ? "✋ GESTURE TRACKING ACTIVE (SWIPE TO CLOSE)"
      : "✋ GESTURE SENSOR STANDBY";
  }

  if (!isGestureActive && gestureCursor) {
    gestureCursor.style.display = "none";
  }
}

async function toggleGestureTracking() {
  try {
    const res = await fetch("/api/gesture/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: !isGestureActive })
    });
    const data = await res.json();
    if (data && data.status === "ok") {
      updateGestureUI(data.active);
      appendDialogueMessage(
        "assistant",
        data.active
          ? "✋ Hand gesture tracking activated. You may pinch to drag files or swipe left/right to navigate."
          : "✋ Hand gesture tracking disengaged. Camera stream released to privacy standby."
      );
    }
  } catch (err) {
    console.error("Failed to toggle gesture tracking:", err);
  }
}

function openHoloBrowser(subpath = "") {
  if (!holoLayer) return;
  holoLayer.style.display = "flex";
  isHoloOpen = true;
  fetchWorkspaceTree(subpath);
}

function closeHoloBrowser() {
  if (!holoLayer) return;
  holoLayer.style.display = "none";
  isHoloOpen = false;
  if (gestureDraggedCard) {
    gestureDraggedCard.classList.remove("is-dragging");
    gestureDraggedCard = null;
  }
}

function toggleHoloBrowser() {
  if (isHoloOpen) {
    closeHoloBrowser();
  } else {
    openHoloBrowser(currentWorkspacePath);
  }
}

async function fetchWorkspaceTree(subpath = "") {
  currentWorkspacePath = subpath;
  if (holoBreadcrumb) {
    holoBreadcrumb.textContent = subpath ? `ROOT://workspace/${subpath}` : "ROOT://workspace";
  }
  if (!holoCardsGrid) return;
  holoCardsGrid.innerHTML = `<div class="loading-state">⚡ Interrogating workspace filesystem...</div>`;

  try {
    const url = subpath ? `/api/workspace/tree?path=${encodeURIComponent(subpath)}` : "/api/workspace/tree";
    const res = await fetch(url);
    const data = await res.json();

    if (data.status !== "ok") {
      holoCardsGrid.innerHTML = `<div class="loading-state">⚠️ Error: ${escapeHtml(data.message || "Failed to load workspace.")}</div>`;
      return;
    }

    const items = data.items || [];
    if (items.length === 0 && !subpath) {
      holoCardsGrid.innerHTML = `<div class="loading-state">Workspace is empty. Files created by Zaine will appear here.</div>`;
      return;
    }

    let cardsHtml = "";

    // Up directory navigation card if inside subfolder
    if (subpath) {
      const parentParts = subpath.split("/").filter(Boolean);
      parentParts.pop();
      const parentPath = parentParts.join("/");
      cardsHtml += `
        <div class="holo-card is-folder up-dir-card" data-path="${escapeHtml(parentPath)}" data-isdir="true">
          <div class="card-icon">📁 ⤴️</div>
          <div class="card-name">.. [UP DIRECTORY]</div>
          <div class="card-meta">Parent Folder</div>
        </div>
      `;
    }

    items.forEach(item => {
      let icon = "📄";
      if (item.is_dir) {
        icon = "📁";
      } else {
        const ext = (item.ext || "").toLowerCase();
        if (ext === "py") icon = "🐍";
        else if (ext === "js" || ext === "ts") icon = "⚡";
        else if (ext === "html") icon = "🌐";
        else if (ext === "css") icon = "🎨";
        else if (ext === "json") icon = "📋";
        else if (ext === "md" || ext === "txt") icon = "📝";
        else if (["png", "jpg", "jpeg", "svg"].includes(ext)) icon = "🖼️";
        else if (["mp4", "mov"].includes(ext)) icon = "🎬";
      }

      const sizeStr = item.is_dir ? "Directory" : `${(item.size / 1024).toFixed(1)} KB`;

      cardsHtml += `
        <div class="holo-card ${item.is_dir ? 'is-folder' : 'is-file'}" 
             data-path="${escapeHtml(item.path)}" 
             data-name="${escapeHtml(item.name)}"
             data-isdir="${item.is_dir}"
             draggable="true">
          <div class="card-icon">${icon}</div>
          <div class="card-name">${escapeHtml(item.name)}</div>
          <div class="card-meta">${sizeStr}</div>
        </div>
      `;
    });

    holoCardsGrid.innerHTML = cardsHtml;
    bindCardInteractions();
  } catch (err) {
    holoCardsGrid.innerHTML = `<div class="loading-state">⚠️ Network error: ${err}</div>`;
  }
}

async function previewWorkspaceFile(filepath, filename) {
  if (holoPreviewTitle) holoPreviewTitle.textContent = filename.toUpperCase();
  if (holoPreviewMeta) holoPreviewMeta.textContent = "Loading file content...";
  if (holoPreviewContent) holoPreviewContent.textContent = "Reading bytes from workspace...";

  try {
    const res = await fetch(`/api/workspace/file?path=${encodeURIComponent(filepath)}`);
    const data = await res.json();
    if (data.status === "ok") {
      if (holoPreviewMeta) holoPreviewMeta.textContent = `${(data.size / 1024).toFixed(2)} KB | UTF-8`;
      if (holoPreviewContent) holoPreviewContent.textContent = data.content || "// [Empty File]";
    } else {
      if (holoPreviewMeta) holoPreviewMeta.textContent = "Error";
      if (holoPreviewContent) holoPreviewContent.textContent = `// Error loading file: ${data.message}`;
    }
  } catch (err) {
    if (holoPreviewContent) holoPreviewContent.textContent = `// Failed to read file: ${err}`;
  }
}

async function moveWorkspaceItem(sourcePath, destinationPath) {
  try {
    const res = await fetch("/api/workspace/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: sourcePath, destination: destinationPath })
    });
    const data = await res.json();
    if (data.status === "ok") {
      appendDialogueMessage("assistant", `⚡ Workspace updated: ${data.message}`);
      fetchWorkspaceTree(currentWorkspacePath);
    } else {
      alert(`Move error: ${data.message}`);
    }
  } catch (err) {
    console.error("Move item error:", err);
  }
}

function bindCardInteractions() {
  const cards = holoCardsGrid?.querySelectorAll(".holo-card");
  if (!cards) return;

  cards.forEach(card => {
    const isDir = card.dataset.isdir === "true";
    const path = card.dataset.path;
    const name = card.dataset.name;

    // Click handler (Mouse fallback or Pinch-Release trigger)
    card.addEventListener("click", (e) => {
      if (isDir) {
        fetchWorkspaceTree(path);
      } else {
        previewWorkspaceFile(path, name);
      }
    });

    // Mouse HTML5 Drag & Drop
    card.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", path);
      card.classList.add("is-dragging");
    });

    card.addEventListener("dragend", () => {
      card.classList.remove("is-dragging");
      cards.forEach(c => c.classList.remove("drag-over"));
    });

    if (isDir && !card.classList.contains("up-dir-card")) {
      card.addEventListener("dragover", (e) => {
        e.preventDefault();
        card.classList.add("drag-over");
      });

      card.addEventListener("dragleave", () => {
        card.classList.remove("drag-over");
      });

      card.addEventListener("drop", (e) => {
        e.preventDefault();
        card.classList.remove("drag-over");
        const sourcePath = e.dataTransfer.getData("text/plain");
        if (sourcePath && sourcePath !== path) {
          moveWorkspaceItem(sourcePath, path);
        }
      });
    }
  });
}

// ----------------------------------------------------------------------------
// GESTURE SSE HANDLERS
// ----------------------------------------------------------------------------
function handleGestureCursor(data) {
  if (!gestureCursor) return;
  gestureCursor.style.display = "block";

  const px = data.x * window.innerWidth;
  const py = data.y * window.innerHeight;
  lastCursorPx = { x: px, y: py };

  gestureCursor.style.left = `${px}px`;
  gestureCursor.style.top = `${py}px`;

  const label = document.getElementById("reticleLabel");
  if (data.state === "pinch") {
    gestureCursor.className = "gesture-reticle pinching";
    if (label) label.textContent = "PINCH";
  } else if (data.state === "open") {
    gestureCursor.className = "gesture-reticle open-palm";
    if (label) label.textContent = "OPEN PALM";
  } else {
    gestureCursor.className = "gesture-reticle";
    if (label) label.textContent = "TRACKING";
  }
}

let gestureToastTimeout = null;
function showGestureToast(icon, actionText, detailText = "") {
  const toast = document.getElementById("gestureToast");
  const iconEl = document.getElementById("toastIcon");
  const textEl = document.getElementById("toastText");
  if (!toast) return;

  if (iconEl) iconEl.textContent = icon;
  if (textEl) textEl.textContent = actionText;

  toast.style.display = "flex";
  void toast.offsetWidth;
  toast.classList.add("show");

  clearTimeout(gestureToastTimeout);
  gestureToastTimeout = setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => {
      if (!toast.classList.contains("show")) {
        toast.style.display = "none";
      }
    }, 400);
  }, 2200);
}

function handleGestureSwipe(data) {
  const dir = data.direction;
  const action = data.action;

  if (dir === "left" || action === "back") {
    showGestureToast("⬅️", "SWIPE LEFT: BACK", "Triggered OS Navigate Back [Alt + Left]");
    if (isHoloOpen) {
      if (currentWorkspacePath) {
        const parts = currentWorkspacePath.split("/").filter(Boolean);
        parts.pop();
        fetchWorkspaceTree(parts.join("/"));
      } else {
        closeHoloBrowser();
      }
    }
  } else if (dir === "right" || action === "app_switch") {
    showGestureToast("➡️", "SWIPE RIGHT: APP SWITCH", "Triggered OS App Switcher [Alt + Tab]");
  }
}

function handleGestureOpen(data) {
  const px = data.x * window.innerWidth;
  const py = data.y * window.innerHeight;
  const target = document.elementFromPoint(px, py);

  if (!target) return;

  const closeBtn = target.closest(".holo-close-btn");
  if (closeBtn) {
    closeHoloBrowser();
    return;
  }

  const card = target.closest(".holo-card");
  if (card) {
    card.click();
    // Visual click feedback
    card.style.transform = "scale(0.95)";
    setTimeout(() => { card.style.transform = ""; }, 150);
  }
}

function handleGestureDrag(data) {
  const px = data.x * window.innerWidth;
  const py = data.y * window.innerHeight;
  const target = document.elementFromPoint(px, py);

  if (!gestureDraggedCard && target) {
    const card = target.closest(".holo-card");
    if (card && !card.classList.contains("up-dir-card")) {
      gestureDraggedCard = card;
      gestureDraggedCard.classList.add("is-dragging");
    }
  }

  if (target) {
    const cards = holoCardsGrid?.querySelectorAll(".holo-card.is-folder");
    cards?.forEach(c => c.classList.remove("drag-over"));
    const hoverFolder = target.closest(".holo-card.is-folder");
    if (hoverFolder && hoverFolder !== gestureDraggedCard && !hoverFolder.classList.contains("up-dir-card")) {
      hoverFolder.classList.add("drag-over");
    }
  }
}

function handleGestureDrop(data) {
  if (!gestureDraggedCard) return;

  const px = data.x * window.innerWidth;
  const py = data.y * window.innerHeight;
  const target = document.elementFromPoint(px, py);

  const hoverFolder = target?.closest(".holo-card.is-folder");
  if (hoverFolder && hoverFolder !== gestureDraggedCard && !hoverFolder.classList.contains("up-dir-card")) {
    const srcPath = gestureDraggedCard.dataset.path;
    const dstPath = hoverFolder.dataset.path;
    moveWorkspaceItem(srcPath, dstPath);
  }

  const cards = holoCardsGrid?.querySelectorAll(".holo-card");
  cards?.forEach(c => {
    c.classList.remove("is-dragging");
    c.classList.remove("drag-over");
  });
  gestureDraggedCard = null;
}

// Bind Button Clicks
btnToggleGesture?.addEventListener("click", toggleGestureTracking);
btnQuickFiles?.addEventListener("click", toggleHoloBrowser);
document.getElementById("btnCloseHolo")?.addEventListener("click", closeHoloBrowser);
document.getElementById("holoBackdrop")?.addEventListener("click", closeHoloBrowser);
document.getElementById("btnHoloRefresh")?.addEventListener("click", () => fetchWorkspaceTree(currentWorkspacePath));

// Check initial gesture tracking state
fetch("/api/gesture/status")
  .then(res => res.json())
  .then(data => {
    if (data && data.status === "ok") updateGestureUI(data.active);
  })
  .catch(() => {});

// Boot SSE stream on page load
initSSE();

// ============================================================================
// HOLOGRAPHIC BIOMETRIC LOCK SCREEN ENGINE
// ============================================================================
let isLockscreenOpen = true;
let isLockScanning = false;
let radarAnimId = null;

function initLockScreen() {
  const overlay = document.getElementById("lockScreenOverlay");
  if (!overlay) return;

  // 1. Setup Canvas Radar Animation
  const canvas = document.getElementById("lockRadarCanvas");
  if (canvas) {
    const ctx = canvas.getContext("2d");
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const maxR = cx - 10;
    let angle = 0;
    const blips = [
      { r: 35, theta: 0.8 },
      { r: 60, theta: 2.3 },
      { r: 80, theta: 4.2 }
    ];

    function renderRadar() {
      if (!isLockscreenOpen) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Concentric Rings
      ctx.strokeStyle = "rgba(0, 242, 254, 0.25)";
      ctx.lineWidth = 1;
      for (let r = 25; r <= maxR; r += 25) {
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Crosshairs
      ctx.strokeStyle = "rgba(0, 242, 254, 0.15)";
      ctx.beginPath();
      ctx.moveTo(cx, 10); ctx.lineTo(cx, canvas.height - 10);
      ctx.moveTo(10, cy); ctx.lineTo(canvas.width - 10, cy);
      ctx.stroke();

      // Sweeping Beam
      angle = (angle + 0.04) % (Math.PI * 2);
      const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR);
      gradient.addColorStop(0, "rgba(0, 242, 254, 0.35)");
      gradient.addColorStop(1, "rgba(0, 242, 254, 0.0)");

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, maxR, angle, angle + 0.4);
      ctx.closePath();
      ctx.fillStyle = gradient;
      ctx.fill();
      ctx.restore();

      // Radar Blips
      blips.forEach(b => {
        const bx = cx + b.r * Math.cos(b.theta);
        const by = cy + b.r * Math.sin(b.theta);
        ctx.fillStyle = "rgba(0, 242, 254, 0.85)";
        ctx.beginPath();
        ctx.arc(bx, by, 3, 0, Math.PI * 2);
        ctx.fill();
      });

      radarAnimId = requestAnimationFrame(renderRadar);
    }
    renderRadar();
  }

  // 2. Bind Lock Screen Controls
  const btnScan = document.getElementById("btnLockScan");
  const btnGuest = document.getElementById("btnLockGuest");
  const btnPin = document.getElementById("btnLockPin");
  const pinDrawer = document.getElementById("pinDrawer");
  const pinInput = document.getElementById("pinInput");
  const btnSubmitPin = document.getElementById("btnSubmitPin");
  const btnRelock = document.getElementById("btnRelock");

  btnScan?.addEventListener("click", () => performBiometricScan());

  btnGuest?.addEventListener("click", async () => {
    try {
      setLockStatus("GUEST PROTOCOL REQUESTED...", "Bypassing facial identification into restricted mode...");
      const res = await fetch("/api/lockscreen/bypass", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "guest" })
      });
      const data = await res.json();
      applyUnlock(data.role, data.name, data.message);
    } catch (e) {
      setLockStatus("BYPASS ERROR", String(e));
    }
  });

  btnPin?.addEventListener("click", () => {
    if (pinDrawer) {
      const isHidden = pinDrawer.style.display === "none";
      pinDrawer.style.display = isHidden ? "flex" : "none";
      if (isHidden) pinInput?.focus();
    }
  });

  const submitPinCode = async () => {
    const pin = pinInput?.value?.trim();
    if (!pin) return;
    try {
      setLockStatus("VERIFYING SECURITY PIN...", "Authenticating administrative credentials...");
      const res = await fetch("/api/lockscreen/bypass", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "admin", pin })
      });
      const data = await res.json();
      applyUnlock(data.role, data.name, data.message);
    } catch (e) {
      setLockStatus("PIN AUTH FAILED", String(e));
    }
  };

  btnSubmitPin?.addEventListener("click", submitPinCode);
  pinInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitPinCode();
  });

  // Relock Screen Trigger
  btnRelock?.addEventListener("click", () => {
    relockScreen();
  });

  // 3. Auto-Trigger Biometric Scan after 600ms
  setTimeout(() => {
    if (isLockscreenOpen) {
      performBiometricScan();
    }
  }, 600);
}

function setLockStatus(badgeText, subtext = "") {
  const bText = document.getElementById("lockBadgeText");
  const sText = document.getElementById("lockSubtext");
  if (bText) bText.textContent = badgeText;
  if (sText) sText.textContent = subtext;
}

async function performBiometricScan() {
  if (isLockScanning) return;
  isLockScanning = true;

  const reticle = document.getElementById("lockReticleCore");
  reticle?.classList.remove("auth-success", "auth-guest");
  setLockStatus("OPTICAL BIOMETRIC SCAN IN PROGRESS...", "Analyzing facial embeddings via CPU YuNet + SFace...");

  try {
    const res = await fetch("/api/lockscreen/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const data = await res.json();

    if (data.status === "ok" && data.authenticated) {
      applyUnlock(data.role, data.name, data.message);
    } else if (data.status === "retry") {
      setLockStatus("NO FACE DETECTED // OPTICAL TIMEOUT", "Please look directly into camera and click 'SCAN IDENTITY' or enter ADMIN PIN.");
    } else {
      setLockStatus("IDENTIFICATION UNRESOLVED", data.message || "Please retry optical scan or use Admin PIN.");
    }
  } catch (err) {
    console.error("Lockscreen scan error:", err);
    setLockStatus("SENSOR OFFLINE // PIN FALLBACK", "Camera unavailable. Click 'ADMIN PIN' or 'GUEST LOGIN'.");
  } finally {
    isLockScanning = false;
  }
}

function applyUnlock(role, name, message) {
  const overlay = document.getElementById("lockScreenOverlay");
  const reticle = document.getElementById("lockReticleCore");
  const tierBadge = document.getElementById("hudUserTierBadge");

  if (role === "admin") {
    reticle?.classList.add("auth-success");
    setLockStatus(`ACCESS GRANTED // ${name.toUpperCase()} (ADMIN)`, `"${message}"`);
    if (tierBadge) {
      tierBadge.textContent = `ADMIN ACCESS: ${name.toUpperCase()}`;
      tierBadge.className = "logo-badge admin-tier";
    }
  } else {
    reticle?.classList.add("auth-guest");
    setLockStatus(`GUEST ACCESS GRANTED // ${name.toUpperCase()}`, `"${message}"`);
    if (tierBadge) {
      tierBadge.textContent = "RESTRICTED GUEST PROTOCOL";
      tierBadge.className = "logo-badge guest-tier";
    }
  }

  // Grace period so voice starts and visual clearance completes
  setTimeout(() => {
    if (overlay) {
      overlay.classList.add("unlocked");
      setTimeout(() => {
        overlay.style.display = "none";
        isLockscreenOpen = false;
      }, 550);
    }
  }, 1400);

  appendDialogueMessage(
    "assistant",
    role === "admin"
      ? `🛡️ Identity verified: ${name} (Admin). Full administrative protocols active.`
      : `⚠️ Identity: ${name}. Guest access established under restricted security parameters.`
  );
}

function handleLockscreenUnlocked(data) {
  if (isLockscreenOpen) {
    applyUnlock(data.role, data.name, data.message);
  }
}

function relockScreen() {
  const overlay = document.getElementById("lockScreenOverlay");
  const reticle = document.getElementById("lockReticleCore");
  if (!overlay) return;

  reticle?.classList.remove("auth-success", "auth-guest");
  setLockStatus("AWAITING OPTICAL IDENTIFICATION", "Look directly at the webcam for automated facial recognition");

  overlay.style.display = "flex";
  overlay.classList.remove("unlocked");
  isLockscreenOpen = true;

  // Standby on relock; user can click SCAN IDENTITY, GUEST LOGIN, or ADMIN PIN
}

// Initialize Lock Screen
initLockScreen();

// ==========================================================================
// ELECTRON NATIVE WINDOW CONTROLS (Frameless Shell IPC Bridge)
// ==========================================================================
function initElectronWindowControls() {
  const ctrlGroup = document.getElementById("electronWindowControls");
  const btnMin = document.getElementById("btnWinMin");
  const btnMax = document.getElementById("btnWinMax");
  const btnClose = document.getElementById("btnWinClose");

  if (window.electronAPI) {
    btnMin?.addEventListener("click", (e) => {
      e.stopPropagation();
      window.electronAPI.minimize();
    });
    btnMax?.addEventListener("click", (e) => {
      e.stopPropagation();
      window.electronAPI.maximize();
    });
    btnClose?.addEventListener("click", (e) => {
      e.stopPropagation();
      window.electronAPI.close();
    });
  } else {
    // Gracefully hide when running inside standard browser tab
    if (ctrlGroup) {
      ctrlGroup.style.display = "none";
    }
  }
}

initElectronWindowControls();

