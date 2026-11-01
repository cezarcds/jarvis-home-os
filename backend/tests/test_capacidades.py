"""Fase 3 — comando nomeado, VS Code e navegador. Casos NEGADOS primeiro. Roda processos e navegador de verdade."""
import asyncio
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from actions import gate
from capacidades import catalogo, navegador, processos, tools  # noqa: F401  (tools registra as ferramentas)
from connections import db
from routines.tools.registry import ToolError
from tarefas import executor, store
from tarefas.contrato import ContratoAtivo
from tarefas.models import carregar

POSIX = sys.platform != "win32"


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    db._migrated.clear()
    store.reset_state()
    gate.reset_state()
    executor._rodando.clear()
    navegador._ocupado = False


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "projeto-x"
    (p / "saida").mkdir(parents=True)
    (p / "gerar.py").write_text(
        "import sys, pathlib\n"
        "n = int(sys.argv[1])\n"
        "for i in range(n):\n"
        "    pathlib.Path('saida', f'video_{i+1}.mp4').write_bytes(bytes([i]) * 8)\n"
        "print('gerados', n)\n", encoding="utf-8")
    return p


def escrever_catalogo(proj, **extra):
    from connections.config import data_dir
    cat = {"schema": 1, "projetos": {"projeto-x": str(proj)},
           "comandos": {"gerar_videos": {"exec": [sys.executable, "gerar.py", "{quantidade}"], "projeto": "projeto-x",
                                          "params": {"quantidade": {"min": 1, "max": 10, "default": 2}}, "timeout_s": 60}}}
    cat.update(extra)
    (data_dir() / "comandos.json").write_text(json.dumps(cat), encoding="utf-8")
    return cat


def morto(pid: int) -> bool:
    """Morto de verdade: sumiu, ou virou zumbi (sem init que recolha, num container, ele fica listado)."""
    try:
        os.kill(pid, 0)
    except OSError:
        return True
    try:
        return open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0] == "Z"
    except OSError:
        return True


class ContratoLivre:
    """Contrato que deixa tudo passar: isola o comportamento da FERRAMENTA (o contrato real é testado à parte)."""
    aprovado = True

    def __init__(self, dominios=()):
        from types import SimpleNamespace
        self.c = SimpleNamespace(escopo=SimpleNamespace(dominios=list(dominios)))

    def checar(self, *a, **k):
        return None


def rodar_gate(nome, params, ctx=None, dominios=()):
    ctx = ctx or gate.Contexto(sid="t", contrato=ContratoLivre(dominios))
    return asyncio.run(gate.executar(nome, params, ctx))


# ---- só dentro de tarefa --------------------------------------------------------------------------

@pytest.mark.parametrize("nome,params", [
    ("comando.rodar", {"nome": "gerar_videos"}),
    ("vscode.abrir_projeto", {"pasta": "/tmp"}),
    ("navegador.abrir", {"url": "https://example.com/"}),
])
@pytest.mark.parametrize("origem", ["assistente", "llm", "rotina", "api"])
def test_fora_de_tarefa_o_gate_recusa(proj, nome, params, origem):
    escrever_catalogo(proj)
    with pytest.raises(gate.AcaoNegada, match="tarefa com contrato"):
        asyncio.run(gate.executar(nome, params, gate.Contexto(sid="t", origem=origem)))
    assert not list((proj / "saida").iterdir())


def test_roteador_de_voz_nao_enxerga_essas_ferramentas():
    from routines.tools.registry import REGISTRY
    for nome in ("comando.rodar", "vscode.abrir_projeto", "navegador.abrir"):
        assert REGISTRY[nome].spec()["somente_tarefa"] is True


# ---- catálogo: recusas ----------------------------------------------------------------------------

def test_sem_catalogo_nada_roda(proj):
    with pytest.raises(ToolError, match="catálogo"):
        rodar_gate("comando.rodar", {"nome": "gerar_videos"})


def test_comando_fora_do_catalogo_e_recusado(proj):
    escrever_catalogo(proj)
    with pytest.raises(ToolError, match="catálogo"):
        rodar_gate("comando.rodar", {"nome": "apagar_tudo"})


