from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Step(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    ferramenta: str
    params: Dict[str, Any] = Field(default_factory=dict)


class Tela(BaseModel):
    cena: Literal["briefing"] = "briefing"
    titulo: Optional[str] = None
    blocos: List[str] = Field(default_factory=list)  # ids de passos; vazio = todos


class Fala(BaseModel):
    # resumo: LLM resume em voz; template: frases fixas (nenhum dado vai para o LLM); nenhuma: só tela
    modo: Literal["resumo", "template", "nenhuma"] = "resumo"
    instrucao: Optional[str] = None


class Routine(BaseModel):
    id: str = ""
    nome: str = Field(min_length=1, max_length=60)
    descricao: str = ""
    gatilhos: List[str] = Field(default_factory=list)
    tipo: Literal["leitura", "acao"] = "leitura"
    ativa: bool = True
    passos: List[Step] = Field(min_length=1, max_length=12)
    tela: Tela = Field(default_factory=Tela)
    fala: Fala = Field(default_factory=Fala)
    criada_em: str = ""
    atualizada_em: str = ""

    @field_validator("gatilhos")
    @classmethod
    def _gatilhos(cls, v: List[str]) -> List[str]:
        seen, out = set(), []
        for g in v:
            g = (g or "").strip()
            if g and g.lower() not in seen:
                seen.add(g.lower())
                out.append(g[:120])
        return out[:20]

    @model_validator(mode="after")
    def _consistencia(self):
        ids = [s.id for s in self.passos]
        if len(set(ids)) != len(ids):
            raise ValueError("ids de passos duplicados")
        invalid = [b for b in self.tela.blocos if b not in ids]
        if invalid:
            raise ValueError(f"tela.blocos referencia passos inexistentes: {invalid}")
        return self
