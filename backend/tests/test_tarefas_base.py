"""Fase 2 — modelo da tarefa, cron e política do contrato. Não depende de FastAPI nem do Windows."""
import copy
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from actions import gate
from connections import db
from tarefas import cron, store
from tarefas.contrato import ContratoAtivo, dentro_de, dominio_ok
from tarefas.models import SCHEMA_ATUAL, SchemaNaoSuportado, carregar, migrar

SP = ZoneInfo("America/Sao_Paulo")

# Exemplo do docs/AGENTE.md (seção 6), com ferramentas e pastas de teste.
EXEMPLO = {
    "schema": 1, "id": "videos-diarios", "nome": "Vídeos diários",
    "agenda": {"cron": "0 9 * * *", "fuso": "America/Sao_Paulo"},
    "parametros": {"quantidade": 5, "prompt_conteudo": "..."},
    "contrato": {
        "escopo": {"pastas": ["C:/projetos/projeto-x"], "contas": ["youtube:canal-teste"],
                   "ferramentas": ["vscode.abrir_projeto", "comando.rodar", "youtube.upload_privado"]},
        "limites": {"por_dia": {"youtube.upload_privado": 5}, "visibilidade": "privado", "max_chamadas_ia": 40,
                    "timeout_min": 90},
        "ao_sair_do_contrato": "pausar_e_perguntar",
    },
    "passos": [
        {"id": "abrir", "ferramenta": "vscode.abrir_projeto", "params": {"pasta": "C:/projetos/projeto-x"}},
        {"id": "gerar", "ferramenta": "comando.rodar", "params": {"nome": "gerar_videos", "quantidade": "{quantidade}"},
         "verificar": {"arquivos_em": "saida/", "minimo": "{quantidade}"}},
        {"id": "subir", "ferramenta": "youtube.upload_privado", "para_cada": "{gerar.arquivos}",
         "params": {"arquivo": "{item}"}},
    ],
    "confianca": {"execucoes_ok": 0, "promover_apos": 10},
}


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    db._migrated.clear()
    store.reset_state()
    gate.reset_state()


def exemplo(**mudar):
    d = copy.deepcopy(EXEMPLO)
    d.update(mudar)
    return d


# ---- modelo ---------------------------------------------------------------------------------------

def test_exemplo_da_documentacao_e_valido_e_volta_igual():
    t = carregar(exemplo())
    assert t.id == "videos-diarios" and t.contrato.aprovado is False       # nasce NÃO aprovado
    assert carregar(t.dump()).dump() == t.dump()


def test_campo_desconhecido_e_recusado_em_qualquer_nivel():
    d = exemplo()
    d["contrato"]["limits"] = {"timeout_min": 5}                            # erro de digitação
    with pytest.raises(ValidationError):
        carregar(d)
    d = exemplo()
    d["contrato"]["limites"]["uploads_por_dia"] = 5                         # campo que não existe
    with pytest.raises(ValidationError):
        carregar(d)
    with pytest.raises(ValidationError):
        carregar({**exemplo(), "extra": 1})


def test_schema_futuro_e_invalido_sao_recusados_e_ausente_vale_1():
    with pytest.raises(SchemaNaoSuportado, match="mais novo"):
        carregar(exemplo(schema=SCHEMA_ATUAL + 1))
    for ruim in (0, -1, "1", True, None):
        with pytest.raises(SchemaNaoSuportado):
            migrar({**exemplo(), "schema": ruim})
    d = exemplo()
    del d["schema"]
    assert carregar(d).schema_ == 1
    with pytest.raises(SchemaNaoSuportado):
        migrar([1, 2])


def test_passo_com_ferramenta_fora_do_escopo_e_recusado():
    d = exemplo()
    d["passos"].append({"id": "extra", "ferramenta": "gmail.enviar"})
    with pytest.raises(ValidationError, match="fora do escopo"):
        carregar(d)


def test_referencias_precisam_apontar_para_algo_que_existe():
    d = exemplo()
    d["passos"][1]["params"]["quantidade"] = "{nao_existe}"
    with pytest.raises(ValidationError, match="parametros"):
        carregar(d)
    d = exemplo()
    d["passos"][0]["params"]["x"] = "{subir.arquivos}"                      # passo que vem DEPOIS
    with pytest.raises(ValidationError, match="não vem antes"):
        carregar(d)
    d = exemplo()
    d["passos"][1]["params"]["x"] = "{item}"                                # {item} sem para_cada
    with pytest.raises(ValidationError):
        carregar(d)


@pytest.mark.parametrize("mexer", [
    lambda d: d["passos"].append(copy.deepcopy(d["passos"][0])),            # id duplicado
    lambda d: d["agenda"].update(cron="isto não é cron"),
    lambda d: d["agenda"].update(fuso="Marte/Olympus"),
    lambda d: d["contrato"]["limites"].update(janela_horario={"inicio": "9h", "fim": "22:00"}),
    lambda d: d["contrato"]["limites"]["por_dia"].update({"x": -1}),
    lambda d: d["contrato"]["limites"].update(timeout_min=0),
    lambda d: d["contrato"]["escopo"].update(ferramentas=[]),               # contrato sem ferramentas permitidas
    lambda d: d.update(id="Tem Espaço"),
    lambda d: d["passos"][1].update(verificar={}),                          # verificar vazio
    lambda d: d.update(passos=[]),
])
def test_tarefas_invalidas_sao_recusadas(mexer):
    d = exemplo()
    mexer(d)
    with pytest.raises(ValidationError):
        carregar(d)


