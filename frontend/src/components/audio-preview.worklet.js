class AudioPreview extends AudioWorkletProcessor {
  buffer = new Int16Array(sampleRate * 5);
  offset = 0;

  process(inputs) {
    for (const float of inputs[0]?.[0] ?? []) {
      const sample = Math.max(-1, Math.min(1, float));
      this.buffer[this.offset++] = sample < 0 ? sample * 32768 : sample * 32767;
      if (this.offset === this.buffer.length) {
        this.port.postMessage(this.buffer.buffer, [this.buffer.buffer]);
        this.buffer = new Int16Array(sampleRate * 5);
        this.offset = 0;
      }
    }
    return true;
  }
}

registerProcessor("audio-preview", AudioPreview);
