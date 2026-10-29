import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Gerenciador de cena do HUD.
 *
 * Cenas: ACTIVE (HUD completo), IDLE (holograma), BRIEFING (resultado de rotina) e ADMIN (painel de rotinas).
 * - ACTIVE -> IDLE após `idleSeconds` sem interação (só se `canIdle`: assistente em STANDBY).
 * - BRIEFING -> IDLE após `briefingSeconds` sem interação.
 * - ADMIN nunca expira.
 * - Qualquer atividade acorda o IDLE (volta para ACTIVE). `wake()` pode ser chamado de fora (wake word).
 * Atalhos: Alt+I alterna IDLE/ACTIVE; Alt+R abre/fecha o painel de rotinas.
 */
export function useSceneManager({ canIdle, idleSeconds = 45, briefingSeconds = 180, onChange }) {
  const [scene, setScene] = useState("ACTIVE");
  const sceneRef = useRef("ACTIVE");
  const timer = useRef(null);
  const lastPos = useRef(null);
  const canIdleRef = useRef(canIdle);
  const onChangeRef = useRef(onChange);
  canIdleRef.current = canIdle;
  onChangeRef.current = onChange;

  const go = useCallback((next) => {
    if (sceneRef.current === next) return;
    sceneRef.current = next;
    setScene(next);
    onChangeRef.current?.(next);
  }, []);

  const arm = useCallback(() => {
    clearTimeout(timer.current);
    const current = sceneRef.current;
    if (!canIdleRef.current || current === "ADMIN" || current === "IDLE") return;
    const secs = current === "BRIEFING" ? briefingSeconds : idleSeconds;
    timer.current = setTimeout(() => {
      if (canIdleRef.current && sceneRef.current !== "ADMIN") go("IDLE");
    }, secs * 1000);
  }, [go, idleSeconds, briefingSeconds]);

  const wake = useCallback(() => {
    go("ACTIVE");
    arm();
  }, [go, arm]);

  const goTo = useCallback(
    (next) => {
      go(next);
      arm();
    },
    [go, arm]
  );

  // Status ocupado => acorda e para o timer; livre => rearma.
  useEffect(() => {
    if (canIdle) {
      arm();
    } else {
      clearTimeout(timer.current);
      if (sceneRef.current === "IDLE") go("ACTIVE");
    }
    return () => clearTimeout(timer.current);
  }, [canIdle, arm, go]);

  // Rearma ao trocar de cena.
  useEffect(() => {
    arm();
  }, [scene, arm]);

  useEffect(() => {
    let lastArm = 0;

    const onActivity = () => {
      if (sceneRef.current === "IDLE") return wake();
      const t = Date.now();
      if (t - lastArm > 500) {
        lastArm = t;
        arm();
      }
    };

    const onMove = (e) => {
      if (sceneRef.current === "IDLE") {
        const p = lastPos.current;
        lastPos.current = { x: e.clientX, y: e.clientY };
        if (!p || Math.hypot(e.clientX - p.x, e.clientY - p.y) > 40) wake();
        return;
      }
      lastPos.current = { x: e.clientX, y: e.clientY };
      onActivity();
    };

    const onKey = (e) => {
      if (e.altKey && e.key.toLowerCase() === "i") {
        e.preventDefault();
        if (sceneRef.current === "IDLE") wake();
        else go("IDLE");
        return;
      }
      if (e.altKey && e.key.toLowerCase() === "r") {
        e.preventDefault();
        go(sceneRef.current === "ADMIN" ? "ACTIVE" : "ADMIN");
        return;
      }
      onActivity();
    };

    window.addEventListener("pointerdown", onActivity);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("keydown", onKey);
    window.addEventListener("touchstart", onActivity, { passive: true });
    return () => {
      window.removeEventListener("pointerdown", onActivity);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("touchstart", onActivity);
    };
  }, [arm, wake, go]);

  return { scene, wake, goTo };
}