@pytest.mark.parametrize("mudar,trecho", [
    ({"schema": 2}, "schema"),
    ({"comandos": {"x": {"exec": "python gerar.py", "projeto": "projeto-x"}}}, "lista"),
    ({"comandos": {"x": {"exec": ["python"], "projeto": "outro"}}}, "não está cadastrado"),
    ({"comandos": {"x": {"exec": ["python", "{tema}"], "projeto": "projeto-x"}}}, "tema"),
    ({"comandos": {"x": {"exec": ["bin/tool"], "projeto": "projeto-x"}}}, "nome simples"),
    ({"comandos": {"x": {"exec": ["python"], "projeto": "projeto-x", "timeout_s": 99999999}}}, "timeout"),
    ({"comandos": {"Nome Ruim": {"exec": ["python"], "projeto": "projeto-x"}}}, "inválido"),
    ({"projetos": {"p": "relativo/pasta"}}, "absoluto"),
])
def test_catalogo_invalido_falha_fechado(proj, mudar, trecho):
    escrever_catalogo(proj, **mudar)
    with pytest.raises(ToolError, match=trecho):
        catalogo.carregar()


def test_quantidade_fora_dos_limites_e_recusada_sem_rodar(proj):
    escrever_catalogo(proj)
    for q in (0, 11, 9999):
        with pytest.raises(ToolError, match="entre 1 e 10"):
            rodar_gate("comando.rodar", {"nome": "gerar_videos", "quantidade": q})
    assert not list((proj / "saida").iterdir())


def test_quantidade_em_comando_que_nao_aceita(proj):
    escrever_catalogo(proj, comandos={"so": {"exec": [sys.executable, "-c", "print(1)"], "projeto": "projeto-x"}})
    with pytest.raises(ToolError, match="não aceita"):
        rodar_gate("comando.rodar", {"nome": "so", "quantidade": 3})


def test_quantidade_com_texto_nao_vira_argumento(proj):
    escrever_catalogo(proj)
    with pytest.raises(ToolError):
        rodar_gate("comando.rodar", {"nome": "gerar_videos", "quantidade": "2; rm -rf /"})


# ---- execução real --------------------------------------------------------------------------------

def test_roda_comando_nomeado_na_pasta_do_projeto(proj):
    escrever_catalogo(proj)
    r = rodar_gate("comando.rodar", {"nome": "gerar_videos", "quantidade": 3})
    assert r["data"]["codigo"] == 0 and "gerados 3" in r["data"]["saida"]
    assert sorted(p.name for p in (proj / "saida").iterdir()) == ["video_1.mp4", "video_2.mp4", "video_3.mp4"]


def test_default_do_catalogo(proj):
    escrever_catalogo(proj)
    rodar_gate("comando.rodar", {"nome": "gerar_videos"})
    assert len(list((proj / "saida").iterdir())) == 2


def test_codigo_de_erro_vira_toolerror_com_o_fim_da_saida(proj):
    escrever_catalogo(proj, comandos={"quebra": {"exec": [sys.executable, "-c", "print('falhou aqui'); raise SystemExit(3)"],
                                                 "projeto": "projeto-x"}})
    with pytest.raises(ToolError, match="código 3.*falhou aqui"):
        rodar_gate("comando.rodar", {"nome": "quebra"})


def test_programa_inexistente(proj):
    escrever_catalogo(proj, comandos={"x": {"exec": ["programa-que-nao-existe-xyz"], "projeto": "projeto-x"}})
    with pytest.raises(ToolError, match="não foi encontrado"):
        rodar_gate("comando.rodar", {"nome": "x"})


def test_ambiente_minimo_nao_vaza_chaves(proj, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "segredo-gemini-123")
    monkeypatch.setenv("JARVIS_SECRET_KEY", "segredo-cofre-456")
    escrever_catalogo(proj, comandos={"env": {"exec": [sys.executable, "-c", "import os; print(sorted(os.environ))"],
                                              "projeto": "projeto-x"}})
    r = rodar_gate("comando.rodar", {"nome": "env"})
    assert "GEMINI_API_KEY" not in r["data"]["saida"] and "JARVIS_SECRET_KEY" not in r["data"]["saida"]


