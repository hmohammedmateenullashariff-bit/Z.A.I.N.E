/**
 * arc_reactor.js - Physically Weighted Living Arc Reactor Canvas Engine
 * 360x360 px canvas with spring-damper rotational dynamics and 3-band FFT response.
 * Implements Gemini Argon 4 High specifications:
 * - 4 Mechanical Layers: Central Core, 12-Segment Stator, Counter-Rotating Gimbals, Bezel.
 * - Angular Acceleration: alpha = (torque - damping * omega) / inertia
 * - Subagent Signatures: Zaine, Edith, Friday, Ultron, DUM-E & U.
 * - Offscreen glow canvas caching for high performance.
 */

class LivingArcReactor {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.size = 360;
    this.center = this.size / 2;

    // Physical state
    this.omega = 0.02; // Angular velocity (rad/s)
    this.angleInner = 0.0;
    this.angleOuter = 0.0;
    this.torque = 0.0;
    this.inertia = 2.2;
    this.damping = 0.88;

    // Frequency bands (0.0 to 1.0)
    this.fftSub = 0.0;  // 80 - 250 Hz (plasma bloom)
    this.fftMid = 0.0;  // 250 - 2500 Hz (stator displacement)
    this.fftHigh = 0.0; // 2.5 - 8 kHz (telemetry jitter)

    // Persona settings
    this.persona = 'zaine';
    this.palette = {
      primary: '#00E5FF',
      secondary: '#0074D9',
      glow: 'rgba(0, 229, 255, 0.4)',
      core: '#E0F7FA'
    };

    this.isActive = false;
    this.lastTime = performance.now();
    this.targetFps = 30; // 30 FPS idle, 60 FPS active

