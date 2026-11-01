"""Armazenamento das tarefas, execuções, itens idempotentes e contadores diários (SQLite).

Usa o mesmo banco do cofre e da auditoria (~/.jarvis/jarvis.db, fora do repositório). As tabelas são
criadas na primeira conexão. Os campos das tarefas NÃO são criptografados: o contrato proíbe segredos
em tarefa (credenciais ficam no cofre e o LLM nunca as vê).

Idempotência (nunca repetir o mesmo item):
- `itens.chave` é única. Um item é reservado ('iniciado') ANTES de a ferramenta rodar e confirmado
  ('ok') depois. Se o programa cair no meio, a reserva fica 'iniciado': na rodada seguinte o item é
  tratado como INCERTO (talvez já tenha sido enviado) e a tarefa pausa para você conferir, em vez
  de arriscar duplicar.
- `execucoes` tem UNIQUE(tarefa_id, disparo): a mesma rodada agendada nunca dispara duas vezes,
  nem depois de um reinício.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing
from typing import Any, Dict, List, Optional

from connections import db

from .models import Tarefa, carregar

SCHEMA = """
CREATE TABLE IF NOT EXISTS tarefas (
    id TEXT PRIMARY KEY,
    dados TEXT NOT NULL,
    ativa INTEGER NOT NULL DEFAULT 1,
    criada REAL NOT NULL,
    atualizada REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS execucoes (
    id TEXT PRIMARY KEY,
    tarefa_id TEXT NOT NULL,
    disparo TEXT NOT NULL,
    inicio REAL NOT NULL,
    fim REAL,
    estado TEXT NOT NULL,
    motivo TEXT NOT NULL DEFAULT '',
    passos TEXT NOT NULL DEFAULT '[]',
    UNIQUE (tarefa_id, disparo)
);
CREATE INDEX IF NOT EXISTS idx_execucoes_tarefa ON execucoes (tarefa_id, inicio DESC);
CREATE TABLE IF NOT EXISTS itens (
    chave TEXT PRIMARY KEY,
    tarefa_id TEXT NOT NULL,
    execucao_id TEXT NOT NULL,
    estado TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS usos (
    tarefa_id TEXT NOT NULL,
    ferramenta TEXT NOT NULL,
    dia TEXT NOT NULL,
    n INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tarefa_id, ferramenta, dia)
);
"""

ESTADOS_FINAIS = ("ok", "falhou", "pausada", "cancelada", "interrompida", "perdida")
_prontos: set = set()


def _conn() -> sqlite3.Connection:
    c = db.connect()
    chave = str(db.data_dir() / db.DB_FILE)
    if chave not in _prontos:
        c.executescript(SCHEMA)
        c.commit()
        _prontos.add(chave)
    return c


def reset_state() -> None:
    _prontos.clear()


# ---- tarefas ----------------------------------------------------------------------------------

def salvar(tarefa: Tarefa, agora: Optional[float] = None) -> None:
    agora = time.time() if agora is None else agora
    dados = json.dumps(tarefa.dump(), ensure_ascii=False)
    with closing(_conn()) as c, c:
        c.execute(
            "INSERT INTO tarefas(id,dados,ativa,criada,atualizada) VALUES(?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET dados=excluded.dados, ativa=excluded.ativa, atualizada=excluded.atualizada",
            (tarefa.id, dados, int(tarefa.ativa), agora, agora))


def obter(id_: str) -> Optional[Tarefa]:
    with closing(_conn()) as c:
        r = c.execute("SELECT dados, ativa FROM tarefas WHERE id=?", (id_,)).fetchone()
    return _montar(r)


def _montar(r) -> Optional[Tarefa]:
    if not r:
        return None
    t = carregar(json.loads(r["dados"]))
    t.ativa = bool(r["ativa"])
    return t


def listar() -> List[Tarefa]:
    with closing(_conn()) as c:
        rows = c.execute("SELECT dados, ativa FROM tarefas ORDER BY id").fetchall()
    return [_montar(r) for r in rows]


def criada_em(id_: str) -> Optional[float]:
    with closing(_conn()) as c:
        r = c.execute("SELECT criada FROM tarefas WHERE id=?", (id_,)).fetchone()
    return r["criada"] if r else None


def definir_ativa(id_: str, ativa: bool) -> bool:
    with closing(_conn()) as c, c:
        cur = c.execute("UPDATE tarefas SET ativa=? WHERE id=?", (int(ativa), id_))
    return cur.rowcount > 0


def remover(id_: str) -> bool:
    """Remove a tarefa. O histórico e a memória de itens já enviados ficam (segurança: recriar a
    tarefa com o mesmo id não reenvia o que já foi feito)."""
    with closing(_conn()) as c, c:
        cur = c.execute("DELETE FROM tarefas WHERE id=?", (id_,))
    return cur.rowcount > 0


# ---- execuções ---------------------------------------------------------------------------------

def iniciar_execucao(tarefa_id: str, disparo: str, agora: float, estado: str = "em_andamento",
                     motivo: str = "") -> Optional[str]:
    """Abre uma execução. Devolve None se esta rodada (tarefa + disparo) já existe."""
    eid = uuid.uuid4().hex[:12]
    try:
        with closing(_conn()) as c, c:
            c.execute("INSERT INTO execucoes(id,tarefa_id,disparo,inicio,estado,motivo,fim) VALUES(?,?,?,?,?,?,?)",
                      (eid, tarefa_id, disparo, agora, estado, motivo, agora if estado != "em_andamento" else None))
    except sqlite3.IntegrityError:
        return None
    return eid


def finalizar(eid: str, estado: str, motivo: str, passos: List[Dict[str, Any]], agora: float) -> None:
    with closing(_conn()) as c, c:
        c.execute("UPDATE execucoes SET estado=?, motivo=?, passos=?, fim=? WHERE id=?",
                  (estado, motivo[:500], json.dumps(passos, ensure_ascii=False, default=str)[:20000], agora, eid))


def _exec(r) -> Dict[str, Any]:
    d = dict(r)
    d["passos"] = json.loads(d["passos"] or "[]")
    return d


def execucoes(tarefa_id: Optional[str] = None, limite: int = 30) -> List[Dict[str, Any]]:
    with closing(_conn()) as c:
        if tarefa_id:
            rows = c.execute("SELECT * FROM execucoes WHERE tarefa_id=? ORDER BY inicio DESC, rowid DESC LIMIT ?",
                             (tarefa_id, limite)).fetchall()
        else:
            rows = c.execute("SELECT * FROM execucoes ORDER BY inicio DESC, rowid DESC LIMIT ?", (limite,)).fetchall()
    return [_exec(r) for r in rows]


def obter_execucao(eid: str) -> Optional[Dict[str, Any]]:
    with closing(_conn()) as c:
        r = c.execute("SELECT * FROM execucoes WHERE id=?", (eid,)).fetchone()
    return _exec(r) if r else None


def disparo_existe(tarefa_id: str, disparo: str) -> bool:
    with closing(_conn()) as c:
        return c.execute("SELECT 1 FROM execucoes WHERE tarefa_id=? AND disparo=?", (tarefa_id, disparo)).fetchone() is not None


def recuperar_interrompidas(agora: float) -> int:
    """Chamado ao subir: execuções que ficaram 'em_andamento' (o programa caiu) viram 'interrompida'."""
    with closing(_conn()) as c, c:
        cur = c.execute(
            "UPDATE execucoes SET estado='interrompida', fim=?, motivo='O Jarvis foi reiniciado durante a execução.' "
            "WHERE estado='em_andamento'", (agora,))
    return cur.rowcount


# ---- itens idempotentes -------------------------------------------------------------------------

def item_reservar(chave: str, tarefa_id: str, execucao_id: str, agora: float) -> str:
    """'novo' (reservado agora, pode executar), 'ok' (já foi feito: pular) ou 'incerto' (reserva
    antiga sem conclusão: pode ou não ter sido feito)."""
    try:
        with closing(_conn()) as c, c:
            c.execute("INSERT INTO itens(chave,tarefa_id,execucao_id,estado,ts) VALUES(?,?,?,'iniciado',?)",
                      (chave, tarefa_id, execucao_id, agora))
        return "novo"
    except sqlite3.IntegrityError:
        with closing(_conn()) as c:
            r = c.execute("SELECT estado FROM itens WHERE chave=?", (chave,)).fetchone()
        return "ok" if r and r["estado"] == "ok" else "incerto"


def item_concluir(chave: str) -> None:
    with closing(_conn()) as c, c:
        c.execute("UPDATE itens SET estado='ok' WHERE chave=?", (chave,))


def item_liberar(chave: str) -> bool:
    """Apaga a reserva (falha definitiva, ou você conferiu que o item NÃO foi feito)."""
    with closing(_conn()) as c, c:
        return c.execute("DELETE FROM itens WHERE chave=?", (chave,)).rowcount > 0


def itens_da_tarefa(tarefa_id: str) -> List[Dict[str, Any]]:
    with closing(_conn()) as c:
        rows = c.execute("SELECT chave,estado,ts,execucao_id FROM itens WHERE tarefa_id=? ORDER BY ts DESC LIMIT 200",
                         (tarefa_id,)).fetchall()
    return [dict(r) for r in rows]


# ---- limites por dia -----------------------------------------------------------------------------

def uso_do_dia(tarefa_id: str, ferramenta: str, dia: str) -> int:
    with closing(_conn()) as c:
        r = c.execute("SELECT n FROM usos WHERE tarefa_id=? AND ferramenta=? AND dia=?", (tarefa_id, ferramenta, dia)).fetchone()
    return r["n"] if r else 0


def uso_reservar(tarefa_id: str, ferramenta: str, dia: str, limite: int) -> bool:
    """Conta uma chamada, atomicamente, se ainda couber no limite do dia. Conta na TENTATIVA (não
    no sucesso): um laço de retry nunca ultrapassa o limite."""
    with closing(_conn()) as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            r = c.execute("SELECT n FROM usos WHERE tarefa_id=? AND ferramenta=? AND dia=?", (tarefa_id, ferramenta, dia)).fetchone()
            n = r["n"] if r else 0
            if n >= limite:
                c.execute("ROLLBACK")
                return False
            c.execute("INSERT INTO usos(tarefa_id,ferramenta,dia,n) VALUES(?,?,?,1) "
                      "ON CONFLICT(tarefa_id,ferramenta,dia) DO UPDATE SET n=n+1", (tarefa_id, ferramenta, dia))
            c.execute("COMMIT")
            return True
        except Exception:
            c.execute("ROLLBACK")
            raise


# ---- pausa do agendador (sobrevive a reinício) ----------------------------------------------------

_PAUSA = "agendador.pausado"


def agendador_pausado() -> bool:
    return (db.get_setting(_PAUSA) or "") == "1"


def definir_pausa(pausado: bool) -> None:
    db.set_setting(_PAUSA, "1" if pausado else "0")
