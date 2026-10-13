"""
Z.A.I.N.E — Autonomous Core Agent Service
Headless HTTP service hosting ZaineAgent, Request Coordinator, and capability endpoints.

Clean Layer 2 Architecture:
- Dispatches to single unified ZaineAgent instance
- Serialized, atomic, idempotent request execution via RequestCoordinator
- REST & Server-Sent Events (SSE) endpoints for Terminal TUI, Telegram, and Cascade
- NO GUI, NO HTML templates, NO Electron, NO browser windows
"""

import os
import sys
import re
import json
import time
import shutil
import psutil
import datetime
import threading
import urllib.parse
import uuid
from pathlib import Path
from typing import Optional, Dict, Tuple, Any
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import ZaineAgent
from coordinator import get_request_coordinator
import voice

_coordinator = get_request_coordinator()


def get_system_telemetry() -> dict:
    """Collects real-time hardware telemetry."""
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent

    battery_info = psutil.sensors_battery()
    bat_pct = int(battery_info.percent) if battery_info else 100
    bat_plugged = bool(battery_info.power_plugged) if battery_info else True

    disk_free = 0
    try:
        _, _, free = shutil.disk_usage("C:\\" if sys.platform == "win32" else "/")
        disk_free = round(free / (1024 ** 3), 1)
    except Exception:
        pass

    hour = datetime.datetime.now().hour
    night_mode = 0 <= hour < 7

    temp_c = None
    try:
        from thermal_guard import get_cpu_temperature_celsius
        temp_c = get_cpu_temperature_celsius()
    except Exception:
        pass

    return {
        "cpu": cpu,
        "ram": ram,
        "temperature": temp_c,
        "battery": bat_pct,
        "battery_plugged": bat_plugged,
        "disk_free": disk_free,
        "night_mode": night_mode,
        "timestamp": time.time(),
    }


def _render_hud_dashboard_html(port: int = 7860) -> str:
    """Renders cybernetic dark-mode web dashboard for Z.A.I.N.E Core Service."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Live telemetry, core diagnostics, and daemon status for Z.A.I.N.E autonomous personal AI assistant.">
  <title>Z.A.I.N.E Neural Engine — Core System Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #06080f;
      --card-bg: rgba(13, 20, 36, 0.7);
      --card-border: rgba(30, 48, 80, 0.6);
      --card-hover-border: rgba(16, 185, 129, 0.4);
      --emerald: #10b981;
      --emerald-glow: rgba(16, 185, 129, 0.25);
      --cyan: #06b6d4;
      --cyan-glow: rgba(6, 182, 212, 0.25);
      --amber: #f59e0b;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #475569;
      --font-sans: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg);
      background-image: 
        radial-gradient(circle at 50% 0%, rgba(16, 185, 129, 0.12) 0%, transparent 60%),
        radial-gradient(circle at 80% 80%, rgba(6, 182, 212, 0.08) 0%, transparent 50%),
        linear-gradient(to bottom, rgba(6, 8, 15, 0.8), #06080f);
      color: var(--text);
      font-family: var(--font-sans);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      line-height: 1.5;
      padding: 1.5rem;
    }

    .container {
      max-width: 1200px;
      margin: 0 auto;
      width: 100%;
    }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.07);
      margin-bottom: 2rem;
      flex-wrap: wrap;
      gap: 1rem;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 0.85rem;
    }

    .brand-icon {
      width: 44px;
      height: 44px;
      border-radius: 10px;
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(6, 182, 212, 0.2));
      border: 1px solid var(--emerald);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 20px var(--emerald-glow);
    }

    .brand-icon svg {
      width: 24px;
      height: 24px;
      color: var(--emerald);
    }

    .brand-title {
      font-weight: 800;
      font-size: 1.35rem;
      letter-spacing: 0.08em;
    }

    .brand-title span.acc-emerald {
      color: var(--emerald);
    }

    .brand-title span.acc-cyan {
      color: var(--cyan);
    }

    .brand-subtitle {
      font-size: 0.75rem;
      color: var(--text-muted);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-family: var(--font-mono);
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.6rem;
      padding: 0.45rem 1rem;
      border-radius: 9999px;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.35);
      font-size: 0.8rem;
      font-family: var(--font-mono);
      font-weight: 600;
      color: var(--emerald);
      box-shadow: 0 0 16px var(--emerald-glow);
    }

    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--emerald);
      box-shadow: 0 0 10px var(--emerald);
      animation: pulse 2s infinite ease-in-out;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
    }

    .hero {
      margin-bottom: 2rem;
    }

    h1 {
      font-size: 2rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin-bottom: 0.4rem;
      background: linear-gradient(135deg, #ffffff 40%, #94a3b8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .hero-sub {
      color: var(--text-muted);
      font-size: 1rem;
    }

    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 1.25rem;
      margin-bottom: 2rem;
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 1.35rem;
      backdrop-filter: blur(12px);
      transition: all 0.25s ease;
      position: relative;
      overflow: hidden;
    }

    .card:hover {
      border-color: var(--card-hover-border);
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35), 0 0 15px rgba(16, 185, 129, 0.1);
      transform: translateY(-2px);
    }

    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
    }

    .card-title {
      font-size: 0.82rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }

    .card-metric {
      font-size: 2.25rem;
      font-weight: 700;
      font-family: var(--font-mono);
      margin-bottom: 0.5rem;
      display: flex;
      align-items: baseline;
      gap: 0.3rem;
    }

    .card-unit {
      font-size: 1.1rem;
      color: var(--text-muted);
      font-weight: 400;
    }

    .progress-track {
      width: 100%;
      height: 7px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 9999px;
      overflow: hidden;
      margin: 0.75rem 0 0.5rem;
    }

    .progress-bar {
      height: 100%;
      background: linear-gradient(90deg, var(--emerald), var(--cyan));
      border-radius: 9999px;
      transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .card-foot {
      font-size: 0.8rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
      display: flex;
      justify-content: space-between;
    }

    .panel {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 1.5rem;
      backdrop-filter: blur(12px);
      margin-bottom: 2rem;
    }

    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.2rem;
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .panel-title {
      font-size: 1.15rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .panel-title svg {
      width: 20px;
      height: 20px;
      color: var(--emerald);
    }

    .cli-notice {
      background: linear-gradient(135deg, rgba(6, 182, 212, 0.1), rgba(16, 185, 129, 0.05));
      border: 1px solid rgba(6, 182, 212, 0.3);
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      margin-bottom: 2rem;
      display: flex;
      align-items: flex-start;
      gap: 1.2rem;
    }

    .cli-notice-icon {
      color: var(--cyan);
      flex-shrink: 0;
      margin-top: 0.2rem;
    }

    .cli-notice-content h2 {
      font-size: 1.05rem;
      margin-bottom: 0.3rem;
      color: #ffffff;
    }

    .cli-notice-content p {
      font-size: 0.9rem;
      color: var(--text-muted);
      margin-bottom: 0.8rem;
    }

    .cmd-box {
      display: inline-flex;
      align-items: center;
      gap: 0.75rem;
      background: #04060b;
      border: 1px solid rgba(255, 255, 255, 0.1);
      padding: 0.45rem 0.9rem;
      border-radius: 8px;
      font-family: var(--font-mono);
      font-size: 0.88rem;
      color: var(--emerald);
    }

    .endpoints-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 0.85rem;
    }

    .endpoint-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.8rem 1rem;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 8px;
      font-family: var(--font-mono);
      font-size: 0.85rem;
      text-decoration: none;
      color: var(--text);
      transition: all 0.2s ease;
    }

    .endpoint-item:hover {
      background: rgba(16, 185, 129, 0.08);
      border-color: rgba(16, 185, 129, 0.3);
      color: #ffffff;
      transform: translateX(4px);
    }

    .endpoint-method {
      display: inline-block;
      padding: 0.15rem 0.4rem;
      border-radius: 4px;
      font-size: 0.72rem;
      font-weight: 700;
      background: rgba(6, 182, 212, 0.15);
      color: var(--cyan);
      margin-right: 0.5rem;
    }

    .endpoint-link {
      display: flex;
      align-items: center;
    }

    .btn-test {
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid var(--emerald);
      color: var(--emerald);
      font-family: var(--font-mono);
      font-size: 0.82rem;
      font-weight: 600;
      padding: 0.45rem 1rem;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s;
    }

    .btn-test:hover {
      background: var(--emerald);
      color: #06080f;
      box-shadow: 0 0 15px var(--emerald-glow);
    }

    footer {
      margin-top: auto;
      padding-top: 2rem;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-icon">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/>
          </svg>
        </div>
        <div>
          <div class="brand-title"><span class="acc-emerald">Z.A.I.N.E</span> <span class="acc-cyan">NEURAL</span> CORE</div>
          <div class="brand-subtitle">Zero-Latency Autonomous Intelligence Neural Engine</div>
        </div>
      </div>
      <div class="status-badge" id="service-status-badge">
        <div class="pulse-dot"></div>
        <span>CORE ONLINE · PORT {{PORT}}</span>
      </div>
    </header>

    <div class="hero">
      <h1>Core System Telemetry & Node Diagnostics</h1>
      <p class="hero-sub">Local-first autonomous intelligence daemon running headless on port {{PORT}}</p>
    </div>

    <!-- Terminal Client Notice -->
    <div class="cli-notice">
      <div class="cli-notice-icon">
        <svg width="26" height="26" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
        </svg>
      </div>
      <div class="cli-notice-content">
        <h2>Terminal Native Architecture</h2>
        <p>Z.A.I.N.E is designed as a terminal-native AI developer and companion agent. The core service daemon on port {{PORT}} powers the CLI/TUI thin clients with local Ollama inference, tool routing, and memory consolidation.</p>
        <div>
          <span style="font-size: 0.85rem; color: var(--text-muted); margin-right: 0.5rem;">Launch Primary TUI:</span>
          <span class="cmd-box">python zaine_tui.py</span>
        </div>
      </div>
    </div>

    <!-- Telemetry Cards -->
    <div class="metrics-grid">
      <!-- CPU -->
      <div class="card">
        <div class="card-top">
          <span class="card-title">CPU Utilization</span>
          <span style="color: var(--emerald);">⚡</span>
        </div>
        <div class="card-metric">
          <span id="cpu-val">--</span><span class="card-unit">%</span>
        </div>
        <div class="progress-track">
          <div class="progress-bar" id="cpu-bar" style="width: 0%;"></div>
        </div>
        <div class="card-foot">
          <span>HOST LOAD</span>
          <span id="cpu-state">NOMINAL</span>
        </div>
      </div>

      <!-- RAM -->
      <div class="card">
        <div class="card-top">
          <span class="card-title">System Memory</span>
          <span style="color: var(--cyan);">📊</span>
        </div>
        <div class="card-metric">
          <span id="ram-val">--</span><span class="card-unit">%</span>
        </div>
        <div class="progress-track">
          <div class="progress-bar" id="ram-bar" style="width: 0%;"></div>
        </div>
        <div class="card-foot">
          <span>RAM USAGE</span>
          <span id="ram-state">ACTIVE</span>
        </div>
      </div>

      <!-- Thermals -->
      <div class="card">
        <div class="card-top">
          <span class="card-title">Hardware Thermal</span>
          <span style="color: var(--amber);">🔥</span>
        </div>
        <div class="card-metric">
          <span id="temp-val">--</span><span class="card-unit">°C</span>
        </div>
        <div class="progress-track">
          <div class="progress-bar" id="temp-bar" style="width: 50%;"></div>
        </div>
        <div class="card-foot">
          <span>THERMAL GUARD</span>
          <span id="temp-state" style="color: var(--emerald);">SAFE &lt; 82°C</span>
        </div>
      </div>

      <!-- AI Core -->
      <div class="card">
        <div class="card-top">
          <span class="card-title">Active AI Model</span>
          <span style="color: var(--emerald);">🧠</span>
        </div>
        <div class="card-metric" style="font-size: 1.5rem; word-break: break-all;">
          <span id="model-val">zaine-reflex-7b</span>
        </div>
        <div class="progress-track">
          <div class="progress-bar" style="width: 100%;"></div>
        </div>
        <div class="card-foot">
          <span>PERSONA MODE</span>
          <span id="persona-val" style="color: var(--cyan);">JARVIS</span>
        </div>
      </div>
    </div>

    <!-- Active REST & SSE Endpoints -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/>
          </svg>
          Core Service Endpoints Directory
        </div>
        <div style="display: flex; align-items: center; gap: 0.75rem;">
          <button class="btn-test" id="ping-btn" onclick="testPing()">Test Ping /api/health</button>
          <span id="ping-result" style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--emerald);"></span>
        </div>
      </div>
      <div class="endpoints-list">
        <a href="/api/health" target="_blank" class="endpoint-item">
          <span class="endpoint-link"><span class="endpoint-method">GET</span>/api/health</span>
          <span style="color: var(--text-dim);">Core health & ping</span>
        </a>
        <a href="/api/status" target="_blank" class="endpoint-item">
          <span class="endpoint-link"><span class="endpoint-method">GET</span>/api/status</span>
          <span style="color: var(--text-dim);">Live telemetry & metrics</span>
        </a>
        <a href="/api/queue" target="_blank" class="endpoint-item">
          <span class="endpoint-link"><span class="endpoint-method">GET</span>/api/queue</span>
          <span style="color: var(--text-dim);">Coordinator request queue</span>
        </a>
        <a href="/api/voice/status" target="_blank" class="endpoint-item">
          <span class="endpoint-link"><span class="endpoint-method">GET</span>/api/voice/status</span>
          <span style="color: var(--text-dim);">Voice synthesis engine</span>
        </a>
        <a href="/api/history" target="_blank" class="endpoint-item">
          <span class="endpoint-link"><span class="endpoint-method">GET</span>/api/history</span>
          <span style="color: var(--text-dim);">Episodic memory timeline</span>
        </a>
      </div>
    </div>

    <footer>
      <div>Z.A.I.N.E Neural Engine · Local Autonomous Agent Platform · Confidential & Proprietary to Mateen Sir</div>
    </footer>
  </div>

  <script>
    async function updateTelemetry() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) throw new Error('Status ' + res.status);
        const data = await res.json();

        // Update CPU
        const cpu = data.cpu !== undefined ? Math.round(data.cpu) : 0;
        document.getElementById('cpu-val').textContent = cpu;
        document.getElementById('cpu-bar').style.width = Math.min(cpu, 100) + '%';

        // Update RAM
        const ram = data.ram !== undefined ? Math.round(data.ram) : 0;
        document.getElementById('ram-val').textContent = ram;
        document.getElementById('ram-bar').style.width = Math.min(ram, 100) + '%';

        // Update Temp
        if (data.temperature !== null && data.temperature !== undefined) {
          document.getElementById('temp-val').textContent = Math.round(data.temperature);
          const tBar = Math.min(Math.max((data.temperature - 30) * (100 / 60), 10), 100);
          document.getElementById('temp-bar').style.width = tBar + '%';
        }

        // Update Model & Mode
        if (data.active_model) {
          document.getElementById('model-val').textContent = data.active_model;
        }
        if (data.mode) {
          document.getElementById('persona-val').textContent = data.mode.toUpperCase();
        }

        const badge = document.getElementById('service-status-badge');
        badge.style.borderColor = 'rgba(16, 185, 129, 0.35)';
      } catch (err) {
        console.warn('Telemetry poll error:', err);
      }
    }

    async function testPing() {
      const btn = document.getElementById('ping-btn');
      const result = document.getElementById('ping-result');
      const t0 = performance.now();
      btn.disabled = true;
      btn.textContent = 'Pinging...';
      try {
        const r = await fetch('/api/health');
        const dt = Math.round(performance.now() - t0);
        if (r.ok) {
          result.style.color = '#10b981';
          result.textContent = '200 OK (' + dt + 'ms)';
        } else {
          result.style.color = '#f59e0b';
          result.textContent = 'Status ' + r.status + ' (' + dt + 'ms)';
        }
      } catch (e) {
        result.style.color = '#ef4444';
        result.textContent = 'Ping failed';
      } finally {
        btn.disabled = false;
        btn.textContent = 'Test Ping /api/health';
      }
    }

    // Initial fetch & loop every 3 seconds
    updateTelemetry();
    setInterval(updateTelemetry, 3000);
  </script>
</body>
</html>"""
    return html.replace("{{PORT}}", str(port))


