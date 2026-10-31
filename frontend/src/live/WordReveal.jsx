import React from "react";

/**
 * As palavras entram uma a uma (subindo e saindo do desfoque), como se fossem ditas.
 * Troque `text` e a animação recomeça. O tempo total é limitado para frases longas não demorarem.
 */
export default function WordReveal({ text, stepMs = 42, maxMs = 1900, className = "" }) {
  const words = String(text ?? "").split(/\s+/).filter(Boolean);
  const step = Math.min(stepMs, words.length > 1 ? maxMs / (words.length - 1) : stepMs);
  return (
    <span className={className} key={text}>
      {words.map((w, i) => (
        <React.Fragment key={i}>
          <span className="wr-w" style={{ animationDelay: `${Math.round(i * step)}ms` }}>{w}</span>{" "}
        </React.Fragment>
      ))}
    </span>
  );
}
