/**
 * AudioWorkletProcessor — downsample to 16 kHz and send int16 PCM chunks.
 * Lives in /public so Vite serves it as a static asset.
 */
class AudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // sampleRate is a global in AudioWorklet scope (native context rate)
    this._ratio = sampleRate / 16000;
    this._inBuf = [];
    this._outBuf = [];
    this._CHUNK = 4096; // output samples per message (~256 ms at 16 kHz)
  }

  process(inputs) {
    const ch = inputs[0]?.[0];
    if (!ch) return true;

    // Simple nearest-neighbour downsampling
    for (let i = 0; i < ch.length; i += this._ratio) {
      this._outBuf.push(ch[Math.floor(i)]);
    }

    while (this._outBuf.length >= this._CHUNK) {
      const slice = this._outBuf.splice(0, this._CHUNK);
      const int16 = new Int16Array(this._CHUNK);
      for (let i = 0; i < this._CHUNK; i++) {
        int16[i] = Math.max(-32768, Math.min(32767, Math.round(slice[i] * 32768)));
      }
      this.port.postMessage({ type: "audio", data: int16.buffer }, [int16.buffer]);
    }

    return true;
  }
}

registerProcessor("audio-processor", AudioProcessor);
