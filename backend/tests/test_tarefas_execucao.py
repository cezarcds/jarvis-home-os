"""Fase 2 — executor e agendador. Casos NEGADOS e de falha primeiro. Ferramentas falsas no catálogo."""
import asyncio
import copy
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from actions import gate
from connections import db
from routines.tools import registry
from routines.tools.registry import REGISTRY, Param, Tool, ToolError
from tarefas import agendador, executor, store
from tarefas.models import carregar

SP = ZoneInfo("America/Sao_Paulo")


def dt(*a):
    return datetime(*a, tzinfo=SP)


class Relogio:
    def __init__(self, quando=None):
        self.t = (quando or dt(2026, 10, 31, 9, 0, 30)).timestamp()

    def __call__(self):
        return self.t


async def sem_espera(_s):
    return None


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    db._migrated.clear()
    store.reset_state()
    gate.reset_state()
    executor._rodando.clear()


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    """Pasta do projeto e ferramentas falsas: gerar (nível 1), subir (nível 2), enviar (nível 3), ler (nível 0, externa)."""
    pasta = tmp_path / "proj"
    (pasta / "saida").mkdir(parents=True)
    w = types_ns = type("W", (), {})()
    w.pasta, w.chamadas, w.falhas, w.gerar_cria, w.ao_gerar = pasta, {}, {}, True, None

    def registrar(nome, risco, params, fn, **kw):
        w.chamadas[nome] = []
        monkeypatch.setitem(REGISTRY, nome, Tool(nome, nome, "falsa", params, fn, risco, **kw))

    def usar(nome):
        w.chamadas[nome].append(1)
        falha = w.falhas.get(nome)
        if falha:
            exc = falha.pop(0) if isinstance(falha, list) and falha else None
            if exc:
                raise exc

    async def gerar(quantidade=1, pasta=""):
        usar("t.gerar")
        arquivos = []
        for i in range(int(quantidade)):
            p = w.pasta / "saida" / f"video_{i + 1}.mp4"
            if w.gerar_cria:
                p.write_bytes(os.urandom(8))
            arquivos.append(str(p))
        if w.ao_gerar:
            w.ao_gerar()
        return {"type": "x", "title": "g", "data": {"arquivos": arquivos}, "falado": "", "resumo_llm": ""}

    async def subir(arquivo="", visibilidade=None, conta=None):
        usar("t.subir")
        w.chamadas.setdefault("subidos", []).append(arquivo)
        return {"type": "x", "title": "s", "data": {"id": f"yt-{len(w.chamadas['subidos'])}"}, "falado": "", "resumo_llm": ""}

    async def enviar(para=""):
        usar("t.enviar")
        return {"type": "x", "title": "e", "data": {}, "falado": "", "resumo_llm": ""}

    async def ler():
        usar("t.ler")
        return {"type": "x", "title": "l", "data": {"itens": ["a"]}, "falado": "", "resumo_llm": ""}

    registrar("t.gerar", "acao_local", [Param("quantidade", "int", 1), Param("pasta", "str", "")], gerar, timeout=5)
    registrar("t.subir", "externo_reversivel",
              [Param("arquivo", "str", ""), Param("visibilidade", "str", None), Param("conta", "str", None)], subir, timeout=5)
    registrar("t.enviar", "externo_irreversivel", [Param("para", "str", "")], enviar)
    registrar("t.ler", "leitura", [], ler, le_dado_externo=True)

    def tarefa(**mudar):
        d = {
            "schema": 1, "id": "videos", "nome": "Vídeos",
            "parametros": {"quantidade": 2},
            "contrato": {"escopo": {"ferramentas": ["t.gerar", "t.subir", "t.enviar", "t.ler"], "pastas": [str(pasta)],
                                    "contas": ["yt:teste"]},
                         "limites": {"por_dia": {"t.subir": 5}, "visibilidade": "privado", "espera_s": 0, "tentativas": 2},
                         "aprovado": True},
            "passos": [
                {"id": "gerar", "ferramenta": "t.gerar", "params": {"quantidade": "{quantidade}", "pasta": str(pasta)},
                 "verificar": {"arquivos_em": "saida", "minimo": "{quantidade}"}},
                {"id": "subir", "ferramenta": "t.subir", "para_cada": "{gerar.arquivos}",
                 "params": {"arquivo": "{item}", "visibilidade": "privado"}},
            ],
        }
        for k, v in mudar.items():
            d[k] = v
        return carregar(d)

    w.tarefa = tarefa
    return w


