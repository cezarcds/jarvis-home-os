import React, { useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import gsap from "gsap";
import { HALO_FRAG, HALO_VERT, ORB_FRAG, ORB_VERT, PARTICLE_FRAG, PARTICLE_VERT } from "./orbShaders.js";
import { hexToRgb01, styleFor } from "./coreStyle.js";
import { smoothLevel, targetLevel } from "./levelMath.js";

const PARTICLE_COUNT = 700;
// raio, inclinação, opacidade (iguais aos usados no teste visual dos shaders)
const RINGS = [
  { r: 1.45, tilt: 0.5, alpha: 0.7, dir: 1 },
  { r: 1.7, tilt: 1.15, alpha: 0.45, dir: -1 },
  { r: 1.95, tilt: -0.4, alpha: 0.3, dir: 1 },
];

/** Partículas determinísticas: 35% por dentro da esfera (dá profundidade), o resto em órbita. */
function makeParticles(count) {
  let seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const position = new Float32Array(count * 3);
  const aSeed = new Float32Array(count);
  const aSize = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    const inner = rnd() < 0.35;
    const r = inner ? 0.15 + rnd() * 0.8 : 1.3 + rnd() * 1.1;
    const th = Math.acos(2 * rnd() - 1);
    const ph = rnd() * Math.PI * 2;
    position[i * 3] = r * Math.sin(th) * Math.cos(ph);
    position[i * 3 + 1] = r * Math.cos(th) * 0.8;
    position[i * 3 + 2] = r * Math.sin(th) * Math.sin(ph);
    aSeed[i] = rnd();
    aSize[i] = 2.5 + rnd() * 6.5;
  }
  return { position, aSeed, aSize };
}

