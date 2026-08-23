/**
 * Per-flap click scheduling. Each flap event gets its own short click,
 * scheduled at the engine timestamp it actually happened at — not fired
 * synchronously — so flaps crossed within a single tick() call (a slow
 * frame, a backgrounded tab catching up) still land spaced out correctly
 * instead of firing as one simultaneous burst.
 *
 * There's no click sample on disk yet, so the buffer is synthesized once:
 * a short burst of decaying noise stands in for a real recorded click.
 * Swap `synthesizeClick` for a loaded sample later without touching the
 * scheduling below.
 */
export class BoardAudio {
  private readonly ctx: AudioContext;
  private readonly master: GainNode;
  private readonly clickBuffer: AudioBuffer;
  private readonly maxVoices: number;
  private activeVoices = 0;

  private originAudioTime = 0;
  private originSet = false;

  constructor(maxVoices = 24) {
    this.ctx = new AudioContext();
    this.master = this.ctx.createGain();
    this.master.gain.value = 1;
    this.master.connect(this.ctx.destination);
    this.maxVoices = maxVoices;
    this.clickBuffer = this.synthesizeClick();
  }

  private synthesizeClick(): AudioBuffer {
    const durationMs = 14;
    const sampleRate = this.ctx.sampleRate;
    const length = Math.floor((sampleRate * durationMs) / 1000);
    const buffer = this.ctx.createBuffer(1, length, sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i++) {
      const t = i / length;
      const envelope = Math.pow(1 - t, 4);
      data[i] = (Math.random() * 2 - 1) * envelope;
    }
    return buffer;
  }

  /** Schedules a click for a flap that happened at `engineTimestamp` ms on the board's clock. */
  scheduleFlap(engineTimestamp: number): void {
    if (!this.originSet) {
      this.originAudioTime = this.ctx.currentTime;
      this.originSet = true;
    }
    const when = this.originAudioTime + engineTimestamp / 1000;
    this.playClickAt(Math.max(when, this.ctx.currentTime));
  }

  private playClickAt(when: number): void {
    // Voice cap: a full-board transition fires 132 near-simultaneous flaps.
    // Uncapped, that clips into white noise — drop rather than mix past the cap.
    if (this.activeVoices >= this.maxVoices) return;

    const src = this.ctx.createBufferSource();
    src.buffer = this.clickBuffer;
    src.playbackRate.value = 1 + (Math.random() * 2 - 1) * 0.05;

    const gain = this.ctx.createGain();
    gain.gain.value = 0.85 + Math.random() * 0.3;

    src.connect(gain).connect(this.master);

    this.activeVoices++;
    src.onended = () => {
      this.activeVoices--;
    };
    src.start(when);
  }

  /** Master volume 0..1. Drive this to 0 for quiet hours — not a "dim," a hard off-switch. */
  setGain(value: number): void {
    this.master.gain.value = Math.max(0, Math.min(1, value));
  }

  /** Browsers block audio until a user gesture resumes the context. */
  async resume(): Promise<void> {
    if (this.ctx.state === "suspended") await this.ctx.resume();
  }
}