def rodar(t, **kw):
    kw.setdefault("relogio", Relogio())
    kw.setdefault("dormir", sem_espera)
    return asyncio.run(executor.executar_tarefa(t, **kw))


def linha(execucao_id):
    return store.obter_execucao(execucao_id)


# ---- falha e parada na primeira falha ---------------------------------------------------------------

def test_passo_que_falha_interrompe_e_nada_depois_roda(mundo):
    mundo.falhas["t.gerar"] = [ToolError("projeto quebrou")] * 5
    t = mundo.tarefa()
    t.contrato.limites.tentativas = 1
    r = rodar(t)
    assert r.estado == "falhou" and "projeto quebrou" in r.motivo
    assert mundo.chamadas["t.subir"] == []                       # o passo seguinte NUNCA rodou
    assert [p["estado"] for p in r.passos] == ["falhou"]


def test_retry_com_espera_so_para_falha_definitiva(mundo):
    mundo.falhas["t.gerar"] = [ToolError("tente de novo")]
    esperas = []

    async def dormir(s):
        esperas.append(s)

    t = mundo.tarefa()
    t.contrato.limites.espera_s = 3
    r = rodar(t, dormir=dormir)
    assert r.estado == "ok" and len(mundo.chamadas["t.gerar"]) == 2
    assert sum(esperas) == pytest.approx(3)


def test_retry_esgotado_falha(mundo):
    mundo.falhas["t.gerar"] = [ToolError("1"), ToolError("2"), ToolError("3")]
    r = rodar(mundo.tarefa())                                    # tentativas = 2
    assert r.estado == "falhou" and len(mundo.chamadas["t.gerar"]) == 2


def test_erro_inesperado_nao_faz_retry_e_deixa_o_item_incerto(mundo):
    t = tarefa_de_itens(mundo, arquivos(mundo, 2))
    mundo.falhas["t.subir"] = [RuntimeError("rede caiu no meio")]
    r = rodar(t)
    assert r.estado == "falhou" and len(mundo.chamadas["t.subir"]) == 1 and "incerto" in r.motivo
    # a próxima rodada NÃO repete o envio às cegas: o mesmo item ficou incerto
    r2 = rodar(t, disparo="outra")
    assert r2.estado == "pausada" and "incerto" in r2.motivo and len(mundo.chamadas["t.subir"]) == 1


def test_falha_definitiva_libera_o_item(mundo):
    mundo.falhas["t.subir"] = [ToolError("quota")] * 5
    r = rodar(mundo.tarefa())
    assert r.estado == "falhou"
    assert store.itens_da_tarefa("videos") == []                 # nada ficou reservado


def test_verificacao_falha_quando_nao_ha_arquivos_novos(mundo):
    mundo.gerar_cria = False
    r = rodar(mundo.tarefa())
    assert r.estado == "falhou" and "Verificação de «gerar»" in r.motivo
    assert mundo.chamadas["t.subir"] == []


def test_arquivo_velho_nao_prova_nada(mundo):
    mundo.gerar_cria = False
    for i in range(2):
        p = mundo.pasta / "saida" / f"video_{i + 1}.mp4"
        p.write_bytes(b"ontem")
        os.utime(p, (time.time() - 86400, time.time() - 86400))
    r = rodar(mundo.tarefa())
    assert r.estado == "falhou" and "encontrei 0" in r.motivo


def test_verificar_resultado_tem(mundo):
    t = mundo.tarefa()
    t.passos[0].verificar = None
    t.passos[1].verificar = carregar_verificar({"resultado_tem": "id"})
    assert rodar(t).estado == "ok"
    t2 = mundo.tarefa()
    t2.passos[0].verificar = carregar_verificar({"resultado_tem": "nao_existe"})
    assert rodar(t2, disparo="d2").estado == "falhou"


def carregar_verificar(d):
    from tarefas.models import Verificar
    return Verificar(**d)


