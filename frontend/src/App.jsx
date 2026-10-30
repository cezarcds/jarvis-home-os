import React, { useCallback, useEffect, useRef, useState } from "react";
import CoreRings from "./components/CoreRings.jsx";
import { LeftPanels, RightConsole } from "./components/SidePanels.jsx";
import { useSpeech } from "./hooks/useSpeech.js";
import { askAssistant, askScene } from "./lib/api.js";
import SceneStage from "./stage/SceneStage.jsx";
import { useScenePlayer } from "./stage/useScenePlayer.js";
import { useMediaResolver } from "./stage/useMediaResolver.js";
import { simpleScene } from "./stage/simpleScene.js";
import SceneManager from "./scenes/SceneManager.jsx";
import { useSceneManager } from "./scenes/useSceneManager.js";

const IDLE_SECONDS = Number(import.meta.env.VITE_IDLE_SECONDS) || 45;
const BRIEFING_SECONDS = Number(import.meta.env.VITE_BRIEFING_SECONDS) || 180;

const now = () => new Date().toLocaleTimeString("pt-BR");
const normalize = (s) =>
  s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

// Comandos tratados no navegador (não precisam do backend)
const CLOSE_RE =
  /^(jarvis )?(ok|fechar|pode fechar|voltar|obrigado|obrigada|valeu|tchau|dispensado)( jarvis)?$/;
const ADMIN_RE =
  /(painel de rotinas|\badmin\b|gerenciar rotinas|editar rotinas|abr\w* (as |a )?(minhas )?rotinas)/;

const newSessionId = () =>
  crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2);

/** Resumo da cena visual para o diretor entender aprofundamentos. */
function summarize(scene) {
  const labels = [
    ...(scene.diagram?.nodes || []).map((n) => n.label),
    ...(scene.geo?.points || []).map((p) => p.label),
  ];
  return { title: scene.title, labels };
}

