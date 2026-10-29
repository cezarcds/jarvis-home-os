import React, { useCallback, useRef, useState } from "react";
import CoreRings from "./components/CoreRings.jsx";
import { LeftPanels, RightConsole } from "./components/SidePanels.jsx";
import { useSpeech } from "./hooks/useSpeech.js";
import { askJarvis, askVisualExplain } from "./lib/api.js";
import VisualExplain from "./components/VisualExplain.jsx";
import SceneManager from "./scenes/SceneManager.jsx";
import { useSceneManager } from "./scenes/useSceneManager.js";

const IDLE_SECONDS = Number(import.meta.env.VITE_IDLE_SECONDS) || 45;
const now = () => new Date().toLocaleTimeString("pt-BR");

export default function App() {
  const [status, setStatus] = useState("STANDBY");
  const [userText, setUserText] = useState("");
  const [reply, setReply] = useState("Sistema em espera. Toque no núcleo para falar.");
  const [visualData, setVisualData] = useState(null);
  const [visualLoading, setVisualLoading] = useState(false);
  const [visualMode, setVisualMode] = useState(false);
  const [logs, setLogs] = useState([{ time: now(), msg: "Sistema inicializado.", level: "info" }]);
  const history = useRef([]);

  const log = useCallback((msg, level = "info") => {
    setLogs((l) => [...l.slice(-100), { time: now(), msg, level }]);
  }, []);

  const handleError = useCallback((msg) => {
    log(msg, "warn");
    setReply(msg);
    setVisualLoading(false);
    setStatus("STANDBY");
  }, [log]);

  const speechRef = useRef(null);

  const handleTranscript = useCallback(async (text) => {
    setUserText(text);
    log(`Comando: "${text}"`);
    setStatus("PROCESSING");
    setVisualMode(true);
    history.current.push({ role: "user", content: text });
    setVisualLoading(true);
    setVisualData(null);
    try {
      let answer;
      try {
        const explanation = await askVisualExplain(history.current.slice(-12));
        answer = explanation.answer;
        setVisualData(explanation);
        log("Palco visual preparado.");
      } catch (visualErr) {
        console.warn("[JARVIS] Visual Explain indisponível; usando resposta simples.", visualErr);
        answer = await askJarvis(history.current.slice(-12));
        setVisualData(null);
        log("Resposta recebida em modo simples.");
      }
      history.current.push({ role: "assistant", content: answer });
      setReply(answer);
      speechRef.current.speak(answer);
    } catch (err) {
      history.current.pop();
      handleError(err.message);
    } finally {
      setVisualLoading(false);
    }
  }, [log, handleError]);

  const speech = useSpeech({
    onFinalTranscript: handleTranscript,
    onSpeakStart: () => setStatus("SPEAKING"),
    onSpeakEnd: () => setStatus("STANDBY"),
    onError: handleError,
  });
  speechRef.current = speech;

  const { scene, wake } = useSceneManager({
    canIdle: status === "STANDBY" && !visualMode,
    idleSeconds: IDLE_SECONDS,
    onChange: (s) => log(s === "IDLE" ? "Modo IDLE ativado." : "Sistema reativado."),
  });

  const onCoreClick = () => {
    if (status === "LISTENING") {
      speech.stopListening();
      setStatus("STANDBY");
      return;
    }
    if (status === "PROCESSING") return;
    setUserText("");
    setVisualData(null);
    setVisualLoading(false);
    setVisualMode(false);
    setStatus("LISTENING");
    log("Microfone ativo.");
    speech.startListening();
  };

  const closeVisualMode = () => {
    window.speechSynthesis?.cancel();
    setVisualMode(false);
    setVisualLoading(false);
    setStatus("STANDBY");
  };

  return (
    <SceneManager scene={scene} onWake={wake}>
      <div className={`blueprint jarvis-app ${visualMode ? "visual-mode" : ""}`}>
        <header className="jarvis-header">
          <span>JARVIS <i>// HOME OS</i></span>
          <span className={`jarvis-status ${status === "LISTENING" ? "is-listening" : ""}`}><b />{status}</span>
          {visualMode && <button className="visual-close" onClick={closeVisualMode} title="Fechar modo visual">ESC ×</button>}
        </header>

        <main className="jarvis-main">
          {!visualMode && <LeftPanels />}
          <section className="jarvis-center">
            <div className="jarvis-core-wrap">
              <CoreRings status={status} onClick={onCoreClick} />
              {!visualMode && <span className="core-hint">{status === "LISTENING" ? "OUVINDO" : "TOQUE PARA FALAR"}</span>}
            </div>

            {visualMode ? (
              <VisualExplain
                data={visualData}
                loading={visualLoading}
                question={userText}
                answer={reply}
                status={status}
              />
            ) : (
              <div className="panel reply-panel">
                {userText && <div className="reply-question">&gt; {userText}</div>}
                <div className="reply-text">{reply}</div>
                {!speech.supported && <div className="speech-warning">Web Speech API indisponível neste navegador (use Chrome/Edge).</div>}
              </div>
            )}
          </section>
          {!visualMode && <RightConsole logs={logs} />}
        </main>
      </div>
    </SceneManager>
  );
}