def test_saida_e_redigida_e_truncada(proj):
    escrever_catalogo(proj, comandos={"v": {"exec": [sys.executable, "-c",
                                                      "print('x'*5000); print('Authorization: Bearer abcdefghijklmnop12345')"],
                                            "projeto": "projeto-x"}})
    r = rodar_gate("comando.rodar", {"nome": "v"})
    assert "abcdefghijklmnop12345" not in r["data"]["saida"] and len(r["data"]["saida"]) <= 1600


@pytest.mark.skipif(not POSIX, reason="checagem de pid por os.kill(pid, 0)")
def test_timeout_mata_a_arvore_inteira(proj):
    filho = proj / "filho.pid"
    script = ("import subprocess, sys, time\n"
              f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
              f"open(r'{filho}', 'w').write(str(p.pid))\n"
              "time.sleep(60)\n")
    (proj / "pai.py").write_text(script, encoding="utf-8")
    escrever_catalogo(proj, comandos={"pai": {"exec": [sys.executable, "pai.py"], "projeto": "projeto-x", "timeout_s": 1}})
    with pytest.raises(ToolError, match="passou de 1s"):
        rodar_gate("comando.rodar", {"nome": "pai"})
    time.sleep(0.3)
    assert morto(int(filho.read_text()))  # o neto também morreu


@pytest.mark.skipif(not POSIX, reason="checagem de pid por os.kill(pid, 0)")
def test_botao_parar_mata_o_processo(proj):
    marca = proj / "vivo.pid"
    (proj / "longo.py").write_text(f"import os, time\nopen(r'{marca}','w').write(str(os.getpid()))\ntime.sleep(60)\n", encoding="utf-8")
    escrever_catalogo(proj, comandos={"longo": {"exec": [sys.executable, "longo.py"], "projeto": "projeto-x", "timeout_s": 120}})

    async def cenario():
        ctx = gate.Contexto(sid="t", contrato=ContratoLivre())
        tarefa = asyncio.ensure_future(gate.executar("comando.rodar", {"nome": "longo"}, ctx))
        for _ in range(100):
            await asyncio.sleep(0.05)
            if marca.exists() and marca.read_text():
                break
        await asyncio.get_running_loop().run_in_executor(None, gate.parar)  # como o atalho global: de outra thread
        with pytest.raises(gate.ExecucaoCancelada):
            await tarefa

    asyncio.run(cenario())
    time.sleep(0.3)
    assert morto(int(marca.read_text()))
    assert processos._vivos == {}


# ---- contrato -------------------------------------------------------------------------------------

def tarefa_de(proj, pastas, ferramentas=("comando.rodar",), dominios=()):
    passo = ({"id": "g", "ferramenta": ferramentas[0], "params": {"nome": "gerar_videos", "quantidade": 2}}
             if ferramentas[0] == "comando.rodar" else {"id": "g", "ferramenta": ferramentas[0], "params": {}})
    return carregar({
        "schema": 1, "id": "t", "nome": "t",
        "contrato": {"escopo": {"ferramentas": list(ferramentas), "pastas": [str(p) for p in pastas], "dominios": list(dominios)},
                     "aprovado": True},
        "passos": [passo],
    })


def test_comando_cuja_pasta_esta_fora_do_contrato_e_negado(proj, tmp_path):
    escrever_catalogo(proj)
    outra = tmp_path / "outra"
    outra.mkdir()
    ctx = gate.Contexto(sid="t", contrato=ContratoAtivo(tarefa_de(proj, [outra])))
    with pytest.raises(gate.ForaDoContrato, match="fora das pastas"):
        rodar_gate("comando.rodar", {"nome": "gerar_videos"}, ctx)
    assert not list((proj / "saida").iterdir())


def test_comando_dentro_do_contrato_roda_e_a_verificacao_confere_os_arquivos(proj):
    escrever_catalogo(proj)
    d = {"schema": 1, "id": "videos", "nome": "v",
         "contrato": {"escopo": {"ferramentas": ["comando.rodar"], "pastas": [str(proj)]}, "aprovado": True},
         "passos": [{"id": "gerar", "ferramenta": "comando.rodar", "params": {"nome": "gerar_videos", "quantidade": 3},
                     "verificar": {"arquivos_em": "saida", "minimo": 3}}]}
    r = asyncio.run(executor.executar_tarefa(carregar(d)))
    assert r.estado == "ok", r.motivo


