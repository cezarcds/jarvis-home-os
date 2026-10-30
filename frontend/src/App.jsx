import React, { useCallback, useEffect, useRef, useState } from "react";
import CoreRings from "./components/CoreRings.jsx";
import CoreOrb from "./core/CoreOrb.jsx";
import { useVoiceLevel } from "./core/useVoiceLevel.js";
import { LeftPanels, RightConsole } from "./components/SidePanels.jsx";
import { useSpeech } from "./hooks/useSpeech.js";
import { handsFreeSupported, useHandsFree } from "./hooks/useHandsFree.js";
import { isLocalCommand } from "./lib/localIntents.js";
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

// Dentro de uma cena, só estes comandos a fecham ("ok" e "obrigado" NÃO, para um ruído não derrubar a cena).
const VISUAL_CLOSE_RE =
  /^(jarvis )?(fechar|fecha|pode fechar|voltar|sair|encerrar|tchau|dispensado)( jarvis)?$/;
// Interjeições soltas dentro de uma cena: não fecham nem remontam nada.
const FILLER_RE =
  /^(jarvis )?(ok|okay|certo|entendi|beleza|legal|uhum|aham|sim|nao|obrigado|obrigada|valeu|hum|hmm)( jarvis)?$/;

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
  // Intensidade da sua voz (ref, sem re-render): o núcleo 3D pulsa e se expande com ela.
  const voiceLevel = useVoiceLevel(status === "LISTENING");
  const [userText, setUserText] = useState("");
  const [reply, setReply] = useState(
    "Sistema em espera. Toque no núcleo para falar."
  );
  const [logs, setLogs] = useState([
    { time: now(), msg: "Sistema inicializado.", level: "info" },
  ]);
  const [briefing, setBriefing] = useState(null);
  const [typed, setTyped] = useState("");

  // Voz sem clique ("Jarvis, ...") e visão de tela
  const [handsFreeOn, setHandsFreeOn] = useState(
    () => handsFreeSupported && localStorage.getItem("jarvis.handsfree") !== "0"
  );
  const [ptt, setPtt] = useState(false); // microfone do clique ativo: o canal livre fica mudo para não duplicar
  const [vision, setVision] = useState({ mode: "off", active: false, label: "" });
  const visionRef = useRef({ mode: "off", until: 0 });

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
  // Refs lidas dentro de handleTranscript, que não deve ficar presa a valores antigos.
  const visualActiveRef = useRef(false);
  const closeVisualRef = useRef(null);
  visualActiveRef.current = visualMode && Boolean(visualScene);

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
      setPtt(false);
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
        if (r.acao) log(`Ação: ${r.acao.tipo}${r.acao.app ? ` (${r.acao.app})` : ""}`);
        if (r.vision) {
          setVision(r.vision);
          visionRef.current = {
            mode: r.vision.mode,
            until: r.vision.active ? Date.now() + r.vision.follow_up_seconds * 1000 : 0,
          };
          if (r.kind === "visao" && r.vision.label) log(`Tela analisada: ${r.vision.label}`);
        }
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
      // Ações no computador e visão de tela vão direto ao assistente (backend)
      const v = visionRef.current;
      if (isLocalCommand(n, v.mode === "on" || Date.now() < v.until)) {
        send(text);
        return;
      }
      // Já estamos numa cena: qualquer fala nova é continuação ("e a segunda?", "fale mais"),
      // então remonta a cena em vez de só responder por voz. Para rodar uma rotina, feche a cena
      // antes (Esc ou "fechar"). Ações e visão de tela (acima) têm prioridade sobre isto.
      if (visualActiveRef.current) {
        if (VISUAL_CLOSE_RE.test(n)) {
          closeVisualRef.current?.();
          return;
        }
        if (FILLER_RE.test(n)) {
          setStatus("STANDBY");
          return;
        }
        sendVisual(text);
        return;
      }
      // Perguntas que pedem explicação visual → motor de cenas
      // Rotinas / comandos de casa → assistente atual
      // Heurística simples: se parece pergunta de conhecimento, usa cena
      // "Jarvis, como funciona..." -> tira o chamado do começo antes de testar os gatilhos.
      const q = n.replace(/^((ei|oi|ola|ok|e ai) )?jarvis /, "");
      const looksLikeExplain =
        /^(o que|oque|como|por que|porque|explique|explica|me explica|me explique|me fale|fale sobre|quem|quando|onde|qual|quais|quanto|quantos|mostra|mostre|me mostra|me mostre|desenhe|desenha|ilustre|compare|liste|conte|me conte|pesquise|busque|visualize)/.test(
          q
        ) ||
        // pedidos explicitamente visuais, em qualquer posição da frase
        /\b(mapa|imagem|imagens|foto|fotos|video|videos|diagrama|grafico|desenho)\b/.test(q) ||
        // normalize() apaga o "?", então a checagem é no texto original
        text.includes("?");
      if (looksLikeExplain) sendVisual(text);
      else send(text);
    },
    [send, sendVisual, goTo, log]
  );

  const speech = useSpeech({
    onFinalTranscript: handleTranscript,
    onInterim: setUserText,
    onListenEnd: (hadText) => {
      setPtt(false);
      if (hadText) return; // a transcrição segue o fluxo normal (PROCESSING)
      setDim(false);
      setStatus((s) => (s === "LISTENING" ? "STANDBY" : s));
    },
    onSpeakStart: () => setStatus("SPEAKING"),
    onSpeakEnd: () => setStatus("STANDBY"),
    onError: handleError,
  });
  speechRef.current = speech;

  const hf = useHandsFree({
    enabled: handsFreeOn,
    muted: status === "PROCESSING" || status === "SPEAKING" || ptt,
    onWake: () => {
      wake();
      setUserText("");
      setStatus("LISTENING");
      log("Palavra de ativação detectada.");
    },
    onSleep: () => setStatus((s) => (s === "LISTENING" ? "STANDBY" : s)),
    onTranscript: (text) => {
      wake();
      handleTranscript(text);
    },
    onError: (m) => log(m, "warn"),
  });

  // Depois que o Jarvis termina de falar, abre uma janela curta para a resposta sem precisar chamar "Jarvis" de novo.
  const prevStatus = useRef(status);
  useEffect(() => {
    if (prevStatus.current === "SPEAKING" && status === "STANDBY" && handsFreeOn) hf.followUp(8);
    prevStatus.current = status;
  }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (hf.state === "listening") setReply((r) => (r.startsWith("Sistema em espera") ? 'Diga "Jarvis" e o comando, ou toque no núcleo.' : r));
    if (hf.state === "loading") log("Carregando o reconhecimento de voz (a primeira vez baixa o modelo)...");
    if (hf.state === "unavailable") log("Voz livre indisponível: instale o faster-whisper (veja o README).", "warn");
  }, [hf.state]); // eslint-disable-line react-hooks/exhaustive-deps

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
  closeVisualRef.current = closeVisualMode;

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && visualMode && closeVisualMode();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visualMode, closeVisualMode]);

  const onCoreClick = () => {
    if (status === "LISTENING") {
      if (!ptt) {
        // Estava esperando o comando por voz livre: clicar cancela.
        hf.sleep();
        setStatus("STANDBY");
        return;
      }
      // Clicar de novo = "terminei": envia o que já foi dito (ou volta ao repouso se nada foi captado).
      speech.stopListening();
      return;
    }
    if (status === "PROCESSING") return;
    player.pause?.();
    hf.sleep();
    setPtt(true);
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
            {vision.active && (
              <span className="text-hud-amber tracking-[0.25em]" title="O Jarvis está analisando a sua tela. Diga: para de olhar a tela.">
                ◉ TELA
              </span>
            )}
            {handsFreeSupported && (
              <button
                onClick={() =>
                  setHandsFreeOn((v) => {
                    localStorage.setItem("jarvis.handsfree", v ? "0" : "1");
                    return !v;
                  })
                }
                className="tracking-[0.2em] opacity-70 hover:opacity-100"
                title='Voz livre: diga "Jarvis" seguido do comando'
              >
                MIC LIVRE {handsFreeOn ? (hf.state === "awake" ? "· OUVINDO" : hf.state === "listening" ? "· ON" : "· …") : "· OFF"}
              </button>
            )}
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
            {!visualMode && <CoreOrb status={status} onClick={onCoreClick} levelRef={voiceLevel} />}

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
