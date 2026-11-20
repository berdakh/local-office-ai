import { useEffect, useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { api } from "../api/client";
import previewWorklet from "./audio-preview.worklet.js?url";

type Capture = {
  stream: MediaStream;
  recorder: MediaRecorder;
  context: AudioContext | null;
  preview: AbortController;
};

export default function Microphone({ disabled, onRecording, onActive }: {
  disabled: boolean;
  onRecording: (file: File) => void;
  onActive: (active: boolean) => void;
}) {
  const active = useRef<Capture | null>(null);
  const mounted = useRef(false);
  const [state, setState] = useState<"idle" | "starting" | "recording" | "stopping">("idle");
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [seconds, setSeconds] = useState(0);

  function release(capture: Capture) {
    capture.preview.abort();
    if (capture.context && capture.context.state !== "closed") void capture.context.close();
    capture.stream.getTracks().forEach((track) => track.stop());
  }

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (active.current) {
        active.current.recorder.onstop = null;
        if (active.current.recorder.state !== "inactive") active.current.recorder.stop();
        release(active.current);
        active.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (state !== "recording") return;
    const start = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 500);
    return () => window.clearInterval(timer);
  }, [state]);

  async function start() {
    setError("");
    setText("");
    setSeconds(0);
    setState("starting");
    onActive(true);
    let stream: MediaStream | undefined;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mounted.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const recorder = new MediaRecorder(stream);
      const capture: Capture = { stream, recorder, context: null, preview: new AbortController() };
      const chunks: Blob[] = [];
      active.current = capture;
      recorder.ondataavailable = ({ data }) => { if (data.size) chunks.push(data); };
      recorder.onstop = () => {
        release(capture);
        active.current = null;
        if (!mounted.current) return;
        setState("idle");
        onActive(false);
        if (!chunks.length) return;
        const mime = recorder.mimeType;
        const ext = mime.includes("mp4") ? "m4a" : mime.includes("ogg") ? "ogg" : "webm";
        const date = new Date().toISOString().slice(0, 19).replace(/:/g, "-");
        onRecording(new File(chunks, `Microphone-${date}.${ext}`, { type: mime }));
      };
      recorder.start(1000);
      setState("recording");

      try {
        const context = new AudioContext({ sampleRate: 16_000 });
        capture.context = context;
        if (context.sampleRate !== 16_000) throw new Error("Unsupported sample rate");
        await context.audioWorklet.addModule(previewWorklet);
        if (capture.preview.signal.aborted) return;
        const node = new AudioWorkletNode(context, "audio-preview");
        const input = context.createMediaStreamSource(stream);
        const silent = context.createGain();
        silent.gain.value = 0;
        let pending = false;
        node.port.onmessage = async ({ data }) => {
          if (pending || capture.preview.signal.aborted) return;
          pending = true;
          try {
            const result = await api.micPreview(data, capture.preview.signal);
            if (result.text && !capture.preview.signal.aborted) {
              setText((previous) => previous ? previous + "\n" + result.text : result.text);
            }
          } catch {
            if (!capture.preview.signal.aborted) setError("Live preview is unavailable. The recording is still being captured.");
          } finally {
            pending = false;
          }
        };
        input.connect(node);
        node.connect(silent).connect(context.destination);
        await context.resume();
      } catch {
        if (!capture.preview.signal.aborted) setError("Live preview is unavailable. The recording is still being captured.");
      }
    } catch (err) {
      stream?.getTracks().forEach((track) => track.stop());
      setError((err as Error).name === "NotAllowedError"
        ? "Microphone permission was denied. Allow access in your browser and try again."
        : "The browser could not start your microphone.");
      setState("idle");
      onActive(false);
    }
  }

  function stop() {
    const capture = active.current;
    if (capture?.recorder.state === "recording") {
      setState("stopping");
      capture.preview.abort();
      capture.recorder.stop();
    }
  }

  const timer = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return (
    <div className="mic-panel">
      <p className="small muted">See a live preview. Stop to save and transcribe the full recording.</p>
      <div className="row">
        {state === "recording" || state === "stopping"
          ? <button className="primary" onClick={stop} disabled={state === "stopping"}><Square size={16} /> Stop &amp; transcribe</button>
          : <button className="primary" onClick={() => void start()} disabled={disabled || state === "starting"}><Mic size={17} />{state === "starting" ? "Starting microphone…" : "Start microphone"}</button>}
        {state === "recording" && <span className="recording-indicator" aria-label="Recording active">{timer}</span>}
      </div>
      {state === "recording" && <div className="live-preview" aria-label="Live transcript preview"><strong>Live preview</strong><p>{text || "Listening… the first words appear after a short batch."}</p></div>}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
