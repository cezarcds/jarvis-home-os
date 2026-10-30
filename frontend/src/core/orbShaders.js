// Shaders do núcleo holográfico. Escritos em GLSL ES 1.00 e só com os built-ins que o
// THREE.ShaderMaterial já declara (position, normal, uv, modelViewMatrix, projectionMatrix,
// normalMatrix), então funcionam no Three.js (WebGL1 e WebGL2) sem ajuste.
// Todos usam mistura aditiva: o brilho soma, como luz.

const NOISE = /* glsl */ `
float hash(vec3 p) {
  p = fract(p * 0.3183099 + vec3(0.1, 0.2, 0.3));
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float vnoise(vec3 x) {
  vec3 i = floor(x);
  vec3 f = fract(x);
  f = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(mix(hash(i + vec3(0.0, 0.0, 0.0)), hash(i + vec3(1.0, 0.0, 0.0)), f.x),
        mix(hash(i + vec3(0.0, 1.0, 0.0)), hash(i + vec3(1.0, 1.0, 0.0)), f.x), f.y),
    mix(mix(hash(i + vec3(0.0, 0.0, 1.0)), hash(i + vec3(1.0, 0.0, 1.0)), f.x),
        mix(hash(i + vec3(0.0, 1.0, 1.0)), hash(i + vec3(1.0, 1.0, 1.0)), f.x), f.y),
    f.z);
}
float fbm(vec3 p) {
  float a = 0.5;
  float s = 0.0;
  for (int i = 0; i < 4; i++) {
    s += a * vnoise(p);
    p = p * 2.03 + vec3(1.7, 9.2, 3.1);
    a *= 0.5;
  }
  return s;
}
`;

/** Casca da esfera: borda luminosa (fresnel), energia correndo por dentro e ondulação pela voz. */
export const ORB_VERT = /* glsl */ `
uniform float uTime;
uniform float uLevel;
varying vec3 vNormal;
varying vec3 vPos;
varying vec3 vView;
${NOISE}
void main() {
  vec3 p = position;
  float n = vnoise(p * 2.2 + vec3(0.0, uTime * 0.6, uTime * 0.3));
  float disp = (n - 0.5) * (0.03 + uLevel * 0.16);
  vec4 mv = modelViewMatrix * vec4(p + normal * disp, 1.0);
  vNormal = normalize(normalMatrix * normal);
  vPos = p;
  vView = -mv.xyz;
  gl_Position = projectionMatrix * mv;
}
`;

export const ORB_FRAG = /* glsl */ `
precision highp float;
uniform float uTime;
uniform float uLevel;
uniform float uIntensity;
uniform float uBack;
uniform vec3 uColorA;
uniform vec3 uColorB;
varying vec3 vNormal;
varying vec3 vPos;
varying vec3 vView;
${NOISE}
void main() {
  vec3 N = normalize(vNormal);
  vec3 V = normalize(vView);
  // 1 no centro, 0 na borda. abs() deixa a casca de trás (uBack) usar a mesma conta.
  float ndv = clamp(abs(dot(N, V)), 0.0, 1.0);
  float fres = pow(1.0 - ndv, 3.0);

  vec3 q = vPos * 1.7 + uBack * vec3(3.1, 1.3, -2.2);
  float t = uTime * 0.22;
  float warp = fbm(q * 1.4 - vec3(t));
  float f1 = fbm(q + vec3(t, -t * 0.7, t * 0.5) + warp * 0.9);
  float ridge = pow(1.0 - abs(f1 * 2.0 - 1.0), 7.0);   // filamentos finos de energia
  float cells = smoothstep(0.55, 0.8, f1) * 0.25;
  float scan = 0.94 + 0.06 * sin(vPos.y * 60.0 - uTime * 2.5);

  vec3 col = mix(uColorA, uColorB, clamp(fres * 1.2 + ridge * 0.8, 0.0, 1.0));
  col += uColorB * ridge * (0.45 + uLevel * 0.9);
  col += vec3(1.0) * fres * fres * 0.25;
  col = 1.0 - exp(-col * 1.25);   // tone mapping suave: a voz intensifica sem estourar em branco

  float body = 0.035 + ridge * 0.55 + cells * 0.3;
  float alpha = (body + fres * 1.05) * scan * uIntensity;
  alpha *= mix(1.0, 0.38, uBack);
  gl_FragColor = vec4(col, clamp(alpha, 0.0, 1.0));
}
`;

/** Brilho suave atrás da esfera (um plano com gradiente radial). */
export const HALO_VERT = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

export const HALO_FRAG = /* glsl */ `
precision highp float;
uniform float uLevel;
uniform float uIntensity;
uniform float uBurst;
uniform vec3 uColor;
varying vec2 vUv;
void main() {
  float r = length(vUv - 0.5) * 2.0;
  float glow = exp(-r * r * 3.4) * (0.45 + uLevel * 0.45);
  float ring = exp(-pow((r - (0.55 + uBurst * 0.4)) * 9.0, 2.0)) * uBurst;
  float a = (glow * 0.65 + ring * 0.8) * uIntensity * smoothstep(1.0, 0.8, r);
  gl_FragColor = vec4(uColor, clamp(a, 0.0, 1.0));
}
`;

/** Poeira de luz em órbita, que se afasta quando a voz aumenta. */
export const PARTICLE_VERT = /* glsl */ `
attribute float aSeed;
attribute float aSize;
uniform float uTime;
uniform float uLevel;
uniform float uPixel;
uniform float uSpeed;
varying float vTw;
void main() {
  float a = uTime * uSpeed * (0.05 + aSeed * 0.08);
  float c = cos(a);
  float s = sin(a);
  vec3 p = position;
  p.xz = mat2(c, -s, s, c) * p.xz;
  p *= 1.0 + uLevel * 0.35 * (0.5 + aSeed);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = aSize * uPixel * (1.0 + uLevel * 0.8) * (6.0 / -mv.z);
  vTw = 0.55 + 0.45 * sin(uTime * (1.0 + aSeed * 2.0) + aSeed * 40.0);
}
`;

export const PARTICLE_FRAG = /* glsl */ `
precision highp float;
uniform vec3 uColor;
uniform float uIntensity;
varying float vTw;
void main() {
  float r = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.0, r);
  gl_FragColor = vec4(uColor, a * a * vTw * uIntensity);
}
`;
