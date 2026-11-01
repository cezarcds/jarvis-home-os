"""Fase 1 — gate: política por nível, confirmação, parada, contaminação e auditoria.
Casos NEGADOS primeiro (regra 10 do CLAUDE.md). Usa ferramentas falsas no catálogo; não depende
de FastAPI nem do Windows."""
import ast
import asyncio
import sqlite3
from pathlib import Path

import pytest

from actions import gate, hotkey
from actions.redact import REDIGIDO, redigir
from connections import db
from routines.tools import registry
from routines.tools.registry import REGISTRY, Param, Tool, nivel_de

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    db._migrated.clear()
    gate.reset_state()
    yield
    gate.reset_state()


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def relogio(monkeypatch):
    r = Relogio()
    monkeypatch.setattr(gate, "_clock", r)
    return r


@pytest.fixture
def ferramentas(monkeypatch):
    """Uma ferramenta falsa por nível, contando quantas vezes a função REAL foi chamada."""
    chamadas = {}

    def criar(nome, risco, **kw):
        chamadas[nome] = []

        async def fn(**p):
            chamadas[nome].append(p)
            return {"type": "acao", "title": nome, "data": {}, "falado": f"{nome} feito", "resumo_llm": ""}

        monkeypatch.setitem(REGISTRY, nome, Tool(nome, nome, "falsa", [Param("alvo", "str", "x")], fn, risco, **kw))

    criar("t.leitura", "leitura")
    criar("t.local", "acao_local")
    criar("t.reversivel", "externo_reversivel")
    criar("t.irreversivel", "externo_irreversivel",
          confirmacao=lambda p: f"ENVIAR email para {p['alvo']}")
    criar("t.estranha", "risco_inventado")  # chega por atribuição direta, sem passar pelo decorator
    criar("t.externa", "leitura", le_dado_externo=True)
    return chamadas


def rodar(coro):
    return asyncio.run(coro)


def registros(**filtro):
    return [r for r in db.recent_actions(100) if all(r[k] == v for k, v in filtro.items())]


# ---- registro: níveis --------------------------------------------------------------------

def test_niveis_e_risco_desconhecido_falha_fechada():
    assert [nivel_de(r) for r in ("leitura", "acao_local", "externo_reversivel", "externo_irreversivel")] == [0, 1, 2, 3]
    assert nivel_de("qualquer-coisa") == 3 and nivel_de(None) == 3


def test_decorator_recusa_risco_inventado():
    with pytest.raises(ValueError):
        registry.tool("x.y", "x", "x", risco="mais_ou_menos")


# ---- casos negados -------------------------------------------------------------------------

@pytest.mark.parametrize("nome", ["t.reversivel", "t.irreversivel", "t.estranha"])
def test_nivel_2_e_3_sem_confirmacao_nunca_executam(ferramentas, nome):
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar(nome, {"alvo": "a"}, gate.Contexto(sid="s")))
    assert ferramentas[nome] == []                       # a função real NÃO rodou
    assert exc.value.pendente["ferramenta"] == nome
    assert [r["resultado"] for r in registros(tool=nome)] == ["pendente"]


def test_risco_desconhecido_vale_nivel_3(ferramentas):
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar("t.estranha", {}, gate.Contexto()))
    assert exc.value.pendente["nivel"] == 3 and exc.value.pendente["forte"] is True


def test_ferramenta_desconhecida_e_negada_e_auditada(ferramentas):
    with pytest.raises(gate.AcaoNegada):
        rodar(gate.executar("nao.existe", {}, gate.Contexto()))
    assert registros(tool="nao.existe")[0]["resultado"] == "negado"


def test_confirmar_por_voz_nao_vale(ferramentas):
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar("t.irreversivel", {"alvo": "a"}, gate.Contexto()))
    pid = exc.value.pendente["id"]
    for via in ("voz", "sim", "", "api"):
        with pytest.raises(gate.ConfirmacaoInvalida):
            rodar(gate.confirmar(pid, via))
    assert ferramentas["t.irreversivel"] == []
    assert len(gate.listar_pendentes()) == 1             # continua esperando o clique


def test_id_errado_e_rejeitado(ferramentas):
    with pytest.raises(gate.ConfirmacaoPendente):
        rodar(gate.executar("t.reversivel", {}, gate.Contexto()))
    for pid in ("", "sim", "00000000", "../x"):
        with pytest.raises(gate.ConfirmacaoInvalida):
            rodar(gate.confirmar(pid, "clique"))
    assert ferramentas["t.reversivel"] == []


