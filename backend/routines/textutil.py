import re
import unicodedata


def normalize(s: str) -> str:
    """minúsculas, sem acentos nem pontuação, espaços únicos, sem 'jarvis' nas pontas."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^(ei |oi |ola )?jarvis\b ?", "", s)
    s = re.sub(r" ?\bjarvis$", "", s)
    return s.strip()


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:40] or "rotina"