def test_verificar_pasta_fora_do_escopo_falha(mundo, tmp_path):
    t = mundo.tarefa()
    t.passos[0].verificar = carregar_verificar({"arquivos_em": str(tmp_path), "minimo": 0})
    r = rodar(t)
    assert r.estado == "falhou" and "fora do escopo" in r.motivo


def test_placeholder_sem_valor_falha_sem_executar(mundo):
    t = mundo.tarefa()
    t.passos[1].para_cada = "{gerar.nao_existe}"
    r = rodar(t)
    assert r.estado == "falhou" and "não tem valor" in r.motivo and mundo.chamadas["t.subir"] == []


# ---- caminho feliz -----------------------------------------------------------------------------------------

def test_executa_na_ordem_registra_historico_e_confirma_arquivos(mundo):
    r = rodar(mundo.tarefa())
    assert r.estado == "ok" and len(mundo.chamadas["subidos"]) == 2
    assert [p["id"] for p in r.passos] == ["gerar", "subir"] and r.passos[1]["itens"] == 2
    gravada = linha(r.execucao_id)
    assert gravada["estado"] == "ok" and gravada["fim"] is not None and len(gravada["passos"]) == 2
    assert db.recent_audit(5)[0]["event"] == "tarefa.ok"
    ferramentas = [a["tool"] for a in reversed(db.recent_actions(50)) if a["resultado"] == "ok"]
    assert ferramentas == ["t.gerar", "t.subir", "t.subir"]       # tudo passou pelo gate, com origem agendador
    assert {a["origem"] for a in db.recent_actions(50)} == {"agendador"}


def test_nivel_2_dentro_do_contrato_roda_sem_confirmar(mundo):
    r = rodar(mundo.tarefa())
    assert r.estado == "ok" and gate.listar_pendentes() == []


# ---- contrato aplicado -----------------------------------------------------------------------------------------

def test_contrato_nao_aprovado_nao_executa_nada(mundo):
    t = mundo.tarefa()
    t.contrato.aprovado = False
    r = rodar(t)
    assert r.estado == "pausada" and "aprovado" in r.motivo
    assert mundo.chamadas["t.gerar"] == []


def test_visibilidade_diferente_do_contrato_pausa_sem_subir(mundo):
    t = mundo.tarefa()
    t.passos[1].params["visibilidade"] = "publico"
    r = rodar(t)
    assert r.estado == "pausada" and "visibilidade" in r.motivo
    assert mundo.chamadas["t.subir"] == [] and store.itens_da_tarefa("videos") == []


def test_ao_sair_do_contrato_cancelar(mundo):
    t = mundo.tarefa()
    t.passos[1].params["visibilidade"] = "publico"
    t.contrato.ao_sair_do_contrato = "cancelar"
    assert rodar(t).estado == "cancelada"


def test_limite_diario_estoura_no_meio_e_pausa(mundo):
    t = mundo.tarefa()
    t.contrato.limites.por_dia = {"t.subir": 1}
    r = rodar(t)
    assert r.estado == "pausada" and "limite diário" in r.motivo
    assert len(mundo.chamadas["subidos"]) == 1                    # o primeiro subiu, o segundo NÃO
    r2 = rodar(t, disparo="outra-no-mesmo-dia")
    assert r2.estado == "pausada" and len(mundo.chamadas["subidos"]) == 1


def test_conta_fora_do_contrato(mundo):
    t = mundo.tarefa()
    t.passos[1].params["conta"] = "yt:principal"
    r = rodar(t)
    assert r.estado == "pausada" and "conta" in r.motivo


def test_janela_de_horario(mundo):
    t = mundo.tarefa()
    t.contrato.limites.janela_horario = carregar_janela("08:00", "22:00")
    assert rodar(t, relogio=Relogio(dt(2026, 10, 31, 23, 30))).estado == "pausada"
    assert mundo.chamadas["t.gerar"] == []


def carregar_janela(a, b):
    from tarefas.models import JanelaHorario
    return JanelaHorario(inicio=a, fim=b)