def test_confirmacao_expirada_e_rejeitada_e_auditada(ferramentas, relogio):
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar("t.reversivel", {}, gate.Contexto()))
    relogio.t += gate.PENDENTE_TTL_S + 1
    with pytest.raises(gate.ConfirmacaoInvalida):
        rodar(gate.confirmar(exc.value.pendente["id"], "clique"))
    assert ferramentas["t.reversivel"] == []
    assert "expirado" in [r["resultado"] for r in registros(tool="t.reversivel")]


def test_confirmacao_vale_uma_vez_so(ferramentas):
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar("t.reversivel", {"alvo": "a"}, gate.Contexto()))
    pid = exc.value.pendente["id"]
    rodar(gate.confirmar(pid, "clique"))
    with pytest.raises(gate.ConfirmacaoInvalida):
        rodar(gate.confirmar(pid, "clique"))
    assert len(ferramentas["t.reversivel"]) == 1


def test_negar_nao_executa(ferramentas):
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar("t.irreversivel", {"alvo": "a"}, gate.Contexto()))
    gate.negar(exc.value.pendente["id"])
    assert ferramentas["t.irreversivel"] == [] and gate.listar_pendentes() == []
    assert "negado" in [r["resultado"] for r in registros(tool="t.irreversivel")]
    with pytest.raises(gate.ConfirmacaoInvalida):
        gate.negar(exc.value.pendente["id"])


def test_rotina_so_pode_nivel_0(ferramentas):
    ctx = gate.Contexto(origem="rotina", max_nivel=0)
    assert rodar(gate.executar("t.leitura", {}, ctx))["falado"] == "t.leitura feito"
    with pytest.raises(gate.AcaoNegada, match="não habilitadas"):
        rodar(gate.executar("t.local", {}, ctx))
    assert ferramentas["t.local"] == []


def test_ferramenta_indisponivel_e_negada(ferramentas, monkeypatch):
    monkeypatch.setattr(REGISTRY["t.local"], "check", lambda: (False, "Disponível só no Windows"))
    with pytest.raises(gate.AcaoNegada, match="Windows"):
        rodar(gate.executar("t.local", {}, gate.Contexto()))
    assert ferramentas["t.local"] == []


def test_pendente_expor_ao_hud_nao_inclui_parametros_crus(ferramentas):
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar("t.irreversivel", {"alvo": "ana@example.com"}, gate.Contexto()))
    pub = exc.value.pendente
    assert "params" not in pub and pub["texto"] == "ENVIAR email para ana@example.com"
    assert pub["forte"] is True


def test_texto_exato_e_o_que_executa(ferramentas):
    """Os parâmetros ficam no servidor: o clique executa exatamente o que foi mostrado."""
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar("t.irreversivel", {"alvo": "ana@example.com"}, gate.Contexto()))
    rodar(gate.confirmar(exc.value.pendente["id"], "clique"))
    assert ferramentas["t.irreversivel"] == [{"alvo": "ana@example.com"}]


def test_limite_de_pendentes(ferramentas):
    for _ in range(gate.MAX_PENDENTES):
        with pytest.raises(gate.ConfirmacaoPendente):
            rodar(gate.executar("t.reversivel", {}, gate.Contexto()))
    with pytest.raises(gate.AcaoNegada):
        rodar(gate.executar("t.reversivel", {}, gate.Contexto()))


# ---- caminho feliz ----------------------------------------------------------------------------

@pytest.mark.parametrize("nome", ["t.leitura", "t.local"])
def test_nivel_0_e_1_executam_e_registram(ferramentas, nome):
    r = rodar(gate.executar(nome, {"alvo": "a"}, gate.Contexto(sid="s1", origem="assistente")))
    assert r["falado"] == f"{nome} feito" and len(ferramentas[nome]) == 1
    regs = registros(tool=nome)
    assert [x["resultado"] for x in reversed(regs)] == ["iniciada", "ok"] if len(regs) == 2 else ["ok"]
    ok = [x for x in regs if x["resultado"] == "ok"][0]
    assert ok["origem"] == "assistente" and ok["sessao"] == "s1" and ok["duracao_ms"] is not None