function Core({ status, levelRef, low }) {
  const statusRef = useRef(status);
  statusRef.current = status;

  // Estado "vivo" animado pelo GSAP (cores, velocidades) e pelo useFrame (tempo, nível).
  const live = useRef(null);
  if (!live.current) {
    const s = styleFor(status);
    live.current = {
      t: 0,
      level: 0,
      burst: 0,
      intensity: s.intensity,
      spin: s.spin,
      ringSpeed: s.ringSpeed,
      particleSpeed: s.particleSpeed,
      colorA: new THREE.Color(...hexToRgb01(s.colorA)),
      colorB: new THREE.Color(...hexToRgb01(s.colorB)),
    };
  }

  const group = useRef();
  const ringGroups = useRef([]);
  const ringMats = useRef([]);

  const uniforms = useMemo(() => {
    const L = live.current;
    return {
      front: {
        uTime: { value: 0 }, uLevel: { value: 0 }, uIntensity: { value: L.intensity }, uBack: { value: 0 },
        uColorA: { value: L.colorA }, uColorB: { value: L.colorB },
      },
      back: {
        uTime: { value: 0 }, uLevel: { value: 0 }, uIntensity: { value: L.intensity }, uBack: { value: 1 },
        uColorA: { value: L.colorA }, uColorB: { value: L.colorB },
      },
      halo: { uLevel: { value: 0 }, uIntensity: { value: L.intensity }, uBurst: { value: 0 }, uColor: { value: L.colorB } },
      pts: {
        uTime: { value: 0 }, uLevel: { value: 0 }, uPixel: { value: 1 }, uSpeed: { value: L.particleSpeed },
        uColor: { value: L.colorB }, uIntensity: { value: L.intensity },
      },
    };
  }, []);

  const particleGeo = useMemo(() => {
    const p = makeParticles(low ? 350 : PARTICLE_COUNT);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(p.position, 3));
    g.setAttribute("aSeed", new THREE.BufferAttribute(p.aSeed, 1));
    g.setAttribute("aSize", new THREE.BufferAttribute(p.aSize, 1));
    return g;
  }, [low]);
  useEffect(() => () => particleGeo.dispose(), [particleGeo]);

  // Transição entre estados: cores e velocidades deslizam, e um pulso de luz marca a mudança.
  useEffect(() => {
    const s = styleFor(status);
    const L = live.current;
    const [ar, ag, ab] = hexToRgb01(s.colorA);
    const [br, bg, bb] = hexToRgb01(s.colorB);
    const tl = gsap.timeline();
    tl.to(L.colorA, { r: ar, g: ag, b: ab, duration: 0.9, ease: "power2.out" }, 0)
      .to(L.colorB, { r: br, g: bg, b: bb, duration: 0.9, ease: "power2.out" }, 0)
      .to(L, { intensity: s.intensity, spin: s.spin, ringSpeed: s.ringSpeed, particleSpeed: s.particleSpeed, duration: 0.9, ease: "power2.out" }, 0)
      .fromTo(L, { burst: 1 }, { burst: 0, duration: 1.2, ease: "expo.out" }, 0);
    return () => tl.kill();
  }, [status]);

  const ringAngles = useRef(RINGS.map((_, i) => i * 1.7));

  useFrame((state, delta) => {
    const L = live.current;
    const dt = Math.min(delta, 0.05); // aba em segundo plano não pode dar um salto gigante
    L.t += dt;
    L.level = smoothLevel(L.level, targetLevel(statusRef.current, L.t, levelRef?.current), dt);
    const lvl = L.level;

    const { front, back, halo, pts } = uniforms;
    front.uTime.value = back.uTime.value = pts.uTime.value = L.t;
    front.uLevel.value = back.uLevel.value = halo.uLevel.value = pts.uLevel.value = lvl;
    front.uIntensity.value = back.uIntensity.value = halo.uIntensity.value = pts.uIntensity.value = L.intensity;
    halo.uBurst.value = L.burst;
    pts.uSpeed.value = L.particleSpeed;
    pts.uPixel.value = (state.size.height * state.viewport.dpr) / 900;

    if (group.current) {
      group.current.rotation.y += dt * L.spin * (1 + lvl * 3);
      group.current.scale.setScalar(1 + lvl * 0.1 + L.burst * 0.06 + Math.sin(L.t * 1.3) * 0.008);
    }
    ringAngles.current.forEach((a, i) => {
      ringAngles.current[i] = a + dt * L.ringSpeed * (0.2 + i * 0.1) * RINGS[i].dir * (1 + lvl);
      if (ringGroups.current[i]) ringGroups.current[i].rotation.y = ringAngles.current[i];
      if (ringMats.current[i]) ringMats.current[i].color.copy(L.colorB);
    });
  });

  const seg = low ? [48, 32] : [96, 64];

  return (
    <>
      {/* brilho atrás da esfera */}
      <mesh position={[0, 0, -0.3]} scale={3.1}>
        <planeGeometry args={[2, 2]} />
        <shaderMaterial
          vertexShader={HALO_VERT} fragmentShader={HALO_FRAG} uniforms={uniforms.halo}
          transparent depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending}
        />
      </mesh>

      {/* esfera: casca de trás (mais fraca) e da frente */}
      <group rotation={[0.35, 0, 0]}>
       <group ref={group}>
        <mesh renderOrder={1}>
          <sphereGeometry args={[1, seg[0], seg[1]]} />
          <shaderMaterial
            vertexShader={ORB_VERT} fragmentShader={ORB_FRAG} uniforms={uniforms.back}
            transparent depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending} side={THREE.BackSide}
          />
        </mesh>
        <mesh renderOrder={2}>
          <sphereGeometry args={[1, seg[0], seg[1]]} />
          <shaderMaterial
            vertexShader={ORB_VERT} fragmentShader={ORB_FRAG} uniforms={uniforms.front}
            transparent depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending} side={THREE.FrontSide}
          />
        </mesh>
       </group>
      </group>

      {/* anéis orbitais */}
      {RINGS.map((ring, i) => (
        <group key={i} ref={(el) => { ringGroups.current[i] = el; }}>
          <group rotation={[ring.tilt, 0, 0]}>
            <mesh rotation={[Math.PI / 2, 0, 0]} renderOrder={3}>
              <torusGeometry args={[ring.r, 0.008, 6, low ? 128 : 256]} />
              <meshBasicMaterial
                ref={(el) => { ringMats.current[i] = el; }}
                color="#38bdf8" transparent opacity={ring.alpha} depthWrite={false} depthTest={false}
                blending={THREE.AdditiveBlending}
              />
            </mesh>
          </group>
        </group>
      ))}

      {/* partículas */}
      <points geometry={particleGeo} frustumCulled={false} renderOrder={4}>
        <shaderMaterial
          vertexShader={PARTICLE_VERT} fragmentShader={PARTICLE_FRAG} uniforms={uniforms.pts}
          transparent depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending}
        />
      </points>
    </>
  );
}

/**
 * Núcleo holográfico. Ocupa o mesmo espaço (340x340) do CoreRings antigo; o canvas é maior
 * e vaza para os lados para os anéis e partículas respirarem. O clique é um botão invisível
 * sobre a esfera (acessível por teclado).
 */
export default function HoloCore({ status, onClick, levelRef, low = false }) {
  return (
    <div className="relative" style={{ width: 340, height: 340 }}>
      <div className="absolute pointer-events-none" style={{ inset: -90 }}>
        <Canvas
          dpr={low ? 1 : [1, 2]}
          gl={{ alpha: true, antialias: !low, powerPreference: "high-performance" }}
          camera={{ fov: 40, position: [0, 0, 5.6], near: 0.1, far: 50 }}
          style={{ background: "transparent" }}
        >
          <Core status={status} levelRef={levelRef} low={low} />
        </Canvas>
      </div>
      <button
        type="button"
        onClick={onClick}
        aria-label={`Ativar voz (${status})`}
        title={`${status}: toque para falar`}
        className="absolute rounded-full"
        style={{ left: "50%", top: "50%", width: 220, height: 220, transform: "translate(-50%, -50%)", background: "transparent", border: "none", cursor: "pointer" }}
      />
      <div
        className="absolute left-0 right-0 text-center text-[10px] tracking-[0.4em] pointer-events-none"
        style={{ bottom: -4, color: "#67e8f9", opacity: 0.75 }}
      >
        {status}
      </div>
    </div>
  );
}