def test_timeout_total_pausa_no_passo_seguinte(mundo):
    r_ = Relogio()
    mundo.ao_gerar = lambda: setattr(r_, "t", r_.t + 3 * 3600)      # a geração "demora" 3 h
    t = mundo.tarefa()
    t.contrato.limites.timeout_min = 60
    r = rodar(t, relogio=r_)
    assert r.estado == "pausada" and "tempo total" in r.motivo and mundo.chamadas["t.subir"] == []


def test_nivel_3_dentro_de_tarefa_pausa_e_descarta_a_confirmacao(mundo):
    t = mundo.tarefa()
    t.passos.append(type(t.passos[0])(id="enviar", ferramenta="t.enviar", params={"para": "ana@example.com"}))
    r = rodar(t)
    assert r.estado == "pausada" and "confirmação" in r.motivo and "ana@example.com" in r.motivo
    assert mundo.chamadas["t.enviar"] == []                          # NUNCA executou
    assert gate.listar_pendentes() == []                             # e a confirmação não ficou solta
    assert [a for a in db.recent_actions(50) if a["tool"] == "t.enviar" and a["resultado"] == "cancelado"]


def test_dado_externo_lido_antes_exige_confirmacao_mesmo_dentro_do_contrato(mundo):
    t = mundo.tarefa()
    P = type(t.passos[0])
    t.passos = [P(id="ler", ferramenta="t.ler")] + t.passos[:1] + [t.passos[1]]
    t.passos[1] = P(id="gerar", ferramenta="t.gerar", params={"quantidade": 2, "pasta": str(mundo.pasta)})
    t.passos[2] = P(id="subir", ferramenta="t.subir", params={"arquivo": str(mundo.pasta / "saida" / "x.mp4")})
    r = rodar(t)
    assert r.estado == "pausada" and "confirmação" in r.motivo        # contaminação vence o contrato
    assert mundo.chamadas["t.subir"] == [] and mundo.chamadas["t.ler"] == [1]


def test_contaminacao_nao_vaza_para_a_execucao_seguinte(mundo):
    t = mundo.tarefa()
    P = type(t.passos[0])
    t.passos = [P(id="ler", ferramenta="t.ler")]
    rodar(t)
    assert not gate.sessao_contaminada(f"tarefa:videos:{store.execucoes('videos')[0]['id']}")
    assert rodar(mundo.tarefa(), disparo="outra").estado == "ok"


# ---- idempotência ------------------------------------------------------------------------------------------------

def tarefa_de_itens(mundo, itens, chave=None):
    d = {"schema": 1, "id": "itens", "nome": "Itens", "parametros": {"arquivos": itens},
         "contrato": {"escopo": {"ferramentas": ["t.subir"], "pastas": [str(mundo.pasta)]},
                      "limites": {"espera_s": 0}, "aprovado": True},
         "passos": [{"id": "subir", "ferramenta": "t.subir", "para_cada": "{arquivos}",
                     "params": {"arquivo": "{item}"}, **({"chave": chave} if chave else {})}]}
    return carregar(d)


def arquivos(mundo, n=2):
    out = []
    for i in range(n):
        p = mundo.pasta / "saida" / f"a{i}.mp4"
        p.write_bytes(os.urandom(8))
        out.append(str(p))
    return out


def test_mesmo_item_nunca_sobe_duas_vezes(mundo):
    t = tarefa_de_itens(mundo, arquivos(mundo))
    assert rodar(t).estado == "ok" and len(mundo.chamadas["subidos"]) == 2
    r = rodar(t, disparo="amanha")
    assert r.estado == "ok" and len(mundo.chamadas["subidos"]) == 2    # nada repetiu
    assert r.passos[0]["pulados"] == 2 and r.passos[0]["itens"] == 0


def test_idempotencia_sobrevive_a_reinicio_do_banco(mundo):
    t = tarefa_de_itens(mundo, arquivos(mundo))
    rodar(t)
    store.reset_state(); db._migrated.clear()                        # "reiniciou": só o arquivo do banco sobrevive
    rodar(t, disparo="depois-do-reinicio")
    assert len(mundo.chamadas["subidos"]) == 2