def test_confirmado_executa_e_registra_a_via(ferramentas):
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar("t.reversivel", {"alvo": "a"}, gate.Contexto()))
    rodar(gate.confirmar(exc.value.pendente["id"], "clique"))
    ok = [x for x in registros(tool="t.reversivel") if x["resultado"] == "ok"][0]
    assert ok["confirmacao"] == "clique" and ok["nivel"] == 2


def test_sessao_atual_chega_a_funcao_da_ferramenta(monkeypatch):
    visto = []

    async def fn(**p):
        visto.append(gate.sessao_atual())
        return {}

    monkeypatch.setitem(REGISTRY, "t.sessao", Tool("t.sessao", "s", "s", [], fn, "acao_local"))
    rodar(gate.executar("t.sessao", {}, gate.Contexto(sid="abc")))
    assert visto == ["abc"] and gate.sessao_atual() == ""


def test_erro_da_ferramenta_e_registrado_e_repassado(monkeypatch):
    async def fn(**p):
        raise registry.ToolError("deu ruim")

    monkeypatch.setitem(REGISTRY, "t.erro", Tool("t.erro", "e", "e", [], fn, "acao_local"))
    with pytest.raises(registry.ToolError):
        rodar(gate.executar("t.erro", {}, gate.Contexto()))
    assert registros(tool="t.erro", resultado="erro")


# ---- parada ---------------------------------------------------------------------------------------

def test_parar_antes_do_proximo_passo(ferramentas):
    ctx = gate.Contexto(origem="rotina")                 # nasce na geração atual
    rodar(gate.executar("t.local", {}, ctx))
    gate.parar("teste")
    with pytest.raises(gate.ExecucaoCancelada):
        rodar(gate.executar("t.local", {}, ctx))        # o passo seguinte da MESMA execução
    assert len(ferramentas["t.local"]) == 1
    assert "cancelado" in [x["resultado"] for x in registros(tool="t.local")]


def test_parar_interrompe_execucao_em_andamento(monkeypatch):
    estado = {"terminou": False}

    async def lenta(**p):
        await asyncio.sleep(5)
        estado["terminou"] = True
        return {}

    monkeypatch.setitem(REGISTRY, "t.lenta", Tool("t.lenta", "l", "l", [], lenta, "acao_local", timeout=30))

    async def cenario():
        tarefa = asyncio.ensure_future(gate.executar("t.lenta", {}, gate.Contexto()))
        await asyncio.sleep(0.05)
        gate.parar("teste")
        with pytest.raises(gate.ExecucaoCancelada):
            await tarefa

    rodar(cenario())
    assert estado["terminou"] is False
    assert registros(tool="t.lenta", resultado="cancelado")


def test_parar_descarta_pendentes_e_chama_ganchos(ferramentas):
    chamou = []
    gate.registrar_gancho_parada(lambda: chamou.append(1))
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar("t.irreversivel", {"alvo": "a"}, gate.Contexto()))
    r = gate.parar("teste")
    assert r["pendentes_descartadas"] == 1 and chamou == [1] and gate.listar_pendentes() == []
    with pytest.raises(gate.ConfirmacaoInvalida):
        rodar(gate.confirmar(exc.value.pendente["id"], "clique"))
    assert ferramentas["t.irreversivel"] == []


def test_contexto_novo_depois_da_parada_funciona(ferramentas):
    gate.parar("teste")
    rodar(gate.executar("t.local", {}, gate.Contexto()))
    assert len(ferramentas["t.local"]) == 1


def test_parada_confirmando_pendente_antiga_e_cancelada(ferramentas):
    """Confirmar uma ação criada ANTES da parada não a executa (as pendentes já foram descartadas)."""
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar("t.reversivel", {}, gate.Contexto()))
    gate.parar("teste")
    with pytest.raises(gate.ConfirmacaoInvalida):
        rodar(gate.confirmar(exc.value.pendente["id"], "clique"))


@pytest.mark.parametrize("frase", ["para tudo", "Jarvis, para tudo!", "pare tudo agora", "cancela tudo", "PARA TUDO."])
def test_comando_de_voz_para_tudo(frase):
    assert gate.eh_comando_parar(frase)


@pytest.mark.parametrize("frase", ["para", "para de olhar a tela", "abre o profit", "para tudo mundo ver", "", "cancela a reunião"])
def test_frases_que_nao_sao_parada(frase):
    assert not gate.eh_comando_parar(frase)


