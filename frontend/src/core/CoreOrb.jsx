import React, { Suspense, lazy } from "react";
import CoreRings from "../components/CoreRings.jsx";

// O núcleo 3D carrega sob demanda: se o Three.js ainda não estiver instalado, ou o WebGL
// falhar, o painel antigo (CoreRings) assume em vez de derrubar a tela.
const HoloCore = lazy(() => import("./HoloCore.jsx"));

// VITE_CORE_MODE: "classic" = só os anéis antigos | "light" = 3D mais leve | (vazio) = completo
const MODE = String(import.meta.env.VITE_CORE_MODE || "").toLowerCase();

let webglOk = null;
function hasWebGL() {
  if (webglOk !== null) return webglOk;
  try {
    const c = document.createElement("canvas");
    webglOk = Boolean(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    webglOk = false;
  }
  return webglOk;
}

class Boundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(err) {
    console.warn("[JARVIS] Núcleo 3D indisponível, usando o painel clássico:", err?.message || err);
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export default function CoreOrb({ status, onClick, levelRef, compact = false }) {
  const classic = <CoreRings status={status} onClick={onClick} compact={compact} />;
  if (compact || MODE === "classic" || !hasWebGL()) return classic;
  return (
    <Boundary fallback={classic}>
      <Suspense fallback={classic}>
        <HoloCore status={status} onClick={onClick} levelRef={levelRef} low={MODE === "light"} />
      </Suspense>
    </Boundary>
  );
}
