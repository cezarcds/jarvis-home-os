// Palavra-chave de cada trecho da cena (a que se forma em partículas na tela). Lógica pura.

export const KEYWORD_MAX_CHARS = 16;

/** Limpa o texto: sem pontuação nas pontas, no máximo 2 palavras e 16 letras. Vazio se não couber. */
export function cleanKeyword(raw) {
  const words = String(raw ?? "")
    .replace(/[\s ]+/g, " ")
    .trim()
    .replace(/^[\s.,;:!?"'()\-–—]+|[\s.,;:!?"'()\-–—]+$/g, "")
    .split(" ")
    .filter(Boolean);
  if (!words.length) return "";
  let out = words.slice(0, 2).join(" ");
  if (out.length > KEYWORD_MAX_CHARS) out = words[0];
  return out.length > KEYWORD_MAX_CHARS ? "" : out;
}

/**
 * O diretor escolhe a palavra (`beat.keyword`). Sem ela, só números ganham destaque
 * ("93 milhões de km" -> "93 milhões"): termos e fatos ficam nas chamadas laterais.
 */
export function pickKeyword(beat) {
  if (!beat) return "";
  const own = cleanKeyword(beat.keyword);
  if (own) return own;
  const num = (beat.callouts || []).find((c) => c.kind === "number");
  return num ? cleanKeyword(num.text) : "";
}
