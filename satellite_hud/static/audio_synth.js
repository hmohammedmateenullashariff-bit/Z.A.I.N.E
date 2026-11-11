/**
 * audio_synth.js - Procedural WebAudio Sound Generator for Z.A.I.N.E
 * 0 KB disk footprint - pure algorithmic sound synthesis.
 * Implements Gemini Argon 4 High sensory specification:
 * - wake: 110ms upward sine (440 -> 587 Hz)
 * - handoff: 95ms dual-impulse relay chirp (660 Hz)
 * - edith: 130ms double-click latch
 * - friday: 220ms high-Q sonar ping (880 Hz with resonance)
 * - ultron: 240ms sub-bass saw drop (92 -> 48 Hz)
 * - reflect: 260ms muted descending minor third
 */

class ZaineAudioSynth {
  constructor() {
    this.ctx = null;
    this.masterGain = null;
    this.panner = null;
  }

  _initContext() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AudioCtx();
      this.masterGain = this.ctx.createGain();
      this.masterGain.gain.setValueAtTime(0.3, this.ctx.currentTime);

      if (this.ctx.createStereoPanner) {
        this.panner = this.ctx.createStereoPanner();
        this.masterGain.connect(this.panner);
        this.panner.connect(this.ctx.destination);
      } else {
        this.masterGain.connect(this.ctx.destination);
      }
    }
    if (this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  setPan(val) {
    if (this.panner) {
      this.panner.pan.setValueAtTime(Math.max(-1, Math.min(1, val)), this.ctx ? this.ctx.currentTime : 0);
    }
  }

  playEarcon(name, pan = 0.0) {
    try {
      this._initContext();
      this.setPan(pan);
      const now = this.ctx.currentTime;

      switch (name.toLowerCase()) {
        case 'wake':
        case 'zaine': {
          // 110ms upward sine chirp (440 -> 587 Hz)
          const osc = this.ctx.createOscillator();
          const gain = this.ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(440, now);
          osc.frequency.exponentialRampToValueAtTime(587.33, now + 0.11);
          gain.gain.setValueAtTime(0.01, now);
          gain.gain.linearRampToValueAtTime(0.35, now + 0.02);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.11);
          osc.connect(gain);
          gain.connect(this.masterGain);
          osc.start(now);
          osc.stop(now + 0.11);
          break;
        }

        case 'handoff': {
          // 95ms dual-impulse relay chirp (660 Hz)
          [0, 0.045].forEach((offset) => {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(660, now + offset);
            gain.gain.setValueAtTime(0.25, now + offset);
            gain.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.04);
            osc.connect(gain);
            gain.connect(this.masterGain);
            osc.start(now + offset);
            osc.stop(now + offset + 0.04);
          });
          break;
        }

        case 'edith': {
          // 130ms double-click latch
          [0, 0.06].forEach((offset, idx) => {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            osc.type = 'square';
            osc.frequency.setValueAtTime(idx === 0 ? 1200 : 1600, now + offset);
            gain.gain.setValueAtTime(0.18, now + offset);
            gain.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.035);
            osc.connect(gain);
            gain.connect(this.masterGain);
            osc.start(now + offset);
            osc.stop(now + offset + 0.035);
          });
          break;
        }

        case 'friday': {
          // 220ms high-resonance sonar ping (880 Hz with exponential decay)
          const osc = this.ctx.createOscillator();
          const gain = this.ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(880, now);
          gain.gain.setValueAtTime(0.4, now);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);
          osc.connect(gain);
          gain.connect(this.masterGain);
          osc.start(now);
          osc.stop(now + 0.22);
          break;
        }

        case 'ultron': {
          // 240ms sub-bass saw drop (92 -> 48 Hz)
          const osc = this.ctx.createOscillator();
          const gain = this.ctx.createGain();
          osc.type = 'sawtooth';
          osc.frequency.setValueAtTime(92.5, now);
          osc.frequency.exponentialRampToValueAtTime(48.0, now + 0.24);
          gain.gain.setValueAtTime(0.5, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.24);
          osc.connect(gain);
          gain.connect(this.masterGain);
          osc.start(now);
          osc.stop(now + 0.24);
          break;
        }

        case 'reflect':
        case 'fail': {
          // 260ms muted descending minor third (440 -> 370 Hz)
          const osc = this.ctx.createOscillator();
          const gain = this.ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(440, now);
          osc.frequency.linearRampToValueAtTime(369.99, now + 0.26);
          gain.gain.setValueAtTime(0.3, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.26);
          osc.connect(gain);
          gain.connect(this.masterGain);
          osc.start(now);
          osc.stop(now + 0.26);
          break;
        }
      }
    } catch (e) {
      console.warn('Procedural audio error:', e);
    }
  }
}

window.ZaineAudio = new ZaineAudioSynth();

