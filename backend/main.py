
import logging
import os
import time
import uuid
from typing import List, Literal, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from connections import router as connections_router
from connections.tools import run_tools_phase

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("jarvis")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv(
    "GROQ_MODEL", "openai/gpt-oss-20b"
).strip()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL", "gemini-3.8-flash"
).strip()

GROQ_URL = (
    "https://api.groq.com/openai/v1/chat/completions"
)
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/{model}:generateContent"
)

SYSTEM_PROMPT = (
    "Você é JARVIS, um assistente residencial sofisticado, "
    "calmo e levemente irônico. Responda sempre em português "
    "do Brasil, de forma concisa, com 1 a 4 frases, pois "
    "suas respostas serão faladas em voz alta. "
    "Não use markdown, listas nem emojis. "
    "Priorize respostas diretas e naturais."
)

app = FastAPI(title="OpenJarvis Home OS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(connections_router)


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 400


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "provider": "groq_with_gemini_fallback",
        "primary_model": GROQ_MODEL,
        "fallback_model": GEMINI_MODEL,
        "groq_configured": bool(GROQ_API_KEY),
        "gemini_configured": bool(GEMINI_API_KEY),
    }


def get_messages(req: ChatRequest, system_prompt: str = SYSTEM_PROMPT):
    messages = [
        {"role": "system", "content": system_prompt}
    ]

    messages.extend(
        message.model_dump()
        for message in req.messages
        if message.role != "system"
    )

    return messages


async def call_groq(messages, req):
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "max_completion_tokens": max(
            1024, min(req.max_tokens or 400, 2048)
        ),
        "reasoning_effort": "low",
        "include_reasoning": False,
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(45.0, connect=10.0)
    ) as client:
        response = await client.post(
            GROQ_URL,
            headers=headers,
            json=payload,
        )

    if response.is_error:
        raise RuntimeError(
            f"Groq HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    result = response.json()
    choices = result.get("choices", [])

    if not choices:
        raise RuntimeError("Groq retornou choices vazio.")

    content = choices[0].get("message", {}).get("content")

    if isinstance(content, list):
        content = "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict)
        )

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Groq retornou conteúdo vazio.")

    result["provider"] = "groq"
    return result


async def call_gemini(messages, req):
    # Converte o formato de mensagens para a API do Gemini.
    contents = []

    for message in messages:
        if message["role"] == "system":
            continue

        role = (
            "model"
            if message["role"] == "assistant"
            else "user"
        )

        contents.append({
            "role": role,
            "parts": [{"text": message["content"]}],
        })

    if not contents:
        raise RuntimeError(
            "Não há mensagens para enviar ao Gemini."
        )

    # A instrução de sistema é enviada separadamente.
    system_text = next(
        (message["content"] for message in messages if message["role"] == "system"),
        SYSTEM_PROMPT,
    )
    payload = {
        "systemInstruction": {
            "parts": [{"text": system_text}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": req.temperature or 0.7,
            "maxOutputTokens": max(
                256, min(req.max_tokens or 400, 2048)
            ),
        },
    }

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json",
    }

    url = GEMINI_URL.format(model=GEMINI_MODEL)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(45.0, connect=10.0)
    ) as client:
        response = await client.post(
            url,
            headers=headers,
            json=payload,
        )

    if response.is_error:
        raise RuntimeError(
            f"Gemini HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    result = response.json()
    candidates = result.get("candidates", [])

    if not candidates:
        raise RuntimeError(
            "Gemini não retornou candidatos. "
            f"Resposta: {str(result)[:300]}"
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    # Ignora partes identificadas como raciocínio interno.
    text_parts = [
        part.get("text", "")
        for part in parts
        if isinstance(part, dict)
        and not part.get("thought", False)
    ]

    content = "".join(text_parts).strip()

    if not content:
        raise RuntimeError(
            "Gemini retornou conteúdo vazio."
        )

    # Normaliza a resposta do Gemini para o formato
    # compatível com a interface que já usa o Groq.
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": GEMINI_MODEL,
        "provider": "gemini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
    }




@app.post("/v1/visual-explain")
async def visual_explain(req: ChatRequest):
    """Retorna uma explicação e um plano visual estruturado para a interface."""
    tools = run_tools_phase(req.messages)
    if tools.direct_answer:
        return {"answer": tools.direct_answer, "title": "Conexão necessária", "visuals": [], "actions": tools.actions}
    if not GROQ_API_KEY and not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Configure GROQ_API_KEY ou GEMINI_API_KEY no .env.")
    if not req.messages:
        raise HTTPException(status_code=400, detail="Envie pelo menos uma mensagem.")

    visual_system = """Você é JARVIS, um professor visual. Responda em português brasileiro.
Crie uma explicação falável e um plano de recursos visuais para acompanhar a fala.
Retorne SOMENTE JSON válido, sem markdown, com este formato exato:
{"answer":"explicação falável de 3 a 6 frases","title":"título curto","visuals":[{"type":"diagram|steps|concepts|comparison|timeline|equation","title":"título do painel","caption":"legenda curta","items":[{"label":"rótulo curto","detail":"descrição de até 12 palavras"}]}]}
Inclua de 1 a 3 painéis visuais. Cada painel deve ter 2 a 5 items. Escolha o tipo adequado ao assunto. Use diagram para processos/partes de um sistema, steps para sequência, concepts para conceitos, comparison para diferenças, timeline para história e equation para matemática. Não invente imagens externas nem URLs. Priorize visualizações que possam ser desenhadas diretamente na interface. O texto de answer deve ser natural para voz, sem listas nem markdown. Não inclua conteúdo perigoso; para temas médicos, financeiros ou de segurança, mantenha cautela e contexto."""
    messages = get_messages(req, visual_system + tools.system_addendum)
    errors = []
    raw = None
    if GROQ_API_KEY:
        try:
            result = await call_groq(messages, req)
            raw = result["choices"][0]["message"]["content"]
        except Exception as exc:
            log.warning("Visual Explain Groq falhou: %s", str(exc)[:300])
            errors.append(f"Groq: {str(exc)[:200]}")
    if raw is None and GEMINI_API_KEY:
        try:
            result = await call_gemini(messages, req)
            raw = result["choices"][0]["message"]["content"]
        except Exception as exc:
            log.warning("Visual Explain Gemini falhou: %s", str(exc)[:300])
            errors.append(f"Gemini: {str(exc)[:200]}")
    if not raw:
        raise HTTPException(status_code=502, detail={"message":"Não foi possível montar a explicação visual.","errors":errors})
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = __import__("json").loads(cleaned)
        if not isinstance(data.get("answer"), str) or not isinstance(data.get("visuals"), list):
            raise ValueError("Estrutura incompleta")
        allowed = {"diagram", "steps", "concepts", "comparison", "timeline", "equation"}
        data["visuals"] = [v for v in data["visuals"][:3] if isinstance(v, dict) and v.get("type") in allowed]
        return data
    except Exception as exc:
        log.warning("JSON visual inválido: %s | conteúdo: %s", exc, raw[:300])
        return {"answer": raw.strip(), "title": "Explicação", "visuals": [{"type":"concepts","title":"Ideias principais","caption":"Resumo visual","items":[{"label":"Explicação","detail":"Consulte a resposta falada e exibida ao lado."}]}]}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    tools = run_tools_phase(req.messages)
    if tools.direct_answer:
        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "jarvis-connections",
            "provider": "jarvis-connections",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": tools.direct_answer}, "finish_reason": "stop"}],
            "actions": tools.actions,
        }
    if not GROQ_API_KEY and not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Configure GROQ_API_KEY ou GEMINI_API_KEY no .env.",
        )

    if not req.messages:
        raise HTTPException(
            status_code=400,
            detail="Envie pelo menos uma mensagem.",
        )

    messages = get_messages(req, SYSTEM_PROMPT + tools.system_addendum)
    started = time.time()
    errors = []

    # 1. Provedor principal: Groq.
    if GROQ_API_KEY:
        try:
            log.info("Tentando Groq: %s", GROQ_MODEL)
            result = await call_groq(messages, req)

            log.info(
                "Resposta recebida do Groq em %.2fs",
                time.time() - started,
            )
            return result

        except Exception as exc:
            log.warning("Groq falhou: %s", str(exc)[:500])
            errors.append(f"Groq: {str(exc)[:300]}")

    # 2. Alternativa: Gemini.
    if GEMINI_API_KEY:
        try:
            log.info("Tentando Gemini: %s", GEMINI_MODEL)
            result = await call_gemini(messages, req)

            log.info(
                "Resposta recebida do Gemini em %.2fs",
                time.time() - started,
            )
            return result

        except Exception as exc:
            log.exception("Gemini falhou")
            errors.append(f"Gemini: {str(exc)[:300]}")

    log.error("Todos os provedores falharam: %s", errors)

    raise HTTPException(
        status_code=502,
        detail={
            "message": (
                "Não foi possível obter resposta de nenhum "
                "provedor de IA."
            ),
            "errors": errors,
        },
    )