class CoreServiceRequestHandler(BaseHTTPRequestHandler):
    """Headless REST and SSE request dispatcher for Z.A.I.N.E Core Service."""

    def log_message(self, format, *args):
        """Suppress console log noise."""
        return

    @property
    def core_service(self):
        return getattr(self.server, "core_service_instance", None)

    ALLOWED_HOST_REGEX = re.compile(r"^(127\.0\.0\.1|localhost)(:\d+)?$", re.IGNORECASE)
    ALLOWED_ORIGIN_REGEX = re.compile(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", re.IGNORECASE)

    def _validate_host(self) -> bool:
        host = self.headers.get("Host", "").strip()
        if not host or not self.ALLOWED_HOST_REGEX.match(host):
            self.send_error(403, "Forbidden: Invalid Host header")
            return False
        return True

    def _get_allowed_origin(self) -> Optional[str]:
        origin = self.headers.get("Origin", "").strip()
        if origin and self.ALLOWED_ORIGIN_REGEX.match(origin):
            return origin
        return None

    def _set_cors_headers(self):
        allowed_origin = self._get_allowed_origin()
        if allowed_origin:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Zaine-Token, Authorization")

    def _validate_auth(self) -> bool:
        if not self.core_service or not getattr(self.core_service, "auth_token", None):
            return True
        token = self.headers.get("X-Zaine-Token", "").strip()
        if not token or token != self.core_service.auth_token:
            self._send_json(401, {"ok": False, "error": "Unauthorized: Missing or invalid X-Zaine-Token"})
            return False
        return True

    def do_OPTIONS(self):
        if not self._validate_host():
            return
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def _send_json(self, status_code: int, data: dict):
        try:
            payload = json.dumps(data).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def _send_html(self, status_code: int, html_str: str):
        try:
            payload = html_str.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def do_GET(self):
        if not self._validate_host():
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 0. Interactive Web Dashboard / HUD (/, /index.html, /hud, /dashboard)
        if path in ("/", "/index.html", "/hud", "/dashboard"):
            port = self.core_service.port if self.core_service else 7860
            self._send_html(200, _render_hud_dashboard_html(port))
            return

        # 1. Core Service Health Check (/api/health)
        if path == "/api/health":
            port = self.core_service.port if self.core_service else 7860
            self._send_json(200, {
                "ok": True,
                "status": "online",
                "port": port,
                "timestamp": time.time(),
            })
            return

        # 2. Coordinator Queue Telemetry (/api/queue)
        if path == "/api/queue":
            self._send_json(200, _coordinator.get_queue_telemetry())
            return

        # 3. Request Status Check (/api/requests/<id>)
        if path.startswith("/api/requests/"):
            req_id = path[len("/api/requests/"):].strip()
            self._send_json(200, _coordinator.get_request_status(req_id))
            return

        # 4. Status endpoint (/api/status)
        if path == "/api/status":
            try:
                telem = get_system_telemetry()
            except Exception as e:
                telem = {"cpu": 0.0, "ram": 0.0, "error": str(e)}
            agent = self.core_service.agent if self.core_service else None
            from core_router import router
            active_model = getattr(agent, "model", None) or router.reflex_model
            raw_status = self.core_service.current_status if self.core_service else "online"
            status_val = "online" if raw_status in ("idle", "ready", "online") else raw_status
            telem["ok"] = True
            telem["status"] = status_val
            telem["mode"] = self.core_service.current_mode if self.core_service else "jarvis"
            telem["active_model"] = active_model
            telem["port"] = self.core_service.port if self.core_service else 7860
            self._send_json(200, telem)
            return

        # 5. Active Persona Mode (/api/mode)
        if path == "/api/mode":
            mode = self.core_service.current_mode if self.core_service else "jarvis"
            self._send_json(200, {"status": "ok", "mode": mode})
            return

        # 6. Voice State Machine Status (/api/voice/status)
        if path == "/api/voice/status":
            self._send_json(200, {
                "status": "ok",
                "voice_state": voice.get_voice_state(),
                "enabled": voice.is_voice_enabled(),
            })
            return

        # 7. Conversation Episodes History (/api/history)
        if path == "/api/history":
            if not self._validate_auth():
                return
            try:
                import memory
                conn = memory._get_memory_conn()
                rows = conn.execute(
                    "SELECT id, session_start, session_end, topic_summary, key_points, keywords, created_at FROM conversation_episodes ORDER BY id DESC LIMIT 15"
                ).fetchall()
                conn.close()
                episodes = [
                    {
                        "id": r[0],
                        "session_start": r[1],
                        "session_end": r[2],
                        "topic_summary": r[3],
                        "key_points": r[4],
                        "keywords": r[5],
                        "created_at": r[6],
                    }
                    for r in rows
                ]
            except Exception:
                episodes = []
            self._send_json(200, {"status": "ok", "episodes": episodes})
            return

        # 8. User / Lockscreen Status (/api/lockscreen/status)
        if path == "/api/lockscreen/status":
            try:
                from face_id import get_active_user
                usr = get_active_user()
            except Exception:
                usr = {"name": "Mateen Sir", "role": "admin"}
            self._send_json(200, {"status": "ok", "user": usr})
            return

        # 9. Pending Approvals (/api/approval/pending or /api/approvals)
        if path in ("/api/approval/pending", "/api/approvals"):
            from approval import ApprovalRegistry
            self._send_json(200, {"ok": True, "pending": ApprovalRegistry.list_pending()})
            return

        self.send_error(404, "Endpoint not found on Z.A.I.N.E Core Service")

    def do_POST(self):
        if not self._validate_host():
            return
        if not self._validate_auth():
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            req_data = json.loads(body)
        except Exception:
            req_data = {}

        # 1. Persona Mode Toggle (/api/mode)
        if path == "/api/mode":
            target_mode = req_data.get("mode", "").lower().strip()
            curr = self.core_service.current_mode if self.core_service else "jarvis"
            enable = (target_mode == "ultron") if target_mode else (curr != "ultron")
            from tools import toggle_ultron_mode
            res_str = toggle_ultron_mode(enable)
            active_mode = "ultron" if enable else "jarvis"
            if self.core_service:
                self.core_service.set_mode(active_mode)
            self._send_json(200, {"status": "ok", "mode": active_mode, "message": res_str})
            return

        # 2. Voice Mode Toggle (/api/voice/toggle)
        if path == "/api/voice/toggle":
            enable = req_data.get("enable")
            if enable is None:
                enable = not voice.is_voice_enabled()
            if enable:
                ok, msg = voice.enable_voice()
            else:
                ok, msg = voice.disable_voice()
            self._send_json(200, {
                "status": "ok",
                "voice_state": voice.get_voice_state(),
                "enabled": voice.is_voice_enabled(),
                "message": msg,
            })
            return

        # 3. Context Clear (/api/context/clear)
        if path == "/api/context/clear":
            if self.core_service and self.core_service.agent:
                if hasattr(self.core_service.agent, "clear_history"):
                    self.core_service.agent.clear_history()
                elif hasattr(self.core_service.agent, "reset_context"):
                    self.core_service.agent.reset_context()
            self._send_json(200, {"status": "ok", "message": "Conversation history cleared."})
            return

        # 4. Approval Response (/api/approval/respond)
        if path == "/api/approval/respond":
            proposal_id = req_data.get("proposal_id", "").strip()
            decision = req_data.get("decision", "").strip().lower()
            note = req_data.get("note", "").strip()

            if not proposal_id or not decision:
                self.send_error(400, "Missing proposal_id or decision")
                return

            from approval import ApprovalRegistry
            if decision in ("approve", "approved", "yes", "y"):
                success, msg = ApprovalRegistry.approve(proposal_id, note=note or "Authorized via TUI")
                status = "APPROVED" if success else "ERROR"
            elif decision in ("deny", "denied", "no", "n"):
                success, msg = ApprovalRegistry.deny(proposal_id, note=note or "Denied via TUI")
                status = "DENIED" if success else "ERROR"
            else:
                self.send_error(400, f"Invalid decision '{decision}'. Expected 'approve' or 'deny'.")
                return

            self._send_json(200 if success else 400, {
                "ok": success,
                "status": status,
                "proposal_id": proposal_id,
                "message": msg,
            })
            return

        # 5. Request Cancellation (/api/chat/cancel or /api/cancel)
        if path in ("/api/chat/cancel", "/api/cancel"):
            target_req_id = req_data.get("request_id", "").strip()
            if target_req_id:
                _coordinator.cancel_request(target_req_id)
            from approval import ApprovalRegistry
            for p in ApprovalRegistry.list_pending():
                ApprovalRegistry.deny(p["id"], note="Cancelled via client abort")
            if self.core_service:
                self.core_service.set_status("idle")
            self._send_json(200, {"ok": True, "request_id": target_req_id, "status": "cancelled"})
            return

        # 6. Standard Chat (/api/chat)
        if path == "/api/chat":
            user_msg = req_data.get("message", "").strip()
            if not user_msg:
                self.send_error(400, "Message empty")
                return

            client = req_data.get("client", "cli")
            request_id = str(req_data.get("request_id") or uuid.uuid4())

            claim_status, m_req, cached = _coordinator.claim_request(request_id=request_id, client=client)

            if claim_status == "completed":
                self._send_json(200, cached)
                return

            if claim_status == "in_flight":
                finished = m_req.wait_for_completion(timeout=120)
                if not finished:
                    self.send_error(504, "In-flight duplicate request timed out")
                    return
                if m_req.state == "failed":
                    self.send_error(500, f"Error processing chat: {m_req.error or 'Failed'}")
                    return
                if m_req.result is not None:
                    self._send_json(200, m_req.result)
                    return
                self.send_error(500, "In-flight duplicate request finished with empty result")
                return

            # claim_status == "claimed"
            was_queued = False
            waited_seconds = 0.0
            if m_req.state == "queued":
                was_queued = True
                if self.core_service:
                    self.core_service.set_status("queued")
                turn_ok = m_req.wait_for_turn(timeout=120.0)
                if not turn_ok:
                    _coordinator.fail_request(request_id, "Timed out waiting in queue")
                    self.send_error(504, "Queued request timed out waiting for turn")
                    return
                waited_seconds = round(time.time() - m_req.queued_at, 3)

            if self.core_service:
                self.core_service.set_status("thinking")
            agent = self.core_service.agent if self.core_service else None
            try:
                if agent:
                    reply = agent.chat(user_msg)
                    tool_called = getattr(agent, "last_tool_called", None)
                    mode = "ultron" if getattr(agent, "ultron_mode", False) else "jarvis"
                else:
                    reply = "CoreService: Agent engine not bound."
                    tool_called = None
                    mode = "jarvis"

                resp_dict = {
                    "ok": True,
                    "reply": reply,
                    "tool_called": tool_called,
                    "mode": mode,
                    "request_id": request_id,
                    "queued": was_queued,
                    "waited_seconds": waited_seconds,
                }
                _coordinator.complete_request(request_id, resp_dict)
            except Exception as e:
                _coordinator.fail_request(request_id, str(e))
                if self.core_service:
                    self.core_service.set_status("idle")
                self.send_error(500, f"Error processing chat: {e}")
                return

            if self.core_service:
                self.core_service.set_status("idle")
            self._send_json(200, resp_dict)
            return

        # 5. Streaming Chat (/api/chat/stream)
        if path == "/api/chat/stream":
            user_msg = req_data.get("message", "").strip()
            if not user_msg:
                self.send_error(400, "Message empty")
                return

            client = req_data.get("client", "terminal-ui")
            request_id = str(req_data.get("request_id") or uuid.uuid4())

            claim_status, m_req, cached = _coordinator.claim_request(request_id=request_id, client=client)

            if claim_status == "completed":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(f"data: {json.dumps({'type': 'done', **cached})}\n\n".encode("utf-8"))
                self.wfile.flush()
                return

            if claim_status == "in_flight":
                finished = m_req.wait_for_completion(timeout=120)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                if not finished:
                    self.wfile.write(f"data: {json.dumps({'type': 'error', 'message': 'In-flight duplicate request timed out'})}\n\n".encode("utf-8"))
                elif m_req.state == "failed":
                    self.wfile.write(f"data: {json.dumps({'type': 'error', 'message': m_req.error or 'Failed'})}\n\n".encode("utf-8"))
                elif m_req.result is not None:
                    self.wfile.write(f"data: {json.dumps({'type': 'done', **m_req.result})}\n\n".encode("utf-8"))
                else:
                    self.wfile.write(f"data: {json.dumps({'type': 'error', 'message': 'Empty in-flight result'})}\n\n".encode("utf-8"))
                self.wfile.flush()
                return

            # claim_status == "claimed": Send SSE headers immediately
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self._set_cors_headers()
            self.end_headers()

            was_queued = False
            waited_seconds = 0.0
            if m_req.state == "queued":
                was_queued = True
                queue_evt = {
                    "type": "queued",
                    "status": "queued",
                    "position": m_req.position,
                    "request_id": request_id,
                }
                self.wfile.write(f"data: {json.dumps(queue_evt)}\n\n".encode("utf-8"))
                self.wfile.flush()
                if self.core_service:
                    self.core_service.set_status("queued")

                turn_ok = m_req.wait_for_turn(timeout=120.0)
                if not turn_ok:
                    _coordinator.fail_request(request_id, "Timed out waiting in queue")
                    err_payload = json.dumps({"type": "error", "message": "Queued request timed out waiting for turn"})
                    self.wfile.write(f"data: {err_payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    return
                waited_seconds = round(time.time() - m_req.queued_at, 3)

            run_evt = {
                "type": "running",
                "status": "running",
                "request_id": request_id,
                "waited_seconds": waited_seconds if was_queued else 0.0,
            }
            self.wfile.write(f"data: {json.dumps(run_evt)}\n\n".encode("utf-8"))
            # Send loading heartbeat to reset client first-token silence timer
            loading_evt = json.dumps({"type": "heartbeat", "stage": "loading", "request_id": request_id})
            self.wfile.write(f"data: {loading_evt}\n\n".encode("utf-8"))
            self.wfile.flush()

            if self.core_service:
                self.core_service.set_status("thinking")
            agent = self.core_service.agent if self.core_service else None

            if not agent:
                err_payload = json.dumps({"type": "error", "message": "Agent engine not bound to Core Service."})
                self.wfile.write(f"data: {err_payload}\n\n".encode("utf-8"))
                self.wfile.flush()
                _coordinator.fail_request(request_id, "Agent not bound")
                if self.core_service:
                    self.core_service.set_status("idle")
                return

            from approval import (
                set_approval_listener,
                clear_approval_listener,
                set_current_request_id,
            )

            wfile_lock = threading.Lock()
            def safe_write(raw_bytes: bytes) -> bool:
                with wfile_lock:
                    try:
                        self.wfile.write(raw_bytes)
                        self.wfile.flush()
                        return True
                    except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
                        return False
                    except Exception:
                        return False

            def stream_approval_listener(stage: str, tool_name: str, data: Any) -> bool:
                payload_data = data if isinstance(data, (dict, list, int, float, bool)) else str(data)[:2000]
                event_payload = json.dumps({
                    "type": "tool_event",
                    "stage": stage,
                    "tool": tool_name,
                    "data": payload_data,
                })
                safe_write(b": ping\n\n")
                return safe_write(f"data: {event_payload}\n\n".encode("utf-8"))

            def on_tool_event(stage: str, tool_name: str, data: Any):
                payload_data = data if isinstance(data, (dict, list, int, float, bool)) else str(data)[:2000]
                event_payload = json.dumps({
                    "type": "tool_event",
                    "stage": stage,
                    "tool": tool_name,
                    "data": payload_data,
                })
                safe_write(b": ping\n\n")
                safe_write(f"data: {event_payload}\n\n".encode("utf-8"))

            set_current_request_id(request_id)
            set_approval_listener(stream_approval_listener)

            full_reply_parts = []
            try:
                for sentence in agent.chat_stream(user_msg, on_tool_event=on_tool_event):
                    if _coordinator.is_request_cancelled(request_id):
                        break
                    full_reply_parts.append(sentence)
                    chunk_payload = json.dumps({"type": "token", "token": sentence, "content": sentence, "text": sentence})
                    if not safe_write(f"data: {chunk_payload}\n\n".encode("utf-8")):
                        _coordinator.cancel_request(request_id)
                        break
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
                _coordinator.cancel_request(request_id)
                if self.core_service:
                    self.core_service.set_status("idle")
                return
            except Exception as e:
                _coordinator.fail_request(request_id, str(e))
                try:
                    err_payload = json.dumps({"type": "error", "message": str(e)})
                    safe_write(f"data: {err_payload}\n\n".encode("utf-8"))
                except Exception:
                    pass
                if self.core_service:
                    self.core_service.set_status("idle")
                return
            finally:
                clear_approval_listener()

            tool_called = getattr(agent, "last_tool_called", None)
            mode = "ultron" if getattr(agent, "ultron_mode", False) else "jarvis"
            full_reply = " ".join(full_reply_parts)

            final_dict = {
                "ok": True,
                "reply": full_reply,
                "tool_called": tool_called,
                "mode": mode,
                "request_id": request_id,
                "queued": was_queued,
                "waited_seconds": waited_seconds,
            }
            _coordinator.complete_request(request_id, final_dict)

            if self.core_service:
                self.core_service.set_status("idle")
            self.wfile.write(f"data: {json.dumps({'type': 'done', **final_dict})}\n\n".encode("utf-8"))
            self.wfile.flush()
            return

        self.send_error(404, "Endpoint not found on Z.A.I.N.E Core Service")


class ZaineHTTPServer(ThreadingHTTPServer):
    core_service_instance: Any = None

    def handle_error(self, request, client_address):
        exctype, value, tb = sys.exc_info()
        if exctype in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            return
        super().handle_error(request, client_address)


class CoreService:
    """
    Unified Headless Core Agent Service for Z.A.I.N.E.
    Owns ZaineAgent, Request Coordinator, and multi-threaded HTTP server.
    """

    def __init__(self, agent: Optional[ZaineAgent] = None, port: int = 7860):
        self.agent = agent or ZaineAgent()
        self.port = port
        self.server: Optional[ZaineHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.current_status: str = "idle"
        self.current_mode: str = "jarvis"
        self.auth_token: str = uuid.uuid4().hex
        self.stop_event = threading.Event()

    def set_status(self, status: str):
        self.current_status = status

    def set_mode(self, mode: str):
        self.current_mode = mode
        if self.agent:
            self.agent.set_ultron_mode(mode == "ultron")

    def _write_core_info(self, status: str = "online"):
        """Persists connection metadata to .zaine_core.json."""
        try:
            core_file = PROJECT_ROOT / ".zaine_core.json"
            data = {
                "port": self.port,
                "pid": os.getpid(),
                "status": status,
                "auth_token": self.auth_token,
                "updated_at": time.time(),
            }
            core_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[CoreService Info Notice]: {e}")

    def start_server(self):
        """Binds multi-threaded HTTP server to port 7860 (or first free port in range)."""
        for p in range(self.port, self.port + 10):
            try:
                self.server = ZaineHTTPServer(("127.0.0.1", p), CoreServiceRequestHandler)
                self.server.core_service_instance = self
                self.port = p
                break
            except OSError:
                continue

        if not self.server:
            raise RuntimeError(f"Could not bind Core Service on ports {self.port} to {self.port + 10}")

        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            name="ZaineCoreServer",
            daemon=True,
        )
        self.server_thread.start()
        self._write_core_info(status="online")

    def stop(self):
        """Cleanly shuts down the server and updates .zaine_core.json."""
        self.stop_event.set()
        self._write_core_info(status="offline")
        if self.server:
            try:
                self.server.shutdown()
            except Exception:
                pass


_active_core_service: Optional[CoreService] = None


def get_core_service() -> Optional[CoreService]:
    """Returns the globally active CoreService instance if started."""
    global _active_core_service
    return _active_core_service


def set_active_core_service(service: CoreService):
    """Sets the globally active CoreService instance."""
    global _active_core_service
    _active_core_service = service
