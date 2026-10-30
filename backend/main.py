import logging
import os
import time
import uuid
from typing import Any, Dict, List, Literal, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from connections import router as connections_router
from connections.tools import run_tools_phase

load_dotenv(override=True)  # ANTES de importar routines.*

from grounding import fetch_context  # noqa: E402
from media import diagnose, search_media_all  # noqa: E402
from scene_schema import extract_json, fallback_scene, sanitize_scene, visual_blocks  # noqa: E402

from routines.api import router as routines_router

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
# A API nativa quer só "gemini-2.5-flash". Aceita também "gemini/gemini-2.5-flash"
# (estilo litellm) e "models/...", que antes geravam a URL quebrada e o 404.
GEMINI_MODEL = (
    os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    .strip()
    .removeprefix("models/")
    .removeprefix("gemini/")
)

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
app.include_router(routines_router)  # depois de criar o app e o CORS


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
            1024, min(req.max_tokens or 400, 4096)
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


async def call_gemini(messages, req, json_mode=False, max_out=2048):
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
    gen = {
        "temperature": req.temperature or 0.7,
        "maxOutputTokens": max(256, min(req.max_tokens or 400, max_out)),
    }
    if json_mode:
        gen["responseMimeType"] = "application/json"  # o diretor de cena precisa de JSON puro
    if "2.5-flash" in GEMINI_MODEL:
        gen["thinkingConfig"] = {"thinkingBudget": 0}  # sem gastar tokens "pensando"
    payload = {
        "systemInstruction": {
            "parts": [{"text": system_text}]
        },
        "contents": contents,
        "generationConfig": gen,
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


# ---------------------------------------------------------------------------
# Motor de cenas: o LLM atua como "diretor" e devolve um roteiro visual.
# ---------------------------------------------------------------------------

DIRECTOR_PROMPT = """Você é o diretor visual do JARVIS. Quando o usuário pergunta algo, você NÃO escreve um texto: você dirige uma cena, como um documentário curto em que a fala e a imagem andam juntas. Responda em português do Brasil (exceto os campos "query", que ficam em inglês).
Retorne SOMENTE JSON válido, sem markdown, neste formato:
{
 "title": "título curto",
 "topic_kind": "process|structure|concept|comparison|timeline|geo|data|math",
 "media": [{"id":"m1","kind":"image|video","query":"busca em inglês, 2 a 5 palavras, substantivos concretos","caption":"legenda curta"}],
 "diagram": {"nodes":[{"id":"reator","label":"Reator","detail":"até 14 palavras","kind":"source|process|store|output|actor|concept|hazard","icon":"atom","x":15,"y":50}],
             "edges":[{"from":"reator","to":"vapor","label":"calor","flow":true}]},
 "chart": {"type":"bar|line","title":"...","unit":"%","series":[{"label":"...","value":0}]},
 "geo": {"points":[{"id":"sp","label":"São Paulo","detail":"...","lat":-23.55,"lon":-46.63,"layer":"cidades"}],"links":[{"from":"sp","to":"rj","label":"rota"}]},
 "beats": [{"say":"fala","layout":"title|media|diagram|split|chart|eye","media":"m1","reveal":["reator"],"focus":["reator"],"caption":"legenda opcional"}]
}
Todos os blocos (media, diagram, chart, geo) são OPCIONAIS: inclua só o que o assunto realmente pede, e use null ou omita o resto.

COMO ESCOLHER O QUE MOSTRAR
- Objeto, lugar, animal, obra, fenômeno visível no mundo real: media com kind "image" (e, se o movimento ajuda, um segundo item kind "video"). A query deve achar fotos reais: "nuclear power plant cooling towers", não "como funciona usina". Use termos GENÉRICOS e comuns em bancos de fotos, sem números nem nomes próprios raros ("nuclear power plant", não "Angra 2 reactor building"); para lugares famosos, o nome da cidade ou do país basta ("Rio de Janeiro skyline").
- Processo, sistema com partes, causa e efeito, ciclo: diagram com 5 a 9 nós e arestas com flow true mostrando o que se move.
- Comparação de quantidades, ranking, evolução numérica: chart (só com números que você conhece com segurança; senão não use chart).
- Lugares, rotas, distribuição geográfica: geo com layout "eye" (visão panorâmica). Use layers diferentes (ex.: "portos", "rotas") quando fizer sentido.
- Pergunta simples ou conversacional ("que horas", "me conte uma piada"): cena mínima, 1 ou 2 beats só com layout "title", sem media, diagram, chart nem geo.

COMO DIRIGIR (beats)
- A cena é para OLHAR e OUVIR, não para ler. A tela mostra imagens, desenhos, mapas e gráficos; quase não tem texto. Quem explica é a fala.
- 3 a 7 beats. Cada "say" tem UMA frase curta e natural (no máximo 2, até 180 caracteres) para ser FALADA (sem markdown, listas, emojis, parênteses ou siglas difíceis de ler). Juntos, os beats formam uma explicação completa e bem encadeada.
- "caption" é opcional e deve ter no máximo 4 palavras (um rótulo, nunca uma frase). Prefira deixar vazio.
- Mostre VÁRIAS coisas ao mesmo tempo sempre que o assunto permitir: o layout "split" põe a imagem/vídeo ao lado do diagrama, do gráfico ou do mapa. Use "split" como padrão depois do primeiro beat; use "diagram", "chart" ou "eye" sozinhos só quando o visual precisa de tela cheia.
- O primeiro beat contextualiza: layout "media" (ou "title") com a imagem principal. Depois use "split" ou "diagram". O último beat fecha a ideia.
- "reveal" lista os ids de nós/pontos que ENTRAM em cena naquele beat, na ordem em que são citados na fala. Todos os nós devem ser revelados em algum beat. "focus" lista 1 ou 2 ids que a fala está destacando agora.
- layouts: title = título grande sobre a imagem; media = imagem/vídeo grande; diagram = diagrama em tela cheia (mídia vira miniatura); split = mídia à esquerda e, à direita, o diagrama (ou o gráfico, ou o mapa, se não houver diagrama); chart = gráfico em tela cheia; eye = mapa panorâmico em tela cheia (precisa de geo).
- Coordenadas do diagrama: x de 8 a 92 e y de 12 a 88, em porcentagem do palco. Processos fluem da esquerda para a direita (ou em círculo, se for ciclo). Dê pelo menos 18 pontos de distância entre nós para não se sobreporem.
- icon (opcional) escolha entre: atom bolt flame drop gear fan cloud sun wind cell dna brain heart globe building factory chip database network lock rocket planet book scale coin chart person leaf thermo magnet wave flask pipe shield clock eye pin.
- Rótulos curtos (até 3 palavras). detail com no máximo 8 palavras, e só quando acrescenta algo que a imagem não mostra.

MÍNIMO VISUAL (vale para qualquer pergunta que não seja conversa solta)
- media com pelo menos 2 itens: uma imagem do assunto principal e outra de um detalhe ou ângulo diferente; acrescente um item kind "video" quando houver movimento ou processo visível. Troque a mídia mostrada ao longo dos beats (campo "media" de cada beat), em vez de repetir a mesma imagem.
- Além da mídia, inclua pelo menos UM bloco estruturado: diagram, chart ou geo.
- Se a pergunta cita lugares, países, cidades, usinas, rotas ou "onde", geo é OBRIGATÓRIO, com 3 a 10 pontos e pelo menos um beat com layout "eye". Use só coordenadas que você conhece com segurança; na dúvida, use a coordenada da cidade.
- Todo bloco que você criar precisa de um beat que o mostre: diagram em "diagram" ou "split", chart em "chart", geo em "eye".
- 4 a 7 beats, e a cada beat algo muda na tela (outra mídia, novos ids em "reveal", outro layout). Nunca fique com a mesma tela parada por dois beats seguidos.

CONTINUIDADE
- Se houver "CENA ANTERIOR" e a nova pergunta for um aprofundamento (ex.: "e como ocorre a fissão?"), monte uma cena NOVA focada no detalhe pedido, sem repetir o que já foi mostrado. Se o assunto mudou, ignore a cena anterior.

SEGURANÇA
- Não detalhe como fabricar armas, drogas ou causar danos. Em temas médicos, financeiros ou legais, seja cauteloso e mencione procurar um profissional quando fizer sentido. Não invente números nem fatos. Em geografia (em que cidade, estado ou país fica algo), só afirme o que souber com certeza; na dúvida, omita o estado ou fale só do país. Prefira dizer menos a dizer errado."""


class SceneRequest(BaseModel):
    messages: List[Message]
    previous: Optional[Dict[str, Any]] = None
    temperature: Optional[float] = 0.5
    max_tokens: Optional[int] = 2500


def _facts_block(facts: str) -> str:
    """Fatos de referência (Wikipédia) para o diretor não inventar."""
    if not facts:
        return ""
    return (
        "\n\nFATOS DE REFERÊNCIA (Wikipédia). Para qualquer nome, localização (cidade, estado, país), "
        "número ou coordenada, use SOMENTE o que está neste texto ou o que você sabe com certeza absoluta. "
        "Nunca contradiga o texto. Se algo não estiver aqui e você tiver dúvida, não afirme (fale de forma geral). "
        "Se o texto não tiver relação com a pergunta, ignore-o.\n" + facts
    )


def _previous_context(previous: Optional[Dict[str, Any]]) -> str:
    if not previous:
        return ""
    title = str(previous.get("title", ""))[:80]
    labels = [str(x)[:30] for x in (previous.get("labels") or [])[:12]]
    return f"\n\nCENA ANTERIOR: {title}. Elementos: {', '.join(labels)}."


def _last_user_text(messages) -> str:
    return next((m.content for m in reversed(messages) if m.role == "user"), "")


def _is_thin(scene: dict, question: str) -> bool:
    """Cena pobre para uma pergunta que merecia mais (conversa curta não conta)."""
    if len(question.split()) < 4:
        return False
    return visual_blocks(scene) < 2 or len(scene["beats"]) < 3


def _richness(scene: dict) -> int:
    return visual_blocks(scene) * 10 + len(scene["beats"])


def _scene_attempts(req):
    """Provedores do diretor, na ordem de SCENE_ORDER (padrão "groq,gemini")."""
    table = {}
    if GROQ_API_KEY:
        table["groq"] = lambda msgs: call_groq(msgs, req)
    if GEMINI_API_KEY:
        table["gemini"] = lambda msgs: call_gemini(msgs, req, json_mode=True, max_out=4096)
    order = [p.strip() for p in os.getenv("SCENE_ORDER", "groq,gemini").lower().split(",")]
    return [(name, table[name]) for name in order if name in table]


async def _direct_scene(messages, req):
    """Monta a cena com o primeiro provedor; se a cena vier pobre, tenta o próximo e fica com a mais rica."""
    question = _last_user_text(req.messages)
    best, best_name, errors = None, None, []
    for name, run in _scene_attempts(req):
        try:
            result = await run(messages)
            raw = result["choices"][0]["message"]["content"]
            scene = sanitize_scene(extract_json(raw))
        except Exception as exc:
            log.warning("Diretor (%s) falhou: %s", name, str(exc)[:300])
            errors.append(f"{name}: {str(exc)[:200]}")
            continue
        if best is None or _richness(scene) > _richness(best):
            best, best_name = scene, name
        if not _is_thin(scene, question):
            break
        log.info(
            "Cena pobre via %s (%d recursos visuais, %d beats); tentando o próximo provedor.",
            name, visual_blocks(scene), len(scene["beats"]),
        )
    return best, best_name, errors


@app.post("/v1/scene")
async def scene(req: SceneRequest):
    """Devolve um roteiro de cena (fala + instruções visuais) para o palco."""
    if not GROQ_API_KEY and not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Configure GROQ_API_KEY ou GEMINI_API_KEY no .env.")
    if not req.messages:
        raise HTTPException(status_code=400, detail="Envie pelo menos uma mensagem.")

    chat_req = ChatRequest(messages=req.messages, temperature=req.temperature, max_tokens=req.max_tokens)
    started = time.time()
    facts = await fetch_context(_last_user_text(req.messages))
    system = DIRECTOR_PROMPT + _facts_block(facts) + _previous_context(req.previous)
    result, provider, errors = await _direct_scene(get_messages(chat_req, system), chat_req)

    if result is None:
        log.warning("Diretor falhou em todos os provedores; usando resposta simples.")
        try:
            simple = await chat_completions(chat_req)
            text = simple["choices"][0]["message"]["content"]
            result, provider = fallback_scene(text), simple.get("provider", "simple")
        except HTTPException:
            raise HTTPException(
                status_code=502,
                detail={"message": "Não foi possível montar a cena.", "errors": errors},
            )

    result["answer"] = " ".join(b["say"] for b in result["beats"])
    result["provider"] = provider
    result["id"] = uuid.uuid4().hex[:10]
    log.info(
        "Cena '%s' via %s em %.2fs (%d beats, %d mídias, diagrama=%d nós, gráfico=%s, mapa=%d pontos)",
        result["title"], provider, time.time() - started, len(result["beats"]),
        len(result.get("media") or []),
        len((result.get("diagram") or {}).get("nodes", [])),
        "sim" if result.get("chart") else "não",
        len((result.get("geo") or {}).get("points", [])),
    )
    return result


@app.get("/v1/media/search")
async def media_search(q: str, kind: str = "image"):
    """Busca uma imagem ou vídeo de referência. Devolve {item: null} se nada serve."""
    if kind not in {"image", "video"}:
        raise HTTPException(status_code=400, detail="kind deve ser image ou video.")
    results, tried = await search_media_all(q, kind)
    # "alternatives": próximos candidatos, para o front usar se o primeiro não carregar.
    # "tried" só vem quando não achou nada: mostra qual provedor falhou e por quê.
    return {
        "item": results[0] if results else None,
        "alternatives": results[1:4],
        "tried": [] if results else tried,
    }


@app.get("/v1/media/diagnose")
async def media_diagnose(q: str = "nuclear power plant"):
    """Testa cada provedor de mídia isoladamente. Abra no navegador para ver quem está falhando."""
    return await diagnose(q)