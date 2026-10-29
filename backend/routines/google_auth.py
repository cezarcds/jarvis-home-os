"""Autenticação Google compartilhada pelas ferramentas (Agenda, Gmail, Analytics).

Autorizar (uma vez), dentro de backend/:
    python -m routines.google_auth

Arquivos (ajustáveis por variável de ambiente, nunca vão para o git):
    GOOGLE_CREDENTIALS_FILE  client secret OAuth tipo "App para computador"  (data/google_credentials.json)
    GOOGLE_TOKEN_FILE        token gerado após autorizar                       (data/google_token.json)

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


class GoogleAuthError(Exception):
    """Erro com mensagem amigável para mostrar/falar."""


def _paths():
    cred = Path(os.getenv("GOOGLE_CREDENTIALS_FILE") or DATA_DIR / "google_credentials.json")
    token = Path(os.getenv("GOOGLE_TOKEN_FILE") or DATA_DIR / "google_token.json")
    return cred, token


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
    creds = Credentials.from_authorized_user_file(str(token), SCOPES)
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


def get_service(api: str, version: str):
    from googleapiclient.discovery import build

    return build(api, version, credentials=get_credentials(), cache_discovery=False)


def authorize():
    from google_auth_oauthlib.flow import InstalledAppFlow

    cred, token = _paths()
    if not cred.exists():
        raise SystemExit(
            f"Arquivo não encontrado: {cred}\n"
            "Crie um OAuth Client ID do tipo 'App para computador' no Google Cloud Console, "
            "baixe o JSON e salve nesse caminho."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(cred), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    print(f"Autorizado. Token salvo em {token}")


if __name__ == "__main__":
    authorize()