# ---- contaminação -------------------------------------------------------------------------------------

@pytest.mark.parametrize("nivel,contaminado,contrato,esperado", [
    (0, True, True, False), (1, True, True, False),
    (2, False, False, True),   # Fase 1: sem contrato, nível 2 sempre confirma
    (2, False, True, False),   # Fase 2: dentro do contrato, sem contaminação, roda
    (2, True, True, True),     # contaminado: confirma MESMO dentro do contrato
    (3, False, True, True), (3, True, True, True),
])
def test_politica_de_confirmacao(nivel, contaminado, contrato, esperado):
    assert gate.exige_confirmacao(nivel, contaminado, contrato) is esperado


def test_ler_dado_externo_contamina_a_sessao(ferramentas):
    assert not gate.sessao_contaminada("s1")
    ctx = gate.Contexto(sid="s1")
    rodar(gate.executar("t.externa", {}, ctx))
    assert gate.sessao_contaminada("s1") and ctx.contaminado is True
    assert not gate.sessao_contaminada("outra")          # outra sessão não é afetada


def test_contaminacao_vai_para_a_pendente_e_para_a_auditoria(ferramentas):
    rodar(gate.executar("t.externa", {}, gate.Contexto(sid="s1")))
    with pytest.raises(gate.ConfirmacaoPendente):
        rodar(gate.executar("t.reversivel", {}, gate.Contexto(sid="s1")))
    assert registros(tool="t.reversivel", resultado="pendente")[0]["contaminado"] == 1


def test_contaminacao_expira(ferramentas, relogio):
    gate.marcar_contaminado("s1")
    relogio.t += gate.CONTAMINACAO_TTL_S + 1
    assert not gate.sessao_contaminada("s1")


# ---- auditoria e redação -------------------------------------------------------------------------------

def test_redacao_por_nome_e_por_formato():
    r = redigir({"token": "abc", "Senha": "123", "api_key": "k", "authorization": "Bearer xyz12345678",
                 "nota": "ok", "texto": "usa Bearer abcdefgh12345 aqui", "chave_longa": "x",
                 "id": "A" * 40, "n": 3, "lista": [{"secret": "s"}]})
    assert r["token"] == r["Senha"] == r["api_key"] == r["authorization"] == r["chave_longa"] == REDIGIDO
    assert r["nota"] == "ok" and r["n"] == 3
    assert "abcdefgh12345" not in r["texto"] and r["id"] == REDIGIDO
    assert r["lista"] == [{"secret": REDIGIDO}]


