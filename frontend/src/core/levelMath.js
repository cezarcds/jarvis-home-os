// Matemática pura da reação à voz (sem React nem WebGL, para poder ser testada).
// "Nível" é sempre um número de 0 a 1: 0 = silêncio, 1 = voz forte.

const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

/**
 * Nível a partir das amostras do microfone (AnalyserNode.getByteTimeDomainData:
 * bytes de 0 a 255 com o silêncio em 128). Ruído de fundo abaixo da porta vira 0.
 */
export function rmsLevel(bytes, gate = 0.012, gain = 3.4) {
  const n = bytes?.length || 0;
  if (!n) return 0;
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const v = (bytes[i] - 128) / 128;
    sum += v * v;
  }
  const rms = Math.sqrt(sum / n);
  if (rms < gate) return 0;
  return clamp01((rms - gate) * gain);
}

/**
 * Suavização com ataque rápido e queda lenta: o núcleo "salta" quando a voz sobe e
 * relaxa devagar quando ela cai, em vez de tremer a cada quadro. Independe do FPS.
 */
export function smoothLevel(prev, target, dt, attack = 16, release = 3.5) {
  const rate = target > prev ? attack : release;
  const k = 1 - Math.exp(-rate * Math.max(0, dt));
  return prev + (target - prev) * k;
}

/** Fala sintética (o navegador não deixa capturar a voz da síntese): ritmo de sílabas. */
export function speakingEnvelope(t) {
  const syl = Math.abs(Math.sin(t * 7.3)) * (0.6 + 0.4 * Math.sin(t * 2.1));
  const flutter = Math.pow(Math.sin(t * 17.0), 2) * 0.15;
  return clamp01(0.3 + 0.38 * syl + flutter);
}

/** Respiração leve enquanto escuta sem sinal do microfone. */
export function listeningIdle(t) {
  return clamp01(0.12 + 0.05 * Math.sin(t * 2.0));
}

/** Pulso regular enquanto o Jarvis pensa. */
export function processingPulse(t) {
  return clamp01(0.18 + 0.12 * (0.5 + 0.5 * Math.sin(t * 5.0)));
}

/** Repouso: quase imóvel. */
export function standbyIdle(t) {
  return clamp01(0.03 + 0.015 * Math.sin(t * 1.2));
}

/**
 * Nível "alvo" de cada estado. `mic` é o nível do microfone (0..1) ou null/undefined
 * quando não há sinal (sem permissão, ou analisador desligado).
 */
export function targetLevel(status, t, mic) {
  switch (status) {
    case "LISTENING":
      return typeof mic === "number" && mic >= 0 ? mic : listeningIdle(t);
    case "SPEAKING":
      return speakingEnvelope(t);
    case "PROCESSING":
      return processingPulse(t);
    default:
      return standbyIdle(t);
  }
}