def test_arquivo_regenerado_com_o_mesmo_nome_e_outro_item(mundo):
    fs = arquivos(mundo, 1)
    t = tarefa_de_itens(mundo, fs)
    rodar(t)
    time.sleep(0.01)
    os.utime(fs[0], None)
    open(fs[0], "ab").write(b"conteudo novo")                          # mesmo nome, outro conteúdo
    rodar(t, disparo="amanha")
    assert len(mundo.chamadas["subidos"]) == 2


def test_chave_explicita_data_item_vale_uma_vez_por_dia(mundo):
    fs = arquivos(mundo, 1)
    t = tarefa_de_itens(mundo, fs, chave="{data}:{item}")
    rodar(t)
    rodar(t, disparo="mesmo-dia")
    assert len(mundo.chamadas["subidos"]) == 1
    rodar(t, disparo="dia-seguinte", relogio=Relogio(dt(2026, 11, 1, 9, 0, 30)))
    assert len(mundo.chamadas["subidos"]) == 2


def test_execucao_interrompida_no_meio_deixa_o_item_incerto_e_pausa(mundo):
    fs = arquivos(mundo, 2)
    t = tarefa_de_itens(mundo, fs)
    # simula o programa caindo depois de reservar o 1º item e antes de concluir
    store.item_reservar(f"itens:subir:{executor.identidade(fs[0])}", "itens", "exec-antiga", time.time())
    r = rodar(t)
    assert r.estado == "pausada" and "incerto" in r.motivo and mundo.chamadas.get("subidos", []) == []
    # você conferiu que NÃO foi enviado: libera e roda
    assert store.item_liberar(f"itens:subir:{executor.identidade(fs[0])}")
    assert rodar(t, disparo="de-novo").estado == "ok" and len(mundo.chamadas["subidos"]) == 2


def test_mesma_rodada_nao_executa_duas_vezes(mundo):
    t = mundo.tarefa()
    assert rodar(t, disparo="2026-10-31T09:00-0300").estado == "ok"
    r = rodar(t, disparo="2026-10-31T09:00-0300")
    assert r.estado == "ja_executada" and len(mundo.chamadas["t.gerar"]) == 1


def test_tarefa_ja_em_execucao_nao_duplica(mundo):
    executor._rodando.add("videos")
    assert rodar(mundo.tarefa()).estado == "ja_em_execucao" and mundo.chamadas["t.gerar"] == []


# ---- parada --------------------------------------------------------------------------------------------------------

def test_parar_entre_passos_cancela_antes_do_proximo(mundo):
    mundo.ao_gerar = lambda: gate.parar("teste")
    r = rodar(mundo.tarefa())
    assert r.estado == "cancelada" and mundo.chamadas["t.subir"] == []
    assert store.itens_da_tarefa("videos") == []                      # nada começou, nada ficou incerto


def test_parar_durante_a_ferramenta_cancela_e_marca_o_item_incerto(mundo, monkeypatch):
    fs = arquivos(mundo, 2)
    t = tarefa_de_itens(mundo, fs)

    async def lenta(arquivo="", visibilidade=None, conta=None):
        await asyncio.sleep(5)
        return {}

    monkeypatch.setitem(REGISTRY, "t.subir", Tool("t.subir", "s", "s", [Param("arquivo", "str", ""),
                        Param("visibilidade", "str", None), Param("conta", "str", None)], lenta, "externo_reversivel", timeout=30))

    async def cenario():
        tarefa_ = asyncio.ensure_future(executor.executar_tarefa(t, relogio=Relogio(), dormir=sem_espera))
        await asyncio.sleep(0.1)
        gate.parar("teste")
        return await tarefa_

    r = asyncio.run(cenario())
    assert r.estado == "cancelada"
    assert len(store.itens_da_tarefa("itens")) == 1                    # 1º item já tinha começado: incerto


def test_parar_durante_a_espera_do_retry(mundo):
    mundo.falhas["t.gerar"] = [ToolError("x")] * 3
    t = mundo.tarefa()
    t.contrato.limites.espera_s = 30
    chamadas = []

    async def dormir(s):
        chamadas.append(s)
        if len(chamadas) == 2:
            gate.parar("teste")

    r = rodar(t, dormir=dormir)
    assert r.estado == "cancelada" and len(mundo.chamadas["t.gerar"]) == 1 and len(chamadas) == 2