def test_redacao_corta_texto_e_profundidade():
    longo = redigir("a b " * 200)
    assert len(longo) < 260 and "…" in longo
    fundo = {"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}
    assert "[…]" in str(redigir(fundo))


def test_segredo_nunca_chega_ao_banco(ferramentas):
    rodar(gate.executar("t.local", {"alvo": "Bearer abcdefghijkl1234"}, gate.Contexto()))
    bruto = sqlite3.connect(db.data_dir() / db.DB_FILE).execute("SELECT params FROM audit_log WHERE tool='t.local'").fetchall()
    assert bruto and all("abcdefghijkl1234" not in (p[0] or "") for p in bruto)


def test_falha_na_auditoria_bloqueia_nivel_2_mas_nao_nivel_1(ferramentas, monkeypatch):
    def quebrado(**kw):
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(db, "audit_action", quebrado)
    with pytest.raises(gate.AcaoNegada, match="auditoria"):
        rodar(gate.executar("t.reversivel", {}, gate.Contexto()))
    assert ferramentas["t.reversivel"] == [] and gate.listar_pendentes() == []
    # nível 1 não depende do banco: um problema de disco não impede "abre o Profit"
    assert rodar(gate.executar("t.local", {}, gate.Contexto()))["falado"] == "t.local feito"


def test_auditoria_quebra_entre_o_pedido_e_o_clique_nao_executa(ferramentas, monkeypatch):
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        rodar(gate.executar("t.reversivel", {}, gate.Contexto()))

    def quebrado(**kw):
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(db, "audit_action", quebrado)
    with pytest.raises(gate.AcaoNegada, match="auditoria"):
        rodar(gate.confirmar(exc.value.pendente["id"], "clique"))
    assert ferramentas["t.reversivel"] == []


def test_migracao_acrescenta_colunas_em_banco_antigo(tmp_path):
    pasta = db.data_dir()
    antigo = sqlite3.connect(pasta / db.DB_FILE)
    antigo.executescript(
        "CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, event TEXT NOT NULL, "
        "detail TEXT NOT NULL DEFAULT '');"
        "INSERT INTO audit_log(ts,event,detail) VALUES (1,'oauth.connected','google');")
    antigo.commit(); antigo.close()
    db._migrated.clear()
    assert db.recent_audit(5)[0]["event"] == "oauth.connected"           # linha antiga continua legível
    colunas = {r[1] for r in sqlite3.connect(pasta / db.DB_FILE).execute("PRAGMA table_info(audit_log)")}
    assert set(db.AUDIT_ACTION_COLUMNS) <= colunas
    db.audit_action(run_id="r", tool="t", nivel=1, resultado="ok")
    assert db.recent_actions(5)[0]["tool"] == "t" and db.recent_audit(5)[0]["event"] == "acao.ok"


def test_migracao_e_idempotente():
    db.audit("a"); db._migrated.clear(); db.audit("b")
    assert [r["event"] for r in db.recent_audit(5)] == ["b", "a"]


# ---- nenhuma ferramenta executa fora do gate (aceite da Fase 1) ---------------------------------------

def _py_do_projeto():
    for p in BACKEND.rglob("*.py"):
        partes = set(p.relative_to(BACKEND).parts)
        if partes & {".venv", "venv", "tests", "__pycache__", "node_modules"}:
            continue
        yield p


def test_so_o_gate_chama_a_funcao_da_ferramenta():
    """Varre o código: qualquer `algo.fn(...)` fora de actions/gate.py reprova. Também proíbe
    desembrulhar a função (`getattr(x, "fn")`) para chamá-la por outro caminho."""
    intruso = []
    for p in _py_do_projeto():
        if p == BACKEND / "actions" / "gate.py":
            continue
        arvore = ast.parse(p.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "fn":
                intruso.append(f"{p.relative_to(BACKEND)}:{no.lineno} chama .fn(...)")
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "getattr" \
                    and len(no.args) >= 2 and isinstance(no.args[1], ast.Constant) and no.args[1].value == "fn":
                intruso.append(f"{p.relative_to(BACKEND)}:{no.lineno} getattr(..., 'fn')")
    assert not intruso, "\n".join(intruso)


def test_ninguem_fora_do_gate_chama_a_implementacao_das_acoes():
    """handler._executar_acao é a implementação por trás da ferramenta; só actions/tools.py pode chamá-la."""
    intruso = []
    for p in _py_do_projeto():
        if p in (BACKEND / "actions" / "tools.py", BACKEND / "actions" / "handler.py"):
            continue
        for no in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Attribute) and no.attr in ("_executar_acao", "_do_open", "_do_layout"):
                intruso.append(f"{p.relative_to(BACKEND)}:{no.lineno} usa {no.attr}")
    assert not intruso, "\n".join(intruso)


def test_handler_so_chama_as_implementacoes_dentro_de_funcoes_conhecidas():
    """No próprio handler, _do_open/_do_layout só podem ser chamadas por _executar_acao."""
    fonte = ast.parse((BACKEND / "actions" / "handler.py").read_text(encoding="utf-8"))
    for func in ast.walk(fonte):
        if isinstance(func, (ast.AsyncFunctionDef, ast.FunctionDef)) and func.name != "_executar_acao":
            for no in ast.walk(func):
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id in ("_do_open", "_do_layout"):
                    pytest.fail(f"handler.{func.name} chama {no.func.id} sem passar pelo gate")


# ---- atalho global ----------------------------------------------------------------------------------------

def test_atalho_parse():
    assert hotkey.parse("ctrl+alt+j") == (0x0002 | 0x0001, ord("J"))
    assert hotkey.parse("Ctrl+Shift+F9") == (0x0002 | 0x0004, 0x70 + 8)


@pytest.mark.parametrize("ruim", ["j", "ctrl", "ctrl+", "meta+j", "ctrl+alt+enter", "ctrl+f99"])
def test_atalho_invalido(ruim):
    with pytest.raises(ValueError):
        hotkey.parse(ruim)


def test_atalho_nao_liga_fora_do_windows(monkeypatch):
    monkeypatch.setattr(hotkey.sys, "platform", "linux")
    assert hotkey.start() is False
