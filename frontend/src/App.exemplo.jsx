// EXEMPLO baseado no App.jsx público do GitHub (109 linhas).
// Se o seu App.jsx local já é diferente, NÃO substitua: aplique só os trechos marcados com "// [NEWS]".
import React, { useCallback, useRef, useState } from "react";
import CoreRings from "./components/CoreRings.jsx";
import { LeftPanels, RightConsole } from "./components/SidePanels.jsx";
import { useSpeech } from "./hooks/useSpeech.js";
// [NEWS] 1/5: imports (o askJarvis antigo deixa de ser usado aqui)
import { askJarvisWithNews, looksLikeNews } from "./lib/newsApi.js";
import NewsMural from "./components/news/NewsMural.jsx";
import HeadlinesCard from "./components/news/HeadlinesCard.jsx";
import SceneManager from "./scenes/SceneManager.jsx";
import { useSceneManager } from "./scenes/useSceneManager.js";

const IDLE_SECONDS = Number(import.meta.env.VITE_IDLE_SECONDS) || 45;
const now = () => new Date().toLocaleTimeString("pt-BR");

export default function App() {
  const [status, setStatus] = useState("STANDBY");
  const [userText, setUserText] = useState("");
  const [reply, setReply] = useState("Sistema em espera. Toque no núcleo para falar.");
  const [logs, setLogs] = useState([{ time: now(), msg: "Sistema inicializado.", level: "info" }]);
  const [news, setNews] = useState(null); // [NEWS] 2/5: notícias da resposta atual
  const history = useRef([]);

  const log = useCallback((msg, level = "info") => {
    setLogs((l) => [...l.slice(-100), { time: now(), msg, level }]);
  }, []);

  const handleError = useCallback(
    (msg) => {
      log(msg, "warn");
      setReply(msg);
      setStatus("STANDBY");
    },
    [log]
  );

  const speechRef = useRef(null);

  const handleTranscript = useCallback(
    async (text) => {
      setUserText(text);
      log(`Comando: "${text}"`);
      setStatus("PROCESSING");
      setNews(null); // [NEWS] 3/5: os cartões anteriores saem
      if (looksLikeNews(text)) {
        setReply("Buscando notícias…");
        log("Buscando notícias.");
      }
      history.current.push({ role: "user", content: text });
      try {
        // [NEWS] 4/5: troca askJarvis(...) por askJarvisWithNews(...)
        const { answer, news: found } = await askJarvisWithNews(history.current.slice(-12));
        history.current.push({ role: "assistant", content: answer });
        setReply(answer);
        setNews(found);
        log(found?.items?.length ? `Resposta recebida com ${found.items.length} fontes.` : "Resposta recebida.");
        speechRef.current.speak(answer);
      } catch (err) {
        history.current.pop();
        handleError(err.message);
      }
    },
    [log, handleError]
  );

  const speech = useSpeech({
    onFinalTranscript: handleTranscript,
    onSpeakStart: () => setStatus("SPEAKING"),
    onSpeakEnd: () => setStatus("STANDBY"),
    onError: handleError,
  });
  speechRef.current = speech;

  const { scene, wake } = useSceneManager({
    canIdle: status === "STANDBY",
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
    setStatus("LISTENING");
    log("Microfone ativo.");
    speech.startListening();
  };

  return (
    <SceneManager scene={scene} onWake={wake}>
      <div className="blueprint h-full w-full flex flex-col text-hud-cyan">
        <header className="px-6 py-3 flex justify-between text-xs tracking-[0.4em] border-b border-hud-cyan/20">
          <span>JARVIS // HOME OS</span>
          <span className={status === "LISTENING" ? "text-hud-amber" : ""}>● {status}</span>
        </header>

        <main className="flex-1 flex items-center justify-between px-8 gap-6 min-h-0">
          {/* [NEWS] 5/5a: cartão de manchetes na tela principal (ou troque um painel existente por ele) */}
          <div className="flex flex-col gap-4 min-h-0 overflow-y-auto">
            <LeftPanels />
            <HeadlinesCard initialTopic="mercado" />
          </div>

          <div className="flex flex-col items-center gap-6 flex-1 min-w-0">
            <CoreRings status={status} onClick={onCoreClick} />
            <div className="panel p-4 w-full max-w-2xl text-sm space-y-2">
              {userText && <div className="text-hud-cyan/60">&gt; {userText}</div>}
              <div className="text-cyan-100 leading-relaxed">{reply}</div>
            </div>
            {!speech.supported && (
              <div className="text-hud-amber text-xs">Web Speech API indisponível neste navegador (use Chrome/Edge).</div>
            )}
          </div>
          <RightConsole logs={logs} />
        </main>

        {/* [NEWS] 5/5b: mural de notícias (cartões entrando e saindo) */}
        <NewsMural news={news} speaking={status === "SPEAKING"} onDismiss={() => setNews(null)} />
      </div>
    </SceneManager>
  );
}
