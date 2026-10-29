"""Catálogo de provedores. Adicionar um novo = registrar um ProviderSpec aqui."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    auth_url: str
    token_url: str
    revoke_url: str
    base_scopes: tuple[str, ...]
    # escopo -> descrição. Só estes podem ser ativados pelo admin (allowlist).
    optional_scopes: dict[str, str] = field(default_factory=dict)
    extra_auth_params: dict[str, str] = field(default_factory=dict)
    env_client_id: str = ""
    env_client_secret: str = ""
    # Palavras que indicam que o usuário está falando deste provedor.
    strong_keywords: tuple[str, ...] = ()
    # Palavras ambíguas: só contam junto de um verbo de leitura (ver tools.py).
    weak_keywords: tuple[str, ...] = ()
    spoken_name: str = ""


G = "https://www.googleapis.com/auth/"

GOOGLE = ProviderSpec(
    id="google",
    label="Google",
    auth_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    revoke_url="https://oauth2.googleapis.com/revoke",
    # Somente leitura nesta fase.
    base_scopes=(
        "openid",
        "email",
        G + "gmail.readonly",
        G + "drive.readonly",
        G + "analytics.readonly",
    ),
    optional_scopes={
        G + "documents.readonly": "Google Docs (leitura)",
        G + "spreadsheets.readonly": "Google Sheets (leitura)",
        G + "youtube.readonly": "YouTube (leitura)",
    },
    extra_auth_params={
        "access_type": "offline",      # devolve refresh_token
        "prompt": "consent",           # garante o refresh_token mesmo em reconexão
        "include_granted_scopes": "true",
    },
    env_client_id="GOOGLE_CLIENT_ID",
    env_client_secret="GOOGLE_CLIENT_SECRET",
    strong_keywords=("gmail", "google drive", "meu drive", "analytics", "google docs", "google sheets"),
    # Quando o Zoho entrar, "email" passa a exigir desambiguação (Gmail x Zoho).
    weak_keywords=("email", "e-mail", "emails", "e-mails"),
    spoken_name="Google",
)

PROVIDERS: dict[str, ProviderSpec] = {GOOGLE.id: GOOGLE}


def get_provider(provider_id: str) -> ProviderSpec | None:
    return PROVIDERS.get(provider_id)
