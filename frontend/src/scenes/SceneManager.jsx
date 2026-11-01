import React, { useEffect, useState } from "react";
import IdleScene from "./IdleScene.jsx";
import BriefingScene from "./BriefingScene.jsx";
import AdminScene from "./AdminScene.jsx";

// Cenas em sobreposição. A cena ACTIVE é o próprio HUD (children), sempre montado por baixo.
// Para criar uma cena nova: registre o componente aqui e chame goTo("NOME").
// As props de cada cena vêm de overlayProps[NOME].
const OVERLAYS = {
  IDLE: IdleScene,
  BRIEFING: BriefingScene,
  ADMIN: AdminScene,
};

const FADE_MS = 600;

export default function SceneManager({ scene, overlayProps = {}, children }) {
  const [mounted, setMounted] = useState(null);
  const [visible, setVisible] = useState(false);
  const [hudGone, setHudGone] = useState(false); // HUD totalmente invisível: sai da composição

  useEffect(() => {
    if (OVERLAYS[scene]) {
      setMounted(scene);
      const id = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(id);
    }
    setVisible(false);
    const id = setTimeout(() => setMounted(null), FADE_MS);
    return () => clearTimeout(id);
  }, [scene]);

  const Overlay = mounted ? OVERLAYS[mounted] : null;
  const hudHidden = Boolean(OVERLAYS[scene]);

  // Depois do fade, o HUD sai de vez (visibility:hidden) para não ficar por baixo da cena.
  useEffect(() => {
    if (!hudHidden) {
      setHudGone(false);
      return;
    }
    const id = setTimeout(() => setHudGone(true), FADE_MS + 50);
    return () => clearTimeout(id);
  }, [hudHidden]);

  return (
    <div className="relative h-full w-full overflow-hidden">
      <div
        className="h-full w-full"
        style={{
          // Ao voltar, o HUD espera o painel quase terminar de sumir: nada de duas telas misturadas.
          transition: `opacity ${FADE_MS}ms ease ${hudHidden ? 0 : Math.round(FADE_MS * 0.55)}ms, transform ${FADE_MS}ms ease, filter ${FADE_MS}ms ease`,
          visibility: hudGone ? "hidden" : "visible",
          opacity: hudHidden ? 0 : 1,
          transform: hudHidden ? "scale(0.97)" : "scale(1)",
          filter: hudHidden ? "blur(6px)" : "none",
          pointerEvents: hudHidden ? "none" : "auto",
        }}
      >
        {children}
      </div>

      {Overlay && (
        <div
          className="absolute inset-0"
          style={{
            transition: `opacity ${FADE_MS}ms ease`,
            opacity: visible ? 1 : 0,
            pointerEvents: visible ? "auto" : "none",
          }}
        >
          <Overlay {...(overlayProps[mounted] || {})} />
        </div>
      )}
    </div>
  );
}