    // Offscreen glow cache
    this._initOffscreenCache();
    this._startLoop();
  }

  _initOffscreenCache() {
    this.offscreen = document.createElement('canvas');
    this.offscreen.width = this.size;
    this.offscreen.height = this.size;
    this.offCtx = this.offscreen.getContext('2d');
  }

  setPersona(name) {
    this.persona = (name || 'zaine').toLowerCase();
    switch (this.persona) {
      case 'edith':
        this.palette = { primary: '#FFB300', secondary: '#FF8F00', glow: 'rgba(255, 179, 0, 0.45)', core: '#FFF8E1' };
        this.inertia = 1.2;
        this.damping = 0.70;
        break;
      case 'friday':
        this.palette = { primary: '#2979FF', secondary: '#1565C0', glow: 'rgba(41, 121, 255, 0.45)', core: '#E3F2FD' };
        this.inertia = 1.6;
        this.damping = 0.92;
        break;
      case 'ultron':
        this.palette = { primary: '#FF1744', secondary: '#D50000', glow: 'rgba(255, 23, 68, 0.55)', core: '#FFEBEE' };
        this.inertia = 0.8;
        this.damping = 0.60;
        break;
      case 'dume':
      case 'dum-e':
        this.palette = { primary: '#FFD600', secondary: '#F57F17', glow: 'rgba(255, 214, 0, 0.4)', core: '#FFFDE7' };
        this.inertia = 3.5;
        this.damping = 0.95;
        break;
      case 'zaine':
      default:
        this.palette = { primary: '#00E5FF', secondary: '#0074D9', glow: 'rgba(0, 229, 255, 0.45)', core: '#E0F7FA' };
        this.inertia = 2.4;
        this.damping = 0.88;
        break;
    }
  }

  setAudioTelemetry(sub, mid, high) {
    this.fftSub = Math.min(1.0, Math.max(0.0, sub));
    this.fftMid = Math.min(1.0, Math.max(0.0, mid));
    this.fftHigh = Math.min(1.0, Math.max(0.0, high));
    this.torque = this.fftMid * 0.15 + this.fftSub * 0.10;
  }

  setActive(active) {
    this.isActive = !!active;
    this.targetFps = this.isActive ? 60 : 30;
  }

  _startLoop() {
    const loop = (now) => {
      const dt = (now - this.lastTime) / 1000.0;
      const minInterval = 1000.0 / this.targetFps;

      if (now - this.lastTime >= minInterval) {
        this._updatePhysics(Math.min(0.1, dt));
        this._render();
        this.lastTime = now;
      }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  _updatePhysics(dt) {
    // Angular acceleration alpha = (torque - damping * omega) / inertia
    const alpha = (this.torque - this.damping * this.omega) / this.inertia;
    this.omega += alpha * dt;

    if (this.persona === 'edith') {
      // 30 degree mechanical stepper ratcheting
      const step = Math.PI / 6;
      this.angleInner += this.omega * dt;
      this.angleOuter = Math.round(this.angleInner / step) * step;
    } else if (this.persona === 'ultron') {
      // Stochastic erratic jitter & reversals
      const jitter = (Math.random() - 0.5) * 0.05 * (this.fftHigh + 0.2);
      this.angleInner += (this.omega + jitter) * dt;
      this.angleOuter -= (this.omega * 1.4 + jitter) * dt;
    } else {
      // Smooth counter-rotation
      this.angleInner += this.omega * dt;
      this.angleOuter -= (this.omega * 0.7) * dt;
    }
  }

  _render() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.size, this.size);
    const c = this.center;

    ctx.save();
    ctx.translate(c, c);

    // Layer 1: Outer Telemetry Bezel
    this._drawOuterBezel(ctx);

    // Layer 2: Counter-Rotating Gyro Gimbals
    this._drawGimbals(ctx);

    // Layer 3: 12-Segment Stator Ring
    this._drawStatorRing(ctx);

    // Layer 4: Central Plasma Core
    this._drawPlasmaCore(ctx);

    ctx.restore();
  }

  _drawOuterBezel(ctx) {
    const r = 160;
    ctx.save();
    ctx.rotate(this.angleOuter * 0.3);

    // Outer faint guide ring
    ctx.strokeStyle = this.palette.secondary;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.stroke();

    // 60 tick marks
    ctx.strokeStyle = this.palette.primary;
    for (let i = 0; i < 60; i++) {
      const angle = (i * Math.PI * 2) / 60;
      const isMajor = i % 5 === 0;
      const len = isMajor ? (12 + this.fftHigh * 6) : 5;
      const x1 = Math.cos(angle) * (r - len);
      const y1 = Math.sin(angle) * (r - len);
      const x2 = Math.cos(angle) * r;
      const y2 = Math.sin(angle) * r;

      ctx.lineWidth = isMajor ? 2.0 : 1.0;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }
    ctx.restore();
  }

  _drawGimbals(ctx) {
    const rInner = 120;
    const rOuter = 138;

    // Outer gimbal (counter-clockwise)
    ctx.save();
    ctx.rotate(this.angleOuter);
    ctx.strokeStyle = this.palette.primary;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(0, 0, rOuter, 0.2, Math.PI - 0.2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(0, 0, rOuter, Math.PI + 0.2, Math.PI * 2 - 0.2);
    ctx.stroke();
    ctx.restore();

    // Inner gimbal (clockwise)
    ctx.save();
    ctx.rotate(this.angleInner);
    ctx.strokeStyle = this.palette.secondary;
    ctx.lineWidth = 2.0;
    for (let i = 0; i < 3; i++) {
      const a = (i * Math.PI * 2) / 3;
      ctx.beginPath();
      ctx.arc(0, 0, rInner, a + 0.15, a + (Math.PI * 2) / 3 - 0.15);
      ctx.stroke();
    }
    ctx.restore();
  }

  _drawStatorRing(ctx) {
    const baseR = 85;
    const displacement = this.fftMid * 12; // Expands radially with mid-range sound
    const r = baseR + displacement;

    ctx.save();
    ctx.rotate(this.angleInner * 0.5);

    // 12 copper stator coil segments
    for (let i = 0; i < 12; i++) {
      const a = (i * Math.PI * 2) / 12;
      ctx.save();
      ctx.rotate(a);
      ctx.translate(0, -r);

      // Coils
      ctx.fillStyle = this.palette.secondary;
      ctx.fillRect(-6, -8, 12, 16);

      // Core cap
      ctx.fillStyle = this.palette.primary;
      ctx.shadowColor = this.palette.glow;
      ctx.shadowBlur = 8 + this.fftSub * 10;
      ctx.fillRect(-8, 6, 16, 4);

      ctx.restore();
    }
    ctx.restore();
  }

  _drawPlasmaCore(ctx) {
    const baseR = 42;
    const bloom = baseR + this.fftSub * 18; // Pulses with sub-bass

    ctx.save();
    const grad = ctx.createRadialGradient(0, 0, 4, 0, 0, bloom);
    grad.addColorStop(0, this.palette.core);
    grad.addColorStop(0.3, this.palette.primary);
    grad.addColorStop(0.7, this.palette.secondary);
    grad.addColorStop(1, 'rgba(0,0,0,0)');

    ctx.fillStyle = grad;
    ctx.shadowColor = this.palette.glow;
    ctx.shadowBlur = 24 + this.fftSub * 20;

    ctx.beginPath();
    ctx.arc(0, 0, bloom, 0, Math.PI * 2);
    ctx.fill();

    // Inner triangular / circular reactor emitter
    ctx.strokeStyle = this.palette.core;
    ctx.lineWidth = 2.0;
    ctx.beginPath();
    ctx.arc(0, 0, 18, 0, Math.PI * 2);
    ctx.stroke();

    ctx.restore();
  }
}

window.LivingArcReactor = LivingArcReactor;