def test_verificacao_pega_comando_que_nao_gerou_nada(proj):
    escrever_catalogo(proj, comandos={"preguica": {"exec": [sys.executable, "-c", "print('ok')"], "projeto": "projeto-x"}})
    d = {"schema": 1, "id": "videos", "nome": "v",
         "contrato": {"escopo": {"ferramentas": ["comando.rodar"], "pastas": [str(proj)]}, "aprovado": True},
         "passos": [{"id": "gerar", "ferramenta": "comando.rodar", "params": {"nome": "preguica"},
                     "verificar": {"arquivos_em": "saida", "minimo": 1}}]}
    assert asyncio.run(executor.executar_tarefa(carregar(d))).estado != "ok"


def test_simulacao_ve_a_pasta_do_comando(proj, tmp_path):
    escrever_catalogo(proj)
    outra = tmp_path / "outra"
    outra.mkdir()
    sim = executor.simular(tarefa_de(proj, [outra]))
    assert "fora das pastas" in json.dumps(sim, ensure_ascii=False)


# ---- vscode ---------------------------------------------------------------------------------------

@pytest.fixture
def code_falso(tmp_path):
    marca = tmp_path / "code.args"
    if POSIX:
        exe = tmp_path / "code"
        exe.write_text(f"#!/bin/sh\necho \"$@\" > '{marca}'\n")
        exe.chmod(0o755)
    else:
        exe = tmp_path / "code.cmd"
        exe.write_text(f"@echo %* > \"{marca}\"\r\n")
    return exe, marca


def test_vscode_recusa_pasta_nao_cadastrada(proj, tmp_path, code_falso):
    exe, marca = code_falso
    escrever_catalogo(proj, vscode=str(exe))
    for pasta in (str(tmp_path), str(proj.parent), str(proj / "saida"), "projeto-x", "", "/etc"):
        with pytest.raises(ToolError, match="cadastrados"):
            rodar_gate("vscode.abrir_projeto", {"pasta": pasta})
    assert not marca.exists()


def test_vscode_recusa_atalho_com_dois_pontos(proj, code_falso):
    exe, marca = code_falso
    escrever_catalogo(proj, vscode=str(exe))
    with pytest.raises(ToolError):
        rodar_gate("vscode.abrir_projeto", {"pasta": str(proj / "saida" / "..")  + os.sep + "../" + proj.parent.name})
    assert not marca.exists()


def test_vscode_abre_projeto_cadastrado(proj, code_falso):
    exe, marca = code_falso
    escrever_catalogo(proj, vscode=str(exe))
    r = rodar_gate("vscode.abrir_projeto", {"pasta": str(proj)})
    assert "projeto-x" in r["falado"] and str(proj) in marca.read_text()


def test_vscode_dentro_de_tarefa_respeita_o_contrato(proj, tmp_path, code_falso):
    exe, marca = code_falso
    escrever_catalogo(proj, vscode=str(exe))
    outra = tmp_path / "outra"
    outra.mkdir()
    ctx = gate.Contexto(sid="t", contrato=ContratoAtivo(tarefa_de(proj, [outra], ferramentas=("vscode.abrir_projeto",))))
    with pytest.raises(gate.ForaDoContrato):
        rodar_gate("vscode.abrir_projeto", {"pasta": str(proj)}, ctx)
    assert not marca.exists()


def test_vscode_sem_code_instalado(proj, monkeypatch):
    escrever_catalogo(proj)
    monkeypatch.setattr(tools.shutil, "which", lambda _n: None)
    with pytest.raises(ToolError, match="VS Code"):
        rodar_gate("vscode.abrir_projeto", {"pasta": str(proj)})


# ---- navegador: allowlist -------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "javascript:alert(1)", "ftp://example.com/x", "data:text/html,<b>x</b>",
    "http://evil.com/", "http://example.com.evil.com/", "http://evil-example.com/", "http://user:pw@example.com/",
    "http://localhost:8000/", "http://169.254.169.254/", "//example.com", "example.com", "",
])
def test_url_fora_da_allowlist_e_recusada(url):
    assert navegador.url_ok(url, ["example.com"]) is not None


