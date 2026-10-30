import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL } from "../lib/api.js";

// Captura o microfone, converte para PCM16 16 kHz e manda ao backend, que detecta "Jarvis"
// e transcreve com Whisper. O código roda num AudioWorklet (fora da thread da interface).
const WORKLET = `
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.inBuf = new Float32Array(0);
    this.pos = 0;
    this.out = [];
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    const merged = new Float32Array(this.inBuf.length + ch.length);
    merged.set(this.inBuf);
    merged.set(ch, this.inBuf.length);
    this.inBuf = merged;
    while (this.pos + 1 < this.inBuf.length) {
      const i = Math.floor(this.pos), f = this.pos - i;
      const v = this.inBuf[i] * (1 - f) + this.inBuf[i + 1] * f;
      this.out.push(Math.max(-1, Math.min(1, v)) * 32767);
      this.pos += this.ratio;
    }
    const drop = Math.floor(this.pos);
    if (drop > 0) { this.inBuf = this.inBuf.slice(drop); this.pos -= drop; }
    if (this.out.length >= 1600) {
      const pcm = new Int16Array(this.out.length);
      for (let k = 0; k < pcm.length; k++) pcm[k] = this.out[k];
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
      this.out = [];
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
`;

const UNMUTE_DELAY_MS = 450; // espera o eco da própria voz do Jarvis acabar antes de voltar a ouvir

export const handsFreeSupported =
  typeof navigator !== "undefined" &&
  Boolean(navigator.mediaDevices?.getUserMedia) &&
  typeof window !== "undefined" &&
  "AudioWorklet" in window;

/**
 * state: off | connecting | loading | listening (esperando "Jarvis") | awake (esperando o comando)
 *        | unavailable | error
 */
export function useHandsFree({ enabled, muted, onWake, onSleep, onTranscript, onError }) {
  const [state, setState] = useState("off");
  const cbs = useRef({});
  cbs.current = { onWake, onSleep, onTranscript, onError };
  const mutedRef = useRef(muted);
  const wsRef = useRef(null);
  const timerRef = useRef(null);

  const send = useCallback((obj) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
  }, []);

  // Mudo enquanto o Jarvis processa/fala (e um instante depois), para ele não ouvir a si mesmo.
  useEffect(() => {
    clearTimeout(timerRef.current);
    if (muted) {
      mutedRef.current = true;
      send({ type: "mute", value: true });
    } else {
      timerRef.current = setTimeout(() => {
        mutedRef.current = false;
        send({ type: "mute", value: false });
      }, UNMUTE_DELAY_MS);
    }
    return () => clearTimeout(timerRef.current);
  }, [muted, send]);

  useEffect(() => {
    if (!enabled || !handsFreeSupported) {
      setState("off");
      return undefined;
    }
    let stopped = false, fatal = false, ws = null, ctx = null, stream = null, node = null, retryTimer = null;
    let retry = 1000;
    const wsUrl = `${API_URL.replace(/^http/, "ws")}/v1/voice/ws`;

    const resume = () => ctx && ctx.state === "suspended" && ctx.resume().catch(() => {});
    window.addEventListener("pointerdown", resume);
    window.addEventListener("keydown", resume);

    const startAudio = async () => {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      try { ctx = new AudioContext({ sampleRate: 16000 }); } catch { ctx = new AudioContext(); }
      const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
      await ctx.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      const src = ctx.createMediaStreamSource(stream);
      node = new AudioWorkletNode(ctx, "pcm-capture");
      node.port.onmessage = (e) => {
        if (!mutedRef.current && ws && ws.readyState === 1) ws.send(e.data);
      };
      // O grafo só processa se chegar a um destino; ganho 0 para não ecoar o microfone.
      const sink = ctx.createGain();
      sink.gain.value = 0;
      src.connect(node);
      node.connect(sink);
      sink.connect(ctx.destination);
      resume();
    };

    const connect = () => {
      if (stopped || fatal) return;
      setState("connecting");
      ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      ws.onopen = () => {
        retry = 1000;
        if (mutedRef.current) ws.send(JSON.stringify({ type: "mute", value: true }));
      };
      ws.onmessage = (ev) => {
        let m;
        try { m = JSON.parse(ev.data); } catch { return; }
        switch (m.type) {
          case "loading": setState("loading"); break;
          case "ready": setState("listening"); break;
          case "wake": setState("awake"); cbs.current.onWake?.(m); break;
          case "awake": setState("awake"); break;
          case "sleep": setState("listening"); cbs.current.onSleep?.(); break;
          case "transcript": setState("listening"); cbs.current.onTranscript?.(m.text); break;
          case "error":
            fatal = m.code === "unavailable";
            setState(fatal ? "unavailable" : "error");
            cbs.current.onError?.(m.message);
            break;
          default: break;
        }
      };
      ws.onclose = (ev) => {
        if (stopped || fatal) return;
        if (ev.code === 4403) {
          fatal = true;
          setState("error");
          cbs.current.onError?.("O backend recusou esta origem. Abra o Jarvis por localhost.");
          return;
        }
        setState("connecting");
        retryTimer = setTimeout(connect, retry);
        retry = Math.min(retry * 2, 10000);
      };
    };

    (async () => {
      try {
        await startAudio();
      } catch (err) {
        if (stopped) return;
        setState("error");
        cbs.current.onError?.(
          err?.name === "NotAllowedError"
            ? "Microfone bloqueado. Libere o microfone para o Jarvis nas permissões do navegador."
            : `Não consegui abrir o microfone: ${err?.message || err}`
        );
        return;
      }
      if (!stopped) connect();
    })();

    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      window.removeEventListener("pointerdown", resume);
      window.removeEventListener("keydown", resume);
      try { ws?.close(); } catch { /* já fechado */ }
      try { node?.disconnect(); } catch { /* já desconectado */ }
      stream?.getTracks().forEach((t) => t.stop());
      ctx?.close().catch(() => {});
      wsRef.current = null;
    };
  }, [enabled]);

  const followUp = useCallback((seconds = 8) => send({ type: "follow_up", seconds }), [send]);
  const sleep = useCallback(() => send({ type: "sleep" }), [send]);
  return { state, followUp, sleep };
}