export default function App() {
  const [status, setStatus] = useState("STANDBY");
  const [userText, setUserText] = useState("");
  const [reply, setReply] = useState(
    "Sistema em espera. Toque no núcleo para falar."
  );
  const [logs, setLogs] = useState([
    { time: now(), msg: "Sistema inicializado.", level: "info" },
  ]);
  const [briefing, setBriefing] = useState(null);
  const [typed, setTyped] = useState("");

  // Motor de cenas (palco visual)
  const [visualScene, setVisualScene] = useState(null);
  const [sceneLoading, setSceneLoading] = useState(false);
  const [visualMode, setVisualMode] = useState(false);
  const [dim, setDim] = useState(false);

  const history = useRef([]);
  const sessionId = useRef(newSessionId());
  const speechRef = useRef(null);
  const sceneRef = useRef("ACTIVE");
  const previousScene = useRef(null);

  const log = useCallback((msg, level = "info") => {
    setLogs((l) => [...l.slice(-100), { time: now(), msg, level }]);
  }, []);

  const { scene, wake, goTo } = useSceneManager({
    canIdle: status === "STANDBY" && !visualMode,
    idleSeconds: IDLE_SECONDS,
    briefingSeconds: BRIEFING_SECONDS,
    onChange: (s) => {
      const names = {
        IDLE: "Modo IDLE ativado.",
        ACTIVE: "HUD ativo.",
        BRIEFING: "Painel de rotina aberto.",
        ADMIN: "Painel de rotinas aberto.",
      };
      log(names[s] || s);
    },
  });
  sceneRef.current = scene;

  const handleError = useCallback(
    (msg) => {
      log(msg, "warn");
      setReply(msg);
      setSceneLoading(false);
      setDim(false);
      setStatus("STANDBY");
    },
    [log]
  );

  // ---------- Assistente com rotinas (comportamento atual) ----------
  const send = useCallback(
    async (text) => {
      setUserText(text);
      log(`Comando: "${text}"`);
      setStatus("PROCESSING");
      history.current.push({ role: "user", content: text });
      try {
        const r = await askAssistant(
          history.current.slice(-12),
          sessionId.current
        );
        history.current.push({
          role: "assistant",
          content: r.text || "(rotina exibida na tela)",
        });
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

  // ---------- Motor de cenas (explicações visuais) ----------
  const sendVisual = useCallback(
    async (text) => {
      setUserText(text);
      log(`Comando (cena): "${text}"`);
      setStatus("PROCESSING");
      setVisualMode(true);
      setDim(true);
      setSceneLoading(true);
      history.current.push({ role: "user", content: text });
      try {
        let next;
        try {
          next = await askScene(
            history.current.slice(-12),
            previousScene.current
          );
          log(`Cena montada: ${next.title} (${next.beats.length} trechos).`);
        } catch (sceneErr) {
          console.warn(
            "[JARVIS] Diretor de cenas indisponível; usando resposta simples.",
            sceneErr
          );
          // Fallback: tenta o assistente normal e monta uma cena mínima
          const r = await askAssistant(
            history.current.slice(-12),
            sessionId.current
          );
          next = simpleScene(r.text || "Não consegui montar a cena.");
          log("Resposta recebida em modo simples.");
        }
        history.current.push({ role: "assistant", content: next.answer });
        previousScene.current = summarize(next);
        setReply(next.answer);
        setVisualScene(next);
      } catch (err) {
        history.current.pop();
        handleError(err.message);
      } finally {
        setSceneLoading(false);
        setDim(false);
      }
    },
    [log, handleError]
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
      // Perguntas que pedem explicação visual → motor de cenas
      // Rotinas / comandos de casa → assistente atual
      // Heurística simples: se parece pergunta de conhecimento, usa cena
      const looksLikeExplain =
        /^(o que|oque|como|por que|porque|explique|me explica|me fale|fale sobre|quem|quando|onde|qual|quais|mostra|mostre)/.test(
          n
        ) || n.includes("?");
      if (looksLikeExplain) sendVisual(text);
      else send(text);
    },
    [send, sendVisual, goTo, log]
  );

  const speech = useSpeech({
    onFinalTranscript: handleTranscript,
    onInterim: setUserText,
    onListenEnd: (hadText) => {
      if (hadText) return; // a transcrição segue o fluxo normal (PROCESSING)
      setDim(false);
      setStatus((s) => (s === "LISTENING" ? "STANDBY" : s));
    },
    onSpeakStart: () => setStatus("SPEAKING"),
    onSpeakEnd: () => setStatus("STANDBY"),
    onError: handleError,
  });
  speechRef.current = speech;

  const media = useMediaResolver(visualScene);
  const player = useScenePlayer({
    scene: visualScene,
    ready: media.ready,
    speakBeat: speech.speakBeat || ((t) => speech.speak?.(t)),
    cancelSpeech: speech.cancelSpeech || (() => speech.stopSpeaking?.()),
  });

  useEffect(() => {
    if (player.playing) setStatus("SPEAKING");
    else setStatus((s) => (s === "SPEAKING" ? "STANDBY" : s));
  }, [player.playing]);

  const closeVisualMode = useCallback(() => {
    player.pause?.();
    speech.cancelSpeech?.() || speech.stopSpeaking?.();
    setVisualScene(null);
    setVisualMode(false);
    setSceneLoading(false);
    setDim(false);
    previousScene.current = null;
    setStatus("STANDBY");
  }, [player, speech]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && visualMode && closeVisualMode();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visualMode, closeVisualMode]);

  const onCoreClick = () => {
    if (status === "LISTENING") {
      // Clicar de novo = "terminei": envia o que já foi dito (ou volta ao repouso se nada foi captado).
      speech.stopListening();
      return;
    }
    if (status === "PROCESSING") return;
    player.pause?.();
    setUserText("");
    setStatus("LISTENING");
    log("Microfone ativo.");
    if (visualScene) setDim(true);
    else setVisualMode(false);
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
    BRIEFING: {
      data: briefing,
      status,
      userText,
      reply,
      onMic: onCoreClick,
      onClose: closeScene,
      onSend: send,
    },
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
      <div
        className={`blueprint h-full w-full flex flex-col text-hud-cyan ${
          visualMode ? "visual-mode" : ""
        }`}
      >
        <header className="px-6 py-3 flex justify-between items-center text-xs tracking-[0.4em] border-b border-hud-cyan/20">
          <span>JARVIS // HOME OS</span>
          <div className="flex items-center gap-6">
            <button
              onClick={() => goTo("ADMIN")}
              className="tracking-[0.3em] opacity-70 hover:opacity-100"
              title="Alt+R"
            >
              ROTINAS
            </button>
            {visualMode && (
              <button
                onClick={closeVisualMode}
                className="tracking-[0.2em] opacity-70 hover:opacity-100"
                title="Fechar modo visual (Esc)"
              >
                ESC ×
              </button>
            )}
            <span className={status === "LISTENING" ? "text-hud-amber" : ""}>
              ● {status}
            </span>
          </div>
        </header>

        <main className="flex-1 flex items-center justify-between px-8 gap-6 min-h-0">
          {!visualMode && <LeftPanels />}

          <div className="flex flex-col items-center gap-6 flex-1 min-w-0">
            {!visualMode && <CoreRings status={status} onClick={onCoreClick} />}

            {visualMode ? (
              <SceneStage
                scene={visualScene}
                media={media}
                player={player}
                loading={sceneLoading}
                dim={dim}
                question={userText}
                status={status}
                notice={reply}
              />
            ) : (
              <>
                <div className="panel p-4 w-full max-w-2xl text-sm space-y-2">
                  {userText && (
                    <div className="text-hud-cyan/60">&gt; {userText}</div>
                  )}
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
                  <div className="text-hud-amber text-xs">
                    Web Speech API indisponível neste navegador (use
                    Chrome/Edge).
                  </div>
                )}
              </>
            )}
          </div>

          {!visualMode && <RightConsole logs={logs} />}
        </main>

        {visualMode && (
          <div className="mic-dock flex items-center justify-center">
            <CoreRings compact status={status} onClick={onCoreClick} />
          </div>
        )}
      </div>
    </SceneManager>
  );
}
