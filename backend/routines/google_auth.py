"""Autenticação Google compartilhada pelas ferramentas (Agenda, Gmail, Analytics).

Autorizar (uma vez), dentro de backend/:
    python -m routines.google_auth

Arquivos (ajustáveis por variável de ambiente, nunca vão para o git):
    GOOGLE_CREDENTIALS_FILE  client secret OAuth tipo "App para computador"  (data/google_credentials.json)
    GOOGLE_TOKEN_FILE        token gerado após autorizar                       (data/google_token.json)

Escritas (opcionais, só se você quiser):  python -m routines.google_auth --youtube --gmail

Se você já tem um token no formato "authorized user" (o JSON que o google-auth gera),
aponte GOOGLE_TOKEN_FILE para ele e ajuste get_credentials() se necessário.
"""
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("JARVIS_DATA_DIR") or Path(__file__).resolve().parent.parent / "data")

# Somente leitura por enquanto. Ações (arquivar, enviar...) exigirão escopos maiores e novo consentimento.
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]


# Escopos de ESCRITA (Fase 4): opcionais, cada um autorizado à parte e só se você pedir. Quem decide o que
# cada ferramenta pode fazer com eles é o gate; o escopo do Google é só o teto.
#   gmail.compose  -> permite criar rascunho E enviar (o Google não tem escopo só de rascunho)
#   youtube.upload -> enviar vídeos
ESCOPOS_OPCIONAIS = {
    "gmail": "https://www.googleapis.com/auth/gmail.compose",
    "youtube": "https://www.googleapis.com/auth/youtube.upload",
}


class GoogleAuthError(Exception):
    """Erro com mensagem amigável para mostrar/falar."""


def _paths():
    cred = Path(os.getenv("GOOGLE_CREDENTIALS_FILE") or DATA_DIR / "google_credentials.json")
    token = Path(os.getenv("GOOGLE_TOKEN_FILE") or DATA_DIR / "google_token.json")
    return cred, token


def escopos_autorizados() -> set:
    """Escopos que o token salvo realmente tem (lidos do arquivo, sem rede)."""
    import json

    _, token = _paths()
    try:
        dados = json.loads(token.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    esc = dados.get("scopes") or []
    return set(esc.split() if isinstance(esc, str) else esc)


def tem_escopo(chave: str) -> bool:
    return ESCOPOS_OPCIONAIS[chave] in escopos_autorizados()


def falta_escopo_msg(chave: str) -> str:
    return (f"Falta autorizar o escopo de {chave} no Google. Rode no backend: "
            f"python -m routines.google_auth --{chave}")


def check_escopo(chave: str):
    ok, motivo = check_google()
    if not ok:
        return ok, motivo
    if not tem_escopo(chave):
        return False, falta_escopo_msg(chave)
    return True, ""


def check_google():
    try:
        import googleapiclient  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
    except ImportError:
        return False, "Bibliotecas Google não instaladas (pip install -r requirements.txt)"
    _, token = _paths()
    if not token.exists():
        return False, "Google não autorizado. Rode: python -m routines.google_auth"
    return True, ""


def get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    _, token = _paths()
    if not token.exists():
        raise GoogleAuthError("Google não autorizado. Rode no backend: python -m routines.google_auth")
    # Pede no refresh exatamente os escopos que o token tem (pedir um que não foi concedido dá invalid_scope).
    creds = Credentials.from_authorized_user_file(str(token), sorted(escopos_autorizados() | set(SCOPES)))
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token.write_text(creds.to_json(), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            raise GoogleAuthError(
                "Não consegui renovar o acesso ao Google. Rode novamente: python -m routines.google_auth"
            ) from exc
    if not creds.valid:
        raise GoogleAuthError("Acesso ao Google expirado. Rode novamente: python -m routines.google_auth")
    return creds


def get_service(api: str, version: str, escopo: str = ""):
    """`escopo`: chave de ESCOPOS_OPCIONAIS exigida pela ferramenta. Sem ele concedido, falha ANTES de chamar a API."""
    if escopo and not tem_escopo(escopo):
        raise GoogleAuthError(falta_escopo_msg(escopo))
    from googleapiclient.discovery import build

    return build(api, version, credentials=get_credentials(), cache_discovery=False)


def authorize(extras=()):
    from google_auth_oauthlib.flow import InstalledAppFlow

    cred, token = _paths()
    if not cred.exists():
        raise SystemExit(
            f"Arquivo não encontrado: {cred}\n"
            "Crie um OAuth Client ID do tipo 'App para computador' no Google Cloud Console, "
            "baixe o JSON e salve nesse caminho."
        )
    # Mantém o que já estava autorizado (incl. escritas antigas) e soma só o que você pediu agora.
    escopos = sorted(set(SCOPES) | escopos_autorizados() | {ESCOPOS_OPCIONAIS[e] for e in extras})
    flow = InstalledAppFlow.from_client_secrets_file(str(cred), escopos)
    creds = flow.run_local_server(port=0, prompt="consent")
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    print(f"Autorizado. Token salvo em {token}")


if __name__ == "__main__":
    import sys

    pedidos = [a[2:] for a in sys.argv[1:] if a.startswith("--")]
    desconhecidos = [a for a in pedidos if a not in ESCOPOS_OPCIONAIS]
    if desconhecidos:
        raise SystemExit(f"Opção desconhecida: {desconhecidos}. Use: " + " ".join(f"--{k}" for k in ESCOPOS_OPCIONAIS))
    authorize(pedidos)
