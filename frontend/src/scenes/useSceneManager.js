import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Gerenciador de cena do HUD.
 *
 * Cenas: "ACTIVE" (HUD completo) e "IDLE" (holograma em espera).
 * - Entra em IDLE depois de `idleSeconds` sem interação, mas só se `canIdle` for true
 *   (ou seja, o assistente está em STANDBY e não ouvindo/processando/falando).
 * - Volta para ACTIVE com clique, toque, tecla, movimento relevante do mouse
 *   ou chamando `wake()` (ex.: futura wake word "Jarvis").
 * - Atalho de teste: Alt+I alterna IDLE/ACTIVE sem esperar o timer.
 */
export function useSceneManager({ canIdle, idleSeconds = 45, onChange }) {
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
    if (!canIdleRef.current) return;
    timer.current = setTimeout(() => {
      if (canIdleRef.current) go("IDLE");
    }, idleSeconds * 1000);
  }, [go, idleSeconds]);

  const wake = useCallback(() => {
    go("ACTIVE");
    arm();
  }, [go, arm]);

  // Reage a mudanças de status: ocupado => acorda e para o timer; livre => rearma.
  useEffect(() => {
    if (canIdle) {
      arm();
    } else {
      clearTimeout(timer.current);
      if (sceneRef.current === "IDLE") go("ACTIVE");
    }
    return () => clearTimeout(timer.current);
  }, [canIdle, arm, go]);

  // Detecta atividade do usuário.
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
        // Ignora tremidas pequenas: só acorda se o mouse andou de verdade.
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

  return { scene, wake, goTo: go };
}
