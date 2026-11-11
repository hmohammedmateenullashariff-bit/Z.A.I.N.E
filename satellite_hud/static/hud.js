/**
 * hud.js - Controller for the Z.A.I.N.E Satellite HUD
 * Bridges LivingArcReactor, WebAudio microphone analyser, and Server-Sent Events.
 */

document.addEventListener('DOMContentLoaded', () => {
  const reactor = new LivingArcReactor('arcCanvas');
  let audioContext = null;
  let analyser = null;
  let micStream = null;

  // Elements
  const statusEl = document.getElementById('coreStatus');
  const personaEl = document.getElementById('activePersona');
  const vramEl = document.getElementById('vramUsage');
  const jobStatusEl = document.getElementById('jobTelemetry');
  const personaBtns = document.querySelectorAll('.btn-persona');

  // Persona switching
  personaBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      const p = btn.getAttribute('data-persona');
      personaBtns.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');

      reactor.setPersona(p);
      if (personaEl) personaEl.textContent = p.toUpperCase();

      // Play procedural earcon
      if (window.ZaineAudio) {
        window.ZaineAudio.playEarcon(p);
      }
    });
  });

  // Microhpone FFT setup
  function initMicAnalyzer() {
    if (audioContext) return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      audioContext = new AudioCtx();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;

      navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
        micStream = stream;
        const source = audioContext.createMediaStreamSource(stream);
        source.connect(analyser);
        pollAudio();
      }).catch((err) => {
        console.warn('Microphone access for HUD audio analysis unavailable:', err);
      });
    } catch (e) {
      console.warn('Web Audio initialization error:', e);
    }
  }

  function pollAudio() {
    if (!analyser) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(data);

    // Split 3 frequency bands
    // 0 - 6 bins: Sub-bass (approx 80 - 250 Hz)
    let subSum = 0;
    for (let i = 1; i <= 6; i++) subSum += data[i] || 0;
    const sub = subSum / (6 * 255.0);

    // 7 - 55 bins: Mid-range (approx 250 - 2500 Hz)
    let midSum = 0;
    for (let i = 7; i <= 55; i++) midSum += data[i] || 0;
    const mid = midSum / (49 * 255.0);

    // 56 - 127 bins: Highs (approx 2.5 - 8 kHz)
    let highSum = 0;
    for (let i = 56; i < 128; i++) highSum += data[i] || 0;
    const high = highSum / (72 * 255.0);

    reactor.setAudioTelemetry(sub, mid, high);
    reactor.setActive(mid > 0.08 || sub > 0.08);

    requestAnimationFrame(pollAudio);
  }

  // Poll system status from /api/status
  function pollStatus() {
    fetch('/api/status')
      .then((r) => r.json())
      .then((data) => {
        if (statusEl) statusEl.textContent = data.status || 'ONLINE';
        if (vramEl && data.gpu) {
          vramEl.textContent = `${data.gpu.vram_used_mb || 0} MB / ${data.gpu.vram_total_mb || 4096} MB`;
        }
        if (data.active_persona && personaEl) {
          personaEl.textContent = data.active_persona.toUpperCase();
          reactor.setPersona(data.active_persona);
        }
      })
      .catch(() => {
        if (statusEl) statusEl.textContent = 'STANDBY';
      });
  }

  // SSE stream for Armory Jobs (/api/jobs/stream)
  function connectJobTelemetry() {
    try {
      const evtSource = new EventSource('/api/jobs/stream');
      evtSource.addEventListener('job_started', (e) => {
        const data = JSON.parse(e.data);
        if (jobStatusEl) jobStatusEl.textContent = `Running ${data.job_id}...`;
        if (window.ZaineAudio) window.ZaineAudio.playEarcon('handoff');
      });
      evtSource.addEventListener('job_succeeded', (e) => {
        const data = JSON.parse(e.data);
        if (jobStatusEl) jobStatusEl.textContent = `${data.job_id} Done`;
        if (window.ZaineAudio) window.ZaineAudio.playEarcon('friday');
      });
      evtSource.addEventListener('job_failed', (e) => {
        const data = JSON.parse(e.data);
        if (jobStatusEl) jobStatusEl.textContent = `${data.job_id} Error`;
        if (window.ZaineAudio) window.ZaineAudio.playEarcon('reflect');
      });
      evtSource.onerror = () => {
        evtSource.close();
        setTimeout(connectJobTelemetry, 5000);
      };
    } catch (e) {
      console.warn('Telemetry SSE connection notice:', e);
    }
  }

  // SSE stream for Real-Time Arc Reactor HUD Telemetry (/api/hud/events)
  function connectHudEvents() {
    try {
      const hudSource = new EventSource('/api/hud/events');
      hudSource.onmessage = (e) => {
        try {
          const state = JSON.parse(e.data);
          if (vramEl && state.vram_used_mb !== undefined) {
            vramEl.textContent = `${Math.round(state.vram_used_mb)} MB / ${state.vram_total_mb || 4096} MB`;
          }
          if (personaEl && state.active_subagent) {
            personaEl.textContent = state.active_subagent.toUpperCase();
            reactor.setPersona(state.active_subagent);
          }
          if (statusEl && state.system_status) {
            statusEl.textContent = state.system_status;
          }
          if (state.breaker_state === 'OPEN') {
            reactor.setActive(true);
            if (window.ZaineAudio) window.ZaineAudio.playEarcon('reflect');
          }
        } catch (err) {}
      };
      hudSource.onerror = () => {
        hudSource.close();
        setTimeout(connectHudEvents, 5000);
      };
    } catch (e) {
      console.warn('HUD SSE connection notice:', e);
    }
  }

  // User click on page initiates AudioContext (browser autoplay policy)
  document.body.addEventListener('click', () => {
    initMicAnalyzer();
  }, { once: true });

  setInterval(pollStatus, 3000);
  pollStatus();
  connectJobTelemetry();
  connectHudEvents();
});

