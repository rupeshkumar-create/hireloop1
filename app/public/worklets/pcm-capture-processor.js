/* global registerProcessor, AudioWorkletProcessor */
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0]?.[0];
    if (input && input.length) {
      const copy = new Float32Array(input.length);
      copy.set(input);
      this.port.postMessage({ type: "audio", samples: copy }, [copy.buffer]);
    }
    return true;
  }
}
registerProcessor("pcm-capture-processor", PcmCaptureProcessor);
