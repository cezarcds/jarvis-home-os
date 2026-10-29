import React, { useCallback, useRef, useState } from "react";
import CoreRings from "./components/CoreRings.jsx";
import { LeftPanels, RightConsole } from "./components/SidePanels.jsx";
import { useSpeech } from "./hooks/useSpeech.js";
import { askAssistant } from "./lib/api.js";
import SceneManager from "./scenes/SceneManager.jsx";
import { useSceneManager } from "./scenes/useSceneManager.js";

const IDLE_SECONDS = Number(import.meta.env.VITE_IDLE_SECONDS) || 45;
const BRIEFING_SECONDS = Number(import.meta.env.VITE_BRIEFING_SECONDS) || 180;

const now = () => new Date().toLocaleTimeString("pt-BR");
const normalize = (s) =>
  s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();

// Comandos tratados no navegador (não precisam do backend)
const CLOSE_RE = /^(jarvis )?(ok|fechar|pode fechar|voltar|obrigado|obrigada|valeu|tchau|dispensado)( jarvis)?$/;
const ADMIN_RE = /(painel de rotinas|\badmin\b|gerenciar rotinas|editar rotinas|abr\w* (as |a )?(minhas )?rotinas)/;

const newSessionId = () => (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2));

export default function App() {
  const [status, setStatus] = useState("STANDBY");
  const [userText, setUserText] = useState("");
  const [reply, setReply] = useState("Sistema em espera. Toque no núcleo para falar.");
  const [logs, setLogs] = useState([{ time: now(), msg: "Sistema inicializado.", level: "info" }]);
  const [briefing, setBriefing] = useState(null);
  const [typed, setTyped] = useState("");
  const history = useRef([]);
  const sessionId = useRef(newSessionId());
  const speechRef = useRef(null);
  const sceneRef = useRef("ACTIVE");

  const log = useCallback((msg, level = "info") => {
    setLogs((l) => [...l.slice(-100), { time: now(), msg, level }]);
  }, []);

  const { scene, wake, goTo } = useSceneManager({
    canIdle: status === "STANDBY",
    idleSeconds: IDLE_SECONDS,
    briefingSeconds: BRIEFING_SECONDS,
    onChange: (s) => {
      const names = { IDLE: "Modo IDLE ativado.", ACTIVE: "HUD ativo.", BRIEFING: "Painel de rotina aberto.", ADMIN: "Painel de rotinas aberto." };
      log(names[s] || s);
    },
  });
  sceneRef.current = scene;

  const handleError = useCallback(
    (msg) => {
      log(msg, "warn");
      setReply(msg);
      setStatus("STANDBY");
    },
    [log]
  );

  // Envia um comando (voz ou texto) ao assistente e aplica a resposta (fala + cena).
  const send = useCallback(
    async (text) => {
      setUserText(text);
      log(`Comando: "${text}"`);
      setStatus("PROCESSING");
      history.current.push({ role: "user", content: text });
      try {
        const r = await askAssistant(history.current.slice(-12), sessionId.current);
        history.current.push({ role: "assistant", content: r.text || "(rotina exibida na tela)" });
        if (r.text) setReply(r.text);
        if (r.scene) {
          setBriefing(r.scene);
          goTo("BRIEFING");
          if (r.scene.rotina) log(`Rotina executada: ${r.scene.rotina.nome}`);
        }
        if (r.text) speechRef.current.speak(r.text);
        else setStatus("STANDBY");
      } catch (err) {
        history.current.pop();
        handleError(err.message);
      }
    },
    [log, handleError, goTo]
  );

  const handleTranscript = useCallback(
    (text) => {
      const n = normalize(text);
      if (sceneRef.current === "BRIEFING" && CLOSE_RE.test(n)) {
        log("Painel fechado por voz.");
        goTo("ACTIVE");
        setStatus("STANDBY");
        return;
      }
      if (ADMIN_RE.test(n)) {
        setUserText(text);
        goTo("ADMIN");
        setStatus("STANDBY");
        return;
      }
      send(text);
    },
    [send, goTo, log]
  );

  const speech = useSpeech({
    onFinalTranscript: handleTranscript,
    onSpeakStart: () => setStatus("SPEAKING"),
    onSpeakEnd: () => setStatus("STANDBY"),
    onError: handleError,
  });
  speechRef.current = speech;

  const onCoreClick = () => {
    if (status === "LISTENING") {
      speech.stopListening();
      setStatus("STANDBY");
      return;
    }
    if (status === "PROCESSING") return;
    setUserText("");
    setStatus("LISTENING");
    log("Microfone ativo.");
    speech.startListening();
  };

  const submitTyped = (e) => {
    e.preventDefault();
    if (!typed.trim() || status === "PROCESSING") return;
    handleTranscript(typed.trim());
    setTyped("");
  };

  const closeScene = () => {
    speech.stopSpeaking?.();
    goTo("ACTIVE");
    setStatus((s) => (s === "SPEAKING" ? "STANDBY" : s));
  };

  const overlayProps = {
    IDLE: { onWake: wake },
    BRIEFING: { data: briefing, status, userText, reply, onMic: onCoreClick, onClose: closeScene, onSend: send },
    ADMIN: {
      onClose: () => goTo("ACTIVE"),
      onRun: (res) => {
        setBriefing(res.scene);
        goTo("BRIEFING");
        if (res.text) {
          setReply(res.text);
          speechRef.current.speak(res.text);
        }
      },
      onToast: (m) => log(m),
    },
  };

  return (
    <SceneManager scene={scene} overlayProps={overlayProps}>
      <div className="blueprint h-full w-full flex flex-col text-hud-cyan">
        <header className="px-6 py-3 flex justify-between items-center text-xs tracking-[0.4em] border-b border-hud-cyan/20">
          <span>JARVIS // HOME OS</span>
          <div className="flex items-center gap-6">
            <button onClick={() => goTo("ADMIN")} className="tracking-[0.3em] opacity-70 hover:opacity-100" title="Alt+R">
              ROTINAS
            </button>
            <span className={status === "LISTENING" ? "text-hud-amber" : ""}>● {status}</span>
          </div>
        </header>

        <main className="flex-1 flex items-center justify-between px-8 gap-6 min-h-0">
          <LeftPanels />

          <div className="flex flex-col items-center gap-6 flex-1 min-w-0">
            <CoreRings status={status} onClick={onCoreClick} />
            <div className="panel p-4 w-full max-w-2xl text-sm space-y-2">
              {userText && <div className="text-hud-cyan/60">&gt; {userText}</div>}
              <div className="text-cyan-100 leading-relaxed">{reply}</div>
            </div>
            <form onSubmit={submitTyped} className="w-full max-w-2xl">
              <input
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder="ou digite um comando, ex.: bom dia"
                className="w-full bg-transparent border border-hud-cyan/25 px-3 py-2 text-xs outline-none focus:border-hud-cyan"
              />
            </form>
            {!speech.supported && (
              <div className="text-hud-amber text-xs">Web Speech API indisponível neste navegador (use Chrome/Edge).</div>
            )}
          </div>

          <RightConsole logs={logs} />
        </main>
      </div>
    </SceneManager>
  );
}
