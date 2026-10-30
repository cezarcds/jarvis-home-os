"""Cliente LLM com fallback Groq <-> Gemini (só depende de httpx).

Ordem dos provedores: variável LLM_ORDER (padrão "groq,gemini").
Para Gemini primeiro: LLM_ORDER=gemini,groq
"""
import base64
import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

import httpx

log = logging.getLogger("jarvis.llm")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    pass


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def provider_order() -> List[str]:
    """Provedores configurados (com chave) na ordem de preferência."""
    keys = {"groq": _env("GROQ_API_KEY"), "gemini": _env("GEMINI_API_KEY")}
    out: List[str] = []
    for p in _env("LLM_ORDER", "groq,gemini").lower().split(","):
        p = p.strip()
        if p in keys and keys[p] and p not in out:
            out.append(p)
    return out


async def _groq(messages, system, max_tokens, temperature, timeout) -> str:
    full = ([{"role": "system", "content": system}] if system else []) + messages
    payload = {
        "model": _env("GROQ_MODEL", "openai/gpt-oss-20b"),
        "messages": full,
        "temperature": temperature,
        "max_completion_tokens": max(1024, min(max_tokens, 4096)),
        "reasoning_effort": "low",
        "include_reasoning": False,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {_env('GROQ_API_KEY')}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=8.0)) as client:
        r = await client.post(GROQ_URL, headers=headers, json=payload)
    if r.is_error:
        raise LLMError(f"Groq HTTP {r.status_code}: {r.text[:300]}")
    choices = r.json().get("choices") or []
    content = choices[0].get("message", {}).get("content") if choices else None
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str) or not content.strip():
        raise LLMError("Groq retornou conteúdo vazio")
    return content.strip()


async def _gemini(messages, system, max_tokens, temperature, timeout, images=None) -> str:
    # Aceita "gemini/gemini-2.5-flash" (estilo litellm) e "models/..." sem quebrar a URL.
    model = (_env("GEMINI_VISION_MODEL") if images else "") or _env("GEMINI_MODEL", "gemini-2.5-flash")
    model = model.removeprefix("models/").removeprefix("gemini/")
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] != "system"
    ]
    if not contents:
        raise LLMError("Sem mensagens para o Gemini")
    if images:  # as imagens vão junto da última fala do usuário
        last_user = next((c for c in reversed(contents) if c["role"] == "user"), contents[-1])
        for img in images:
            last_user["parts"].append(
                {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(img).decode("ascii")}}
            )
    gen = {"temperature": temperature, "maxOutputTokens": max(256, min(max_tokens, 4096))}
    if "2.5-flash" in model:
        # Respostas rápidas (sem pensar). Para olhar gráficos, GEMINI_VISION_THINKING=512 melhora a análise.
        budget = _env("GEMINI_VISION_THINKING", "0") if images else "0"
        gen["thinkingConfig"] = {"thinkingBudget": int(budget) if budget.isdigit() else 0}
        if images and gen["thinkingConfig"]["thinkingBudget"]:
            gen["maxOutputTokens"] = max(gen["maxOutputTokens"], 1024 + gen["thinkingConfig"]["thinkingBudget"])
    payload = {"contents": contents, "generationConfig": gen}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    headers = {"x-goog-api-key": _env("GEMINI_API_KEY"), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=8.0)) as client:
        r = await client.post(GEMINI_URL.format(model=model), headers=headers, json=payload)
    if r.is_error:
        raise LLMError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    cands = r.json().get("candidates") or []
    if not cands:
        raise LLMError("Gemini sem candidatos")
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
    if not text:
        raise LLMError("Gemini retornou conteúdo vazio")
    return text


async def complete(
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    max_tokens: int = 400,
    temperature: float = 0.7,
    timeout: float = 20.0,
    images: Optional[List[bytes]] = None,
) -> Tuple[str, str]:
    """Retorna (texto, provedor). Tenta cada provedor na ordem até um responder.

    Com `images` (JPEG), só o Gemini serve: o Groq/GPT-OSS não enxerga imagem.
    """
    order = provider_order()
    if images:
        order = [p for p in order if p == "gemini"]
        if not order:
            raise LLMError("Ver a tela precisa de GEMINI_API_KEY no .env")
    if not order:
        raise LLMError("Configure GROQ_API_KEY ou GEMINI_API_KEY no .env")
    errors = []
    for name in order:
        try:
            if name == "groq":
                return await _groq(messages, system, max_tokens, temperature, timeout), name
            return await _gemini(messages, system, max_tokens, temperature, timeout, images), name
        except Exception as exc:  # noqa: BLE001 - qualquer falha cai para o próximo
            log.warning("%s falhou: %s", name, str(exc)[:300])
            errors.append(f"{name}: {str(exc)[:200]}")
    raise LLMError(" | ".join(errors))


def extract_json(text: str) -> dict:
    """Extrai o primeiro objeto JSON de uma resposta de LLM (tolera cercas ``` e texto extra)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE)
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(t[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    raise LLMError("A resposta do modelo não veio em JSON válido")