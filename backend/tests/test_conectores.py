"""Fase 4 — YouTube (só privado), Gmail rascunhar/enviar e GA4 genérico. Casos NEGADOS primeiro.
Nenhuma chamada real ao Google: o serviço é falso e registra tudo que for chamado."""
import ast
import asyncio
import inspect
import json
import sys
import types

import pytest

from actions import gate
from connections import db
from routines import google_auth
from routines.tools import analytics, gmail_escrita, youtube
from routines.tools.registry import REGISTRY, ToolError
from tarefas import executor, store
from tarefas.models import carregar


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(google_auth, "DATA_DIR", tmp_path / "data")
    monkeypatch.delenv("GOOGLE_TOKEN_FILE", raising=False)
    db._migrated.clear()
    store.reset_state()
    gate.reset_state()
    executor._rodando.clear()


def com_escopos(monkeypatch, *chaves):
    """Finge que o token tem os escopos das chaves, e que as bibliotecas estão instaladas."""
    monkeypatch.setattr(google_auth, "escopos_autorizados", lambda: {google_auth.ESCOPOS_OPCIONAIS[c] for c in chaves})
    monkeypatch.setattr(google_auth, "check_google", lambda: (True, ""))


class Servico:
    """Serviço Google falso: guarda o nome de TODA chamada feita (para provar o que NÃO foi chamado)."""

    def __init__(self, resposta=None):
        self.chamadas = []
        self.resposta = resposta or {}

    def __getattr__(self, nome):
        self.chamadas.append(nome)
        return self

    def __call__(self, *a, **k):
        if k.get("body") is not None:
            self.corpo = k["body"]
        return self

    def execute(self):
        return {"id": "d1"}


class ContratoLivre:
    aprovado = True

    def __init__(self):
        self.c = types.SimpleNamespace(escopo=types.SimpleNamespace(dominios=[]))

    def checar(self, *a, **k):
        return None


def video(tmp_path, nome="v.mp4", dados=b"x" * 10):
    p = tmp_path / nome
    p.write_bytes(dados)
    return str(p)


# ---- escopos / reconexão --------------------------------------------------------------------------

def test_sem_token_nenhum_escopo(tmp_path):
    assert google_auth.escopos_autorizados() == set()


def test_escopos_lidos_do_arquivo_do_token(tmp_path):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "google_token.json").write_text(
        json.dumps({"scopes": ["https://www.googleapis.com/auth/gmail.readonly"]}), encoding="utf-8")
    assert google_auth.escopos_autorizados() == {"https://www.googleapis.com/auth/gmail.readonly"}
    assert not google_auth.tem_escopo("gmail") and not google_auth.tem_escopo("youtube")


def test_faltando_escopo_ferramenta_fica_indisponivel_e_diz_como_reconectar(monkeypatch):
    com_escopos(monkeypatch)  # token sem escritas
    for nome, chave in (("youtube.upload_privado", "youtube"), ("gmail.rascunhar", "gmail"), ("gmail.enviar", "gmail")):
        ok, motivo = REGISTRY[nome].disponivel()
        assert not ok and f"--{chave}" in motivo


def test_get_service_recusa_antes_de_chamar_a_api_sem_o_escopo(monkeypatch):
    com_escopos(monkeypatch)
    with pytest.raises(google_auth.GoogleAuthError, match="--youtube"):
        google_auth.get_service("youtube", "v3", escopo="youtube")


def test_opcao_desconhecida_do_autorizar_e_recusada():
    assert set(google_auth.ESCOPOS_OPCIONAIS) == {"gmail", "youtube"}


def test_gate_recusa_ferramenta_sem_escopo(monkeypatch):
    com_escopos(monkeypatch)
    with pytest.raises(gate.AcaoNegada, match="--gmail"):
        asyncio.run(gate.executar("gmail.rascunhar", {"para": "a@b.com", "assunto": "x", "corpo": "y"}, gate.Contexto(sid="t")))


# ---- YouTube: só privado --------------------------------------------------------------------------

def test_ferramenta_nao_tem_parametro_de_visibilidade():
    nomes = {p["nome"] for p in REGISTRY["youtube.upload_privado"].spec()["params"]}
    assert not nomes & {"visibilidade", "privacidade", "privacyStatus", "publico"}


@pytest.mark.parametrize("arq,tit,msg", [
    ("relativo.mp4", "t", "caminho completo"),
    ("/tmp/x.exe", "t", "Formato"),
    ("/tmp/nao_existe_xyz.mp4", "t", "não existe"),
])
def test_arquivo_invalido(arq, tit, msg):
    with pytest.raises(ToolError, match=msg):
        youtube.validar(arq, tit, "", "")


def test_arquivo_vazio(tmp_path):
    with pytest.raises(ToolError, match="vazio"):
        youtube.validar(video(tmp_path, dados=b""), "t", "", "")


@pytest.mark.parametrize("titulo", ["", "  ", "a" * 101, "linha1\nlinha2", "<script>"])
def test_titulo_invalido(tmp_path, titulo):
    with pytest.raises(ToolError, match="título"):
        youtube.validar(video(tmp_path), titulo, "", "")


def test_tags_demais_ou_perigosas(tmp_path):
    with pytest.raises(ToolError, match="tags"):
        youtube.validar(video(tmp_path), "t", "", ",".join(f"t{i}" for i in range(31)))
    with pytest.raises(ToolError, match="tags"):
        youtube.validar(video(tmp_path), "t", "", "ok,<b>")


def test_corpo_enviado_ao_google_e_sempre_privado(tmp_path):
    v = youtube.validar(video(tmp_path), "Meu vídeo", "desc", "a, b")
    corpo = youtube.corpo_privado(v)
    assert corpo["status"]["privacyStatus"] == "private"
    assert corpo["snippet"]["tags"] == ["a", "b"]


def fake_google(monkeypatch, resposta, erro_http=None):
    """Injeta googleapiclient falso e um serviço cujo insert devolve `resposta` (ou levanta `erro`)."""
    class HttpError(Exception):
        def __init__(self, status, texto=""):
            super().__init__(texto)
            self.resp = types.SimpleNamespace(status=status)

    class Req:
        def next_chunk(self):
            if erro_http:
                raise HttpError(erro_http, "quotaExceeded" if erro_http == 403 else "falha")
            return None, resposta

    svc = Servico()
    svc.videos = lambda: types.SimpleNamespace(insert=lambda **k: (setattr(svc, "corpo", k["body"]), Req())[1])
    http = types.ModuleType("googleapiclient.http")
    http.MediaFileUpload = lambda *a, **k: object()
    errors = types.ModuleType("googleapiclient.errors")
    errors.HttpError = HttpError
    pkg = types.ModuleType("googleapiclient")
    pkg.http, pkg.errors = http, errors
    for n, m in (("googleapiclient", pkg), ("googleapiclient.http", http), ("googleapiclient.errors", errors)):
        monkeypatch.setitem(sys.modules, n, m)
    monkeypatch.setattr(youtube, "get_service", lambda *a, **k: svc)
    return svc


def test_upload_ok_confere_o_retorno(tmp_path, monkeypatch):
    svc = fake_google(monkeypatch, {"id": "yt1", "status": {"privacyStatus": "private"}})
    r = youtube._enviar(youtube.validar(video(tmp_path), "T", "", ""))
    assert r["id"] == "yt1" and svc.corpo["status"]["privacyStatus"] == "private"


def test_se_o_google_devolver_publico_a_ferramenta_grita(tmp_path, monkeypatch):
    fake_google(monkeypatch, {"id": "yt9", "status": {"privacyStatus": "public"}})
    with pytest.raises(ToolError, match="ATENÇÃO.*yt9"):
        youtube._enviar(youtube.validar(video(tmp_path), "T", "", ""))


def test_cota_estourada_e_falha_definitiva(tmp_path, monkeypatch):
    fake_google(monkeypatch, None, erro_http=403)
    with pytest.raises(ToolError, match="cota"):
        youtube._enviar(youtube.validar(video(tmp_path), "T", "", ""))


def test_erro_de_servidor_nao_vira_toolerror_para_o_executor_marcar_incerto(tmp_path, monkeypatch):
    fake_google(monkeypatch, None, erro_http=503)
    with pytest.raises(Exception) as exc:
        youtube._enviar(youtube.validar(video(tmp_path), "T", "", ""))
    assert not isinstance(exc.value, ToolError)


def test_parar_cancela_entre_os_blocos(tmp_path, monkeypatch):
    class Req:
        def next_chunk(self):
            youtube._ao_parar()
            return object(), None

    svc = Servico()
    svc.videos = lambda: types.SimpleNamespace(insert=lambda **k: Req())
    http = types.ModuleType("googleapiclient.http"); http.MediaFileUpload = lambda *a, **k: object()
    errors = types.ModuleType("googleapiclient.errors"); errors.HttpError = type("HttpError", (Exception,), {})
    pkg = types.ModuleType("googleapiclient")
    for n, m in (("googleapiclient", pkg), ("googleapiclient.http", http), ("googleapiclient.errors", errors)):
        monkeypatch.setitem(sys.modules, n, m)
    monkeypatch.setattr(youtube, "get_service", lambda *a, **k: svc)
    with pytest.raises(ToolError, match="PARAR"):
        youtube._enviar(youtube.validar(video(tmp_path), "T", "", ""))


# ---- YouTube dentro de um contrato real -----------------------------------------------------------

def tarefa(pasta, **mudar):
    d = {"schema": 1, "id": "yt", "nome": "YT",
         "contrato": {"escopo": {"ferramentas": ["youtube.upload_privado", "gmail.enviar", "gmail.rascunhar"],
                                 "pastas": [str(pasta)], "contas": ["youtube:teste"]},
                      "limites": {"por_dia": {"youtube.upload_privado": 2}, "visibilidade": "privado"}, "aprovado": True},
         "passos": [{"id": "subir", "ferramenta": "youtube.upload_privado",
                     "params": {"arquivo": str(pasta / "v.mp4"), "titulo": "T", "conta": "youtube:teste"}}]}
    d.update(mudar)
    return carregar(d)


def ativar_youtube(monkeypatch, enviado):
    com_escopos(monkeypatch, "youtube", "gmail")
    monkeypatch.setattr(youtube, "_enviar", lambda v: enviado.append(v) or {"id": "yt1", "visibilidade": "private", "link": "x"})


def test_arquivo_fora_da_pasta_do_contrato_e_negado(tmp_path, monkeypatch):
    enviado = []
    ativar_youtube(monkeypatch, enviado)
    pasta = tmp_path / "ok"; pasta.mkdir()
    fora = tmp_path / "fora"; fora.mkdir(); video(fora)
    t = tarefa(pasta)
    t.passos[0].params["arquivo"] = str(fora / "v.mp4")
    r = asyncio.run(executor.executar_tarefa(t, dormir=lambda s: asyncio.sleep(0)))
    assert enviado == [] and r.estado != "ok"


def test_conta_fora_do_contrato_e_negada(tmp_path, monkeypatch):
    enviado = []
    ativar_youtube(monkeypatch, enviado)
    pasta = tmp_path / "ok"; pasta.mkdir(); video(pasta)
    t = tarefa(pasta)
    t.passos[0].params["conta"] = "youtube:outra"
    asyncio.run(executor.executar_tarefa(t, dormir=lambda s: asyncio.sleep(0)))
    assert enviado == []


def test_dentro_do_contrato_nivel_2_sobe_sem_confirmar_e_respeita_limite_diario(tmp_path, monkeypatch):
    enviado = []
    ativar_youtube(monkeypatch, enviado)
    pasta = tmp_path / "ok"; pasta.mkdir(); video(pasta)
    t = tarefa(pasta)
    r = asyncio.run(executor.executar_tarefa(t, dormir=lambda s: asyncio.sleep(0)))
    assert r.estado == "ok" and len(enviado) == 1
    assert enviado[0]["titulo"] == "T"
    # limite de 2 por dia: o 3º ataque (mesmo vídeo muda mtime → outro item) é barrado
    for i in range(2):
        (pasta / "v.mp4").write_bytes(b"y" * (20 + i))
        asyncio.run(executor.executar_tarefa(t, dormir=lambda s: asyncio.sleep(0)))
    assert len(enviado) == 2


def test_fora_de_tarefa_upload_e_recusado(tmp_path, monkeypatch):
    ativar_youtube(monkeypatch, [])
    with pytest.raises(gate.AcaoNegada, match="tarefa com contrato"):
        asyncio.run(gate.executar("youtube.upload_privado", {"arquivo": video(tmp_path), "titulo": "t"}, gate.Contexto(sid="t")))


# ---- Gmail: rascunhar x enviar --------------------------------------------------------------------

@pytest.mark.parametrize("para,assunto,corpo,msg", [
    ("", "a", "b", "destinatários"),
    ("a@b.com", "", "b", "assunto"),
    ("a@b.com", "a", "  ", "corpo"),
    ("a@b.com\nBcc: x@y.com", "a", "b", "uma linha"),
    ("a@b.com", "oi\nBcc: x@y.com", "b", "uma linha"),
    ("naoeumemail", "a", "b", "inválido"),
    (",".join(f"u{i}@b.com" for i in range(6)), "a", "b", "destinatários"),
])
def test_validacao_do_email(para, assunto, corpo, msg):
    with pytest.raises(ToolError, match=msg):
        gmail_escrita.validar(para, assunto, corpo)


def test_enviar_recusa_corpo_que_nao_cabe_na_confirmacao():
    with pytest.raises(ToolError, match="corpo"):
        gmail_escrita.validar("a@b.com", "a", "x" * 1501, gmail_escrita.CORPO_MAX_ENVIO)


def test_rascunhar_so_chama_drafts_create_e_nunca_envio(monkeypatch):
    com_escopos(monkeypatch, "gmail")
    svc = Servico()
    monkeypatch.setattr(gmail_escrita, "get_service", lambda *a, **k: svc)
    ctx = gate.Contexto(sid="t", contrato=ContratoLivre())
    r = asyncio.run(gate.executar("gmail.rascunhar", {"para": "a@b.com", "assunto": "oi", "corpo": "texto"}, ctx))
    assert r["data"]["rascunho_id"] == "d1"
    assert "drafts" in svc.chamadas and "create" in svc.chamadas
    assert "send" not in svc.chamadas and "messages" not in svc.chamadas


def test_codigo_de_rascunhar_nao_contem_nenhuma_chamada_de_envio():
    for fn in (gmail_escrita._criar_rascunho, gmail_escrita.gmail_rascunhar):
        fonte = inspect.getsource(fn)
        atributos = {n.attr for n in ast.walk(ast.parse(fonte.lstrip())) if isinstance(n, ast.Attribute)}
        assert "send" not in atributos and "messages" not in atributos
        assert "_enviar_email" not in fonte


def test_rascunhar_fora_de_tarefa_pede_confirmacao_e_nao_cria(monkeypatch):
    com_escopos(monkeypatch, "gmail")
    svc = Servico()
    monkeypatch.setattr(gmail_escrita, "get_service", lambda *a, **k: svc)
    with pytest.raises(gate.ConfirmacaoPendente):
        asyncio.run(gate.executar("gmail.rascunhar", {"para": "a@b.com", "assunto": "oi", "corpo": "t"}, gate.Contexto(sid="t")))
    assert svc.chamadas == []


def test_enviar_dentro_de_tarefa_e_recusado_mesmo_listado_no_contrato(tmp_path, monkeypatch):
    com_escopos(monkeypatch, "gmail")
    svc = Servico()
    monkeypatch.setattr(gmail_escrita, "get_service", lambda *a, **k: svc)
    pasta = tmp_path / "ok"; pasta.mkdir()
    t = tarefa(pasta, passos=[{"id": "e", "ferramenta": "gmail.enviar",
                               "params": {"para": "a@b.com", "assunto": "oi", "corpo": "t"}}])
    r = asyncio.run(executor.executar_tarefa(t, dormir=lambda s: asyncio.sleep(0)))
    assert svc.chamadas == [] and r.estado != "ok"
    ctx = gate.Contexto(sid="t", contrato=ContratoLivre())
    with pytest.raises(gate.AcaoNegada, match="não roda dentro de tarefa"):
        asyncio.run(gate.executar("gmail.enviar", {"para": "a@b.com", "assunto": "oi", "corpo": "t"}, ctx))


def test_simulacao_tambem_mostra_enviar_negado(tmp_path, monkeypatch):
    com_escopos(monkeypatch, "gmail")
    pasta = tmp_path / "ok"; pasta.mkdir()
    t = tarefa(pasta, passos=[{"id": "e", "ferramenta": "gmail.enviar",
                               "params": {"para": "a@b.com", "assunto": "oi", "corpo": "t"}}])
    sim = executor.simular(t)
    assert "não roda dentro de tarefa" in json.dumps(sim, ensure_ascii=False)


def test_enviar_por_clique_mostra_texto_inteiro_e_so_envia_na_confirmacao(monkeypatch):
    com_escopos(monkeypatch, "gmail")
    svc = Servico()
    monkeypatch.setattr(gmail_escrita, "get_service", lambda *a, **k: svc)
    params = {"para": "a@b.com", "assunto": "Proposta", "corpo": "Texto completo do e-mail."}
    with pytest.raises(gate.ConfirmacaoPendente) as exc:
        asyncio.run(gate.executar("gmail.enviar", params, gate.Contexto(sid="t")))
    assert "Texto completo do e-mail." in exc.value.pendente["texto"] and "a@b.com" in exc.value.pendente["texto"]
    assert svc.chamadas == []
    with pytest.raises(gate.ConfirmacaoInvalida):
        asyncio.run(gate.confirmar(exc.value.pendente["id"], "voz"))
    assert svc.chamadas == []
    asyncio.run(gate.confirmar(exc.value.pendente["id"], "clique"))
    assert "send" in svc.chamadas
    with pytest.raises(gate.GateErro):
        asyncio.run(gate.confirmar(exc.value.pendente["id"], "clique"))  # uso único


def test_mime_nao_deixa_cabecalho_extra(monkeypatch):
    import base64
    v = gmail_escrita.validar("a@b.com, c@d.com", "Assunto", "Corpo")
    texto = base64.urlsafe_b64decode(gmail_escrita._raw(v)).decode()
    assert "To: a@b.com, c@d.com" in texto and "Bcc" not in texto


# ---- GA4 ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("metricas,dimensoes,prop,msg", [
    ("sessions; DROP", "", "123", "Métrica não permitida"),
    ("", "", "123", "métricas"),
    ("sessions", "senha", "123", "Dimensão não permitida"),
    ("sessions,sessions", "", "123", "repetidas"),
    ("sessions", "country", "abc", "número"),
    ("sessions", "", "", "número"),
    (",".join(f"customEvent:e{i}" for i in range(9)), "", "123", "métricas"),
    ("sessions", "customEvent:a b", "123", "Dimensão não permitida"),
])
def test_ga4_recusa_nomes_fora_da_lista(metricas, dimensoes, prop, msg):
    with pytest.raises(ToolError, match=msg):
        analytics.validar_consulta(metricas, dimensoes, 7, 10, prop)


def test_ga4_aceita_conhecidas_e_personalizadas_e_limita_janela_e_linhas():
    q = analytics.validar_consulta("sessions,customEvent:cliques", "country,pagePath", 9999, 9999, "42")
    assert q["dias"] == 365 and q["limite"] == 100 and q["metricas"] == ["sessions", "customEvent:cliques"]


def test_ga4_e_leitura_e_contamina():
    t = REGISTRY["analytics.consultar"]
    assert t.risco == "leitura" and t.le_dado_externo is True


# ---- fluxo inteiro: gerar (sem lista) -> verificar -> subir cada arquivo como privado ---------------

def test_fluxo_gerar_e_subir_usa_os_arquivos_provados_pela_verificacao(tmp_path, monkeypatch):
    from routines.tools.registry import Param, Tool
    enviado = []
    ativar_youtube(monkeypatch, enviado)
    pasta = tmp_path / "proj"; (pasta / "saida").mkdir(parents=True)

    async def gerar(quantidade=1):
        for i in range(int(quantidade)):
            (pasta / "saida" / f"v{i}.mp4").write_bytes(bytes([i + 1]) * 8)
        return {"type": "x", "title": "g", "data": {"codigo": 0}, "falado": "", "resumo_llm": ""}  # SEM lista de arquivos

    monkeypatch.setitem(REGISTRY, "t.gerar", Tool("t.gerar", "g", "falsa", [Param("quantidade", "int", 1)], gerar, "acao_local"))
    (pasta / "saida" / "velho.mp4").write_bytes(b"antigo")
    import os, time
    os.utime(pasta / "saida" / "velho.mp4", (time.time() - 86400,) * 2)
    t = carregar({
        "schema": 1, "id": "fluxo", "nome": "Fluxo", "parametros": {"quantidade": 2},
        "contrato": {"escopo": {"ferramentas": ["t.gerar", "youtube.upload_privado"], "pastas": [str(pasta)],
                                "contas": ["youtube:teste"]},
                     "limites": {"por_dia": {"youtube.upload_privado": 5}, "visibilidade": "privado", "espera_s": 0},
                     "aprovado": True},
        "passos": [
            {"id": "gerar", "ferramenta": "t.gerar", "params": {"quantidade": "{quantidade}"},
             "verificar": {"arquivos_em": "saida", "minimo": "{quantidade}"}},
            {"id": "subir", "ferramenta": "youtube.upload_privado", "para_cada": "{gerar.arquivos}",
             "params": {"arquivo": "{item}", "titulo": "Vídeo do dia", "conta": "youtube:teste"}},
        ]})
    r = asyncio.run(executor.executar_tarefa(t, dormir=lambda s: asyncio.sleep(0)))
    assert r.estado == "ok", r.motivo
    assert sorted(os.path.basename(v["arquivo"]) for v in enviado) == ["v0.mp4", "v1.mp4"]  # o velho NÃO sobe
