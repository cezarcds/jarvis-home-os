import React, { useEffect, useState } from "react";
import IdleScene from "./IdleScene.jsx";

// Registro de cenas em sobreposição. A cena ACTIVE é o próprio HUD (children).
// Para criar uma cena nova (ex.: ALERT, HOME), registre o componente aqui
// e chame goTo("ALERT") no useSceneManager.
const OVERLAYS = {
  IDLE: IdleScene,
};

const FADE_MS = 700;

export default function SceneManager({ scene, onWake, children }) {
  const [mounted, setMounted] = useState(null); // cena em sobreposição montada
  const [visible, setVisible] = useState(false); // controla o fade

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

  return (
    <div className="relative h-full w-full overflow-hidden">
      {/* HUD ativo fica sempre montado para preservar logs, histórico e clima */}
      <div
        className="h-full w-full"
        style={{
          transition: `opacity ${FADE_MS}ms ease, transform ${FADE_MS}ms ease, filter ${FADE_MS}ms ease`,
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
          <Overlay onWake={onWake} />
        </div>
      )}
    </div>
  );
}
