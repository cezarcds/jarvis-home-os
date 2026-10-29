"""Armazenamento das rotinas em JSON (backend/data/routines.json), com escrita atômica."""
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import Routine
from .textutil import slugify

log = logging.getLogger("jarvis.routines")

DATA_DIR = Path(os.getenv("JARVIS_DATA_DIR") or Path(__file__).resolve().parent.parent / "data")
FILE = DATA_DIR / "routines.json"
_lock = threading.RLock()

SEEDS = [
    {
        "id": "bom-dia",
        "nome": "Bom dia",
        "descricao": "Panorama da manhã: agenda de hoje, emails aguardando resposta e clima.",
        "gatilhos": [
            "bom dia",
            "bom dia jarvis",
            "como está meu dia hoje",
            "como tá meu dia hoje",
            "o que tenho para hoje",
            "o que eu tenho que fazer hoje",
            "resumo do dia",
        ],
        "passos": [
            {"id": "agenda", "ferramenta": "agenda.hoje"},
            {"id": "emails", "ferramenta": "gmail.para_responder", "params": {"max": 5}},
            {"id": "clima", "ferramenta": "clima.agora"},
        ],
        "tela": {"titulo": "Bom dia", "blocos": ["agenda", "emails", "clima"]},
        "fala": {"modo": "resumo"},
    },
    {
        "id": "fim-do-dia",
        "nome": "Fim do dia",
        "descricao": "Fechamento: agenda de amanhã e emails que ainda precisam de resposta.",
        "gatilhos": ["encerrar o dia", "fim do expediente", "como está amanhã", "o que tenho amanhã"],
        "passos": [
            {"id": "agenda", "ferramenta": "agenda.amanha"},
            {"id": "emails", "ferramenta": "gmail.para_responder", "params": {"max": 5}},
        ],
        "tela": {"titulo": "Fim do dia", "blocos": ["agenda", "emails"]},
        "fala": {"modo": "resumo"},
    },
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read() -> List[Routine]:
    if not FILE.exists():
        routines = [Routine.model_validate({**s, "criada_em": _now(), "atualizada_em": _now()}) for s in SEEDS]
        _write(routines)
        return routines
    try:
        raw = json.loads(FILE.read_text(encoding="utf-8"))
        return [Routine.model_validate(r) for r in raw]
    except Exception:  # noqa: BLE001
        log.exception("routines.json inválido; fazendo backup e recriando")
        FILE.replace(FILE.with_suffix(".json.bak"))
        return _read()


def _write(routines: List[Routine]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps([r.model_dump() for r in routines], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp, FILE)


def list_routines() -> List[Routine]:
    with _lock:
        return _read()


def get(routine_id: str) -> Optional[Routine]:
    with _lock:
        return next((r for r in _read() if r.id == routine_id), None)


def upsert(routine: Routine) -> Routine:
    with _lock:
        items = _read()
        now = _now()
        existing = next((r for r in items if r.id == routine.id), None) if routine.id else None
        if existing:
            routine.criada_em = existing.criada_em
            routine.atualizada_em = now
            items = [routine if r.id == routine.id else r for r in items]
        else:
            base = routine.id or slugify(routine.nome)
            taken = {r.id for r in items}
            rid, n = base, 2
            while rid in taken:
                rid = f"{base}-{n}"
                n += 1
            routine.id = rid
            routine.criada_em = routine.atualizada_em = now
            items.append(routine)
        _write(items)
        return routine


def delete(routine_id: str) -> bool:
    with _lock:
        items = _read()
        rest = [r for r in items if r.id != routine_id]
        if len(rest) == len(items):
            return False
        _write(rest)
        return True