def test_url_permitida_e_subdominio():
    assert navegador.url_ok("https://example.com/a?b=1", ["example.com"]) is None
    assert navegador.url_ok("https://www.example.com/", ["example.com"]) is None


def test_sem_dominios_nada_abre():
    assert navegador.url_ok("https://example.com/", []) is not None


def test_em_tarefa_o_contrato_barra_dominio_antes_da_ferramenta(proj, monkeypatch):
    escrever_catalogo(proj)
    monkeypatch.setattr(navegador, "disponivel", lambda: (True, ""))
    t = tarefa_de(proj, [proj], ferramentas=("navegador.abrir",), dominios=["outro.com"])
    ctx = gate.Contexto(sid="t", contrato=ContratoAtivo(t))
    with pytest.raises(gate.ForaDoContrato):  # `url` é conferida pelo contrato antes de chamar a ferramenta
        rodar_gate("navegador.abrir", {"url": "https://example.com/"}, ctx)


def test_navegador_usa_os_dominios_do_contrato_da_execucao(proj, monkeypatch):
    escrever_catalogo(proj)
    monkeypatch.setattr(navegador, "disponivel", lambda: (True, ""))
    vistos = []

    async def falso(url, permitidos):
        vistos.append(list(permitidos))
        return {"type": "pagina", "title": "x", "data": {}, "falado": "", "resumo_llm": ""}

    monkeypatch.setattr(navegador, "abrir", falso)
    rodar_gate("navegador.abrir", {"url": "https://example.com/"}, dominios=["example.com", "api.example.com"])
    assert vistos == [["example.com", "api.example.com"]]


# ---- navegador: Chromium de verdade ---------------------------------------------------------------

class _Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        porta = self.server.server_port
        self.server.acessos.append(self.path)
        if self.path == "/redireciona":
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{porta}/")
            self.end_headers()
            return
        if self.path == "/interno":
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return
        corpo = (f"<html><head><title>Oi Jarvis</title></head><body>Texto da página"
                 f"<img src='http://localhost:{porta}/pixel.png'></body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo)


@pytest.fixture(scope="module")
def site():
    srv = HTTPServer(("127.0.0.1", 0), _Site)
    srv.acessos = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


@pytest.fixture
def chromium_ok():
    ok, _ = navegador.disponivel()
    if not ok:
        pytest.skip("Playwright não instalado")


def test_abre_pagina_permitida_e_bloqueia_recurso_de_outro_host(site, chromium_ok):
    srv, site = site, site.server_port
    srv.acessos.clear()
    try:
        r = asyncio.run(navegador.abrir(f"http://127.0.0.1:{site}/", ["127.0.0.1"]))
    except ToolError as exc:
        if "Não consegui abrir" in str(exc):
            pytest.skip(f"Chromium indisponível: {exc}")
        raise
    assert r["data"]["titulo"] == "Oi Jarvis" and "Texto da página" in r["data"]["texto"]
    assert "localhost" in r["data"]["bloqueados"]  # a imagem de outro host foi abortada na rede
    assert "/pixel.png" not in srv.acessos          # e o pedido NEM CHEGOU ao outro host


def test_redirecionamento_para_fora_e_bloqueado(site, chromium_ok):
    srv, site = site, site.server_port
    srv.acessos.clear()
    with pytest.raises(ToolError, match="allowlist|fora"):
        asyncio.run(navegador.abrir(f"http://127.0.0.1:{site}/redireciona", ["127.0.0.1"]))
    assert srv.acessos == ["/redireciona"]  # o destino do redirecionamento não foi buscado


def test_redirecionamento_dentro_da_allowlist_funciona(site, chromium_ok):
    r = asyncio.run(navegador.abrir(f"http://127.0.0.1:{site.server_port}/interno", ["127.0.0.1"]))
    assert r["data"]["titulo"] == "Oi Jarvis" and r["data"]["url"].endswith("/")


def test_navegador_nao_fica_preso_depois_de_erro(site, chromium_ok):
    with pytest.raises(ToolError):
        asyncio.run(navegador.abrir(f"http://127.0.0.1:{site.server_port}/redireciona", ["127.0.0.1"]))
    assert navegador._ocupado is False and navegador._ativos == []


def test_perfil_fica_em_pasta_propria(chromium_ok):
    assert navegador.perfil().endswith("browser-profile")