# ---- cron ----------------------------------------------------------------------------------------------

def dt(*a, tz=SP):
    return datetime(*a, tzinfo=tz)


def test_proxima_e_anterior():
    agora = dt(2026, 10, 31, 11, 11)
    assert cron.proxima("0 9 * * *", agora, SP) == dt(2026, 11, 1, 9, 0)
    assert cron.anterior("0 9 * * *", agora, SP) == dt(2026, 10, 31, 9, 0)
    assert cron.anterior("0 9 * * *", dt(2026, 10, 31, 9, 0), SP) == dt(2026, 10, 31, 9, 0)   # inclusive
    assert cron.proxima("0 9 * * *", dt(2026, 10, 31, 9, 0), SP) == dt(2026, 11, 1, 9, 0)     # estrito


def test_passos_listas_intervalos_e_dia_da_semana():
    assert cron.proxima("*/15 * * * *", dt(2026, 10, 31, 11, 11), SP) == dt(2026, 10, 31, 11, 15)
    assert cron.proxima("0 9,18 * * *", dt(2026, 10, 31, 11, 0), SP) == dt(2026, 10, 31, 18, 0)
    assert cron.proxima("0 9 * * 1-5", dt(2026, 10, 31, 11, 0), SP) == dt(2026, 11, 2, 9, 0)    # sábado -> segunda
    assert cron.proxima("0 9 * * 0", dt(2026, 10, 31, 11, 0), SP) == dt(2026, 11, 1, 9, 0)      # domingo
    assert cron.proxima("0 9 * * 7", dt(2026, 10, 31, 11, 0), SP) == dt(2026, 11, 1, 9, 0)      # 7 também é domingo
    assert cron.proxima("0 9 1 * *", dt(2026, 10, 31, 11, 0), SP) == dt(2026, 11, 1, 9, 0)
    assert cron.anterior("0 9 29 2 *", dt(2026, 10, 31, 11, 0), SP) == dt(2024, 2, 29, 9, 0)


def test_dia_do_mes_e_dia_da_semana_juntos_valem_um_ou_outro():
    # dia 1 OU segunda-feira
    assert cron.proxima("0 9 1 * 1", dt(2026, 10, 31, 11, 0), SP) == dt(2026, 11, 1, 9, 0)
    assert cron.proxima("0 9 1 * 1", dt(2026, 11, 1, 12, 0), SP) == dt(2026, 11, 2, 9, 0)


def test_horario_que_nao_existe_no_horario_de_verao_e_pulado():
    ny = ZoneInfo("America/New_York")
    assert cron.proxima("30 2 * * *", dt(2026, 3, 7, 12, tz=ny), ny) == dt(2026, 3, 9, 2, 30, tz=ny)


def test_chave_do_slot_e_estavel():
    assert cron.chave_slot(dt(2026, 10, 31, 9, 0)) == "2026-10-31T09:00-0300"


@pytest.mark.parametrize("ruim", ["", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *", "* * 0 * *", "* * * 13 *",
                                  "* * * * 8", "a * * * *", "*/0 * * * *", "5-1 * * * *", "1,,2 * * * *", "*/x * * * *"])
def test_cron_invalido(ruim):
    with pytest.raises(ValueError):
        cron.parse(ruim)


# ---- política do contrato -----------------------------------------------------------------------------------

class Relogio:
    def __init__(self, quando=None):
        self.t = (quando or dt(2026, 10, 31, 10, 0)).timestamp()

    def __call__(self):
        return self.t


def contrato(tmp_path, **limites):
    pasta = tmp_path / "proj"
    pasta.mkdir(exist_ok=True)
    d = exemplo()
    d["contrato"] = {"escopo": {"ferramentas": ["a", "b"], "pastas": [str(pasta)], "dominios": ["exemplo.com"],
                                "contas": ["youtube:teste"]},
                     "limites": limites, "aprovado": True}
    d["passos"] = [{"id": "p", "ferramenta": "a"}]
    return carregar(d), pasta


def test_ferramenta_fora_do_escopo(tmp_path):
    t, _ = contrato(tmp_path)
    c = ContratoAtivo(t, relogio=Relogio())
    assert c.checar("a", {}, 1) is None
    assert "não está entre as ferramentas" in c.checar("gmail.enviar", {}, 3)