# ---- dry-run ---------------------------------------------------------------------------------------------------------

def test_dry_run_nao_executa_nem_grava_nem_conta(mundo):
    t = mundo.tarefa()
    plano = executor.simular(t, relogio=Relogio())
    assert mundo.chamadas["t.gerar"] == [] and mundo.chamadas["t.subir"] == []
    assert store.execucoes() == [] and store.uso_do_dia("videos", "t.subir", "2026-10-31") == 0
    assert db.recent_actions(10) == []                                  # nem auditoria de ferramenta
    assert plano["rodaria_sem_pausar"] is True and [p["id"] for p in plano["passos"]] == ["gerar", "subir"]
    assert plano["passos"][1]["nivel"] == 2 and plano["passos"][1]["params"]["arquivo"] == "{item}"


def test_dry_run_mostra_o_que_seria_bloqueado(mundo):
    t = mundo.tarefa()
    t.passos[1].params["visibilidade"] = "publico"
    t.passos.append(type(t.passos[0])(id="enviar", ferramenta="t.enviar", params={"para": "a@b.c"}))
    plano = executor.simular(t, relogio=Relogio())
    assert plano["rodaria_sem_pausar"] is False
    assert plano["passos"][1]["permitido"] is False and "visibilidade" in plano["passos"][1]["motivo"]
    assert plano["passos"][2]["exige_confirmacao"] is True
    t.contrato.aprovado = False
    assert executor.simular(t, relogio=Relogio())["rodaria_sem_pausar"] is False


# ---- agendador --------------------------------------------------------------------------------------------------------

def agendada(mundo, **extra):
    t = mundo.tarefa(agenda={"cron": "0 9 * * *", "fuso": "America/Sao_Paulo", "tolerancia_min": 30}, **extra)
    return t


async def tick(ag):
    tasks = await ag.tick()
    if tasks:
        await asyncio.gather(*tasks)
    return len(tasks)


def novo(relogio):
    return agendador.Agendador(relogio=relogio, dormir=sem_espera)


def test_dispara_na_hora_e_so_uma_vez(mundo):
    r = Relogio(dt(2026, 10, 31, 9, 0, 30))
    store.salvar(agendada(mundo), agora=dt(2026, 10, 30, 12, 0).timestamp())
    ag = novo(r)
    assert asyncio.run(tick(ag)) == 1 and len(mundo.chamadas["t.gerar"]) == 1
    assert asyncio.run(tick(ag)) == 0                                    # mesmo minuto: não repete
    r.t += 60
    assert asyncio.run(tick(ag)) == 0
    assert asyncio.run(tick(novo(r))) == 0                               # "reiniciou": não repete
    assert [e["estado"] for e in store.execucoes("videos")] == ["ok"]


def test_antes_do_horario_nao_dispara(mundo):
    store.salvar(agendada(mundo), agora=dt(2026, 10, 30, 12, 0).timestamp())
    assert asyncio.run(tick(novo(Relogio(dt(2026, 10, 31, 8, 59))))) == 0   # a rodada de ontem já passou da tolerância


def test_rodada_anterior_a_criacao_da_tarefa_nao_roda(mundo):
    store.salvar(agendada(mundo), agora=dt(2026, 10, 31, 9, 10).timestamp())    # criada DEPOIS das 9h
    assert asyncio.run(tick(novo(Relogio(dt(2026, 10, 31, 9, 15))))) == 0
    assert store.execucoes("videos") == []


def test_computador_ligado_tarde_demais_registra_perdida(mundo):
    store.salvar(agendada(mundo), agora=dt(2026, 10, 30, 12, 0).timestamp())
    assert asyncio.run(tick(novo(Relogio(dt(2026, 10, 31, 22, 0))))) == 0       # atraso de 13 h
    e = store.execucoes("videos")[0]
    assert e["estado"] == "perdida" and "atraso" in e["motivo"] and mundo.chamadas["t.gerar"] == []


def test_ligado_dentro_da_tolerancia_ainda_roda(mundo):
    store.salvar(agendada(mundo), agora=dt(2026, 10, 30, 12, 0).timestamp())
    assert asyncio.run(tick(novo(Relogio(dt(2026, 10, 31, 9, 20))))) == 1


def test_fora_da_janela_do_contrato_vira_perdida_mesmo_na_tolerancia(mundo):
    t = agendada(mundo)
    t.contrato.limites.janela_horario = carregar_janela("10:00", "22:00")
    store.salvar(t, agora=dt(2026, 10, 30, 12, 0).timestamp())
    assert asyncio.run(tick(novo(Relogio(dt(2026, 10, 31, 9, 10))))) == 0
    assert store.execucoes("videos")[0]["estado"] == "perdida"


def test_tarefa_inativa_ou_sem_agenda_nao_dispara(mundo):
    inativa = agendada(mundo)
    inativa.ativa = False
    store.salvar(inativa, agora=0)
    sem = mundo.tarefa(id="manual")
    store.salvar(sem, agora=0)
    assert asyncio.run(tick(novo(Relogio(dt(2026, 10, 31, 9, 0, 30))))) == 0


def test_pausa_impede_disparo_e_sobrevive_a_reinicio(mundo):
    store.salvar(agendada(mundo), agora=dt(2026, 10, 30, 12, 0).timestamp())
    r = Relogio(dt(2026, 10, 31, 9, 0, 30))
    ag = novo(r)
    ag.pausar("teste")
    assert asyncio.run(tick(ag)) == 0 and asyncio.run(tick(novo(r))) == 0       # outra instância = reinício
    assert novo(r).estado()["pausado"] is True
    ag.retomar()
    assert asyncio.run(tick(novo(r))) == 1


def test_botao_de_parada_pausa_o_agendador(mundo):
    r = Relogio()
    ag = novo(r)

    async def sobe():
        ag.iniciar()
        gate.parar("teste")
        await ag.encerrar()

    asyncio.run(sobe())
    assert ag.pausado() is True


def test_ao_subir_execucoes_em_andamento_viram_interrompidas(mundo):
    eid = store.iniciar_execucao("videos", "x", time.time())
    assert store.obter_execucao(eid)["estado"] == "em_andamento"

    async def sobe():
        ag = novo(Relogio())
        ag.iniciar()
        await ag.encerrar()

    asyncio.run(sobe())
    e = store.obter_execucao(eid)
    assert e["estado"] == "interrompida" and "reiniciado" in e["motivo"]


def test_proximas_no_estado(mundo):
    store.salvar(agendada(mundo), agora=0)
    est = novo(Relogio(dt(2026, 10, 31, 11, 0))).estado()
    assert est["proximas"][0]["proxima"].startswith("2026-11-01T09:00")


def test_tarefa_escrita_a_mao_em_json_roda_todo_dia(mundo, tmp_path):
    """Aceite da Fase 2: JSON na pasta de tarefas -> importa -> roda dia após dia, sem repetir."""
    import json
    from tarefas import pasta

    d = agendada(mundo).dump()
    (pasta.pasta() / "videos.json").write_text(json.dumps(d), encoding="utf-8")
    (pasta.pasta() / "quebrado.json").write_text('{"id": "x", "campo_errado": 1}', encoding="utf-8")
    res = pasta.importar(agora=dt(2026, 10, 30, 12, 0).timestamp())
    assert [r["ok"] for r in res] == [False, True] and "campo_errado" in res[0]["erro"]

    for dia, hora in [(31, 0), (1, 0), (2, 0)]:
        mes = 10 if dia == 31 else 11
        asyncio.run(tick(novo(Relogio(dt(2026, mes, dia, 9, 5)))))
    assert len(mundo.chamadas["t.gerar"]) == 3
    assert [e["estado"] for e in store.execucoes("videos")] == ["ok", "ok", "ok"]
    assert len(mundo.chamadas["subidos"]) == 6                         # arquivos regenerados = itens novos


def test_reimportar_preserva_ativa(mundo):
    import json
    from tarefas import pasta
    (pasta.pasta() / "v.json").write_text(json.dumps(agendada(mundo).dump()), encoding="utf-8")
    pasta.importar()
    store.definir_ativa("videos", False)
    pasta.importar()
    assert store.obter("videos").ativa is False