def test_pastas_so_dentro_do_escopo_inclusive_contra_traversal(tmp_path):
    t, pasta = contrato(tmp_path)
    c = ContratoAtivo(t, relogio=Relogio())
    assert c.checar("a", {"pasta": str(pasta)}, 1) is None
    assert c.checar("a", {"arquivo": str(pasta / "saida" / "v.mp4")}, 1) is None
    assert c.checar("a", {"arquivo": "saida/v.mp4"}, 1) is None                       # relativo à 1ª pasta
    for ruim in (str(tmp_path), str(tmp_path / "outra"), str(pasta / ".." / "outra"), "../fora.mp4",
                 str(pasta) + "-irma", "/etc/passwd"):
        assert "fora das pastas" in c.checar("a", {"pasta": ruim}, 1), ruim
    assert "fora das pastas" in c.checar("a", {"arquivos": [str(pasta / "ok.mp4"), "/etc/passwd"]}, 1)


def test_symlink_para_fora_nao_escapa(tmp_path):
    t, pasta = contrato(tmp_path)
    fora = tmp_path / "fora"
    fora.mkdir()
    (pasta / "atalho").symlink_to(fora)
    c = ContratoAtivo(t, relogio=Relogio())
    assert "fora das pastas" in c.checar("a", {"pasta": str(pasta / "atalho")}, 1)


def test_dominios_contas_e_visibilidade(tmp_path):
    t, _ = contrato(tmp_path, visibilidade="privado")
    c = ContratoAtivo(t, relogio=Relogio())
    assert c.checar("a", {"url": "https://exemplo.com/x", "conta": "youtube:teste", "visibilidade": "privado"}, 2) is None
    assert c.checar("a", {"url": "https://api.exemplo.com/x"}, 1) is None             # subdomínio
    assert "domínio" in c.checar("a", {"url": "https://exemplo.com.malicioso.io/x"}, 1)
    assert "domínio" in c.checar("a", {"url": "https://malicioso.io/?r=exemplo.com"}, 1)
    assert "conta" in c.checar("a", {"conta": "youtube:principal"}, 2)
    assert "visibilidade" in c.checar("a", {"visibilidade": "publico"}, 2)


def test_dominio_ok_e_dentro_de_direto():
    assert dominio_ok("exemplo.com", ["exemplo.com"]) and not dominio_ok("", ["exemplo.com"])
    assert not dentro_de("x", [])


def test_janela_de_horario_inclusive_a_que_atravessa_a_meia_noite(tmp_path):
    t, _ = contrato(tmp_path, janela_horario={"inicio": "08:00", "fim": "22:00"})
    assert ContratoAtivo(t, relogio=Relogio(dt(2026, 10, 31, 10, 0))).checar("a", {}, 1) is None
    assert "janela" in ContratoAtivo(t, relogio=Relogio(dt(2026, 10, 31, 23, 0))).checar("a", {}, 1)
    t, _ = contrato(tmp_path, janela_horario={"inicio": "22:00", "fim": "06:00"})
    assert ContratoAtivo(t, relogio=Relogio(dt(2026, 10, 31, 23, 0))).checar("a", {}, 1) is None
    assert ContratoAtivo(t, relogio=Relogio(dt(2026, 10, 31, 3, 0))).checar("a", {}, 1) is None
    assert "janela" in ContratoAtivo(t, relogio=Relogio(dt(2026, 10, 31, 12, 0))).checar("a", {}, 1)


def test_timeout_total_e_max_passos(tmp_path):
    t, _ = contrato(tmp_path, timeout_min=10, max_passos=2)
    r = Relogio()
    c = ContratoAtivo(t, relogio=r)
    assert c.checar("a", {}, 1) is None and c.checar("a", {}, 1) is None
    assert "limite de 2 chamadas" in c.checar("a", {}, 1)
    c = ContratoAtivo(t, relogio=r)
    r.t += 11 * 60
    assert "tempo total" in c.checar("a", {}, 1)


def test_limite_por_dia_conta_entre_execucoes_e_a_simulacao_nao_conta(tmp_path):
    t, _ = contrato(tmp_path, por_dia={"a": 2})
    r = Relogio()
    for _ in range(5):                                                   # simular não gasta cota
        assert ContratoAtivo(t, relogio=r).checar("a", {}, 1, simulacao=True) is None
    assert ContratoAtivo(t, relogio=r).checar("a", {}, 1) is None        # execuções diferentes, mesmo dia
    assert ContratoAtivo(t, relogio=r).checar("a", {}, 1) is None
    assert "limite diário" in ContratoAtivo(t, relogio=r).checar("a", {}, 1)
    assert "limite diário" in ContratoAtivo(t, relogio=r).checar("a", {}, 1, simulacao=True)
    r.t += 24 * 3600                                                     # no dia seguinte volta
    assert ContratoAtivo(t, relogio=r).checar("a", {}, 1) is None


def test_limite_por_dia_zero_bloqueia_tudo(tmp_path):
    t, _ = contrato(tmp_path, por_dia={"a": 0})
    assert "limite diário" in ContratoAtivo(t, relogio=Relogio()).checar("a", {}, 1)


def test_contrato_nao_aprovado_marca_aprovado_falso(tmp_path):
    d = exemplo()
    assert ContratoAtivo(carregar(d), relogio=Relogio()).aprovado is False
