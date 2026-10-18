"""
Esquemas del servicio `integrals`.
"""
from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field, StringConstraints

Latex = Annotated[str, StringConstraints(strip_whitespace=True,
                                         min_length=1, max_length=1_000)]
ErrorCode = Literal["LATEX_INVALID", "NOT_AN_INTEGRAL", "UNSOLVABLE", "TIMEOUT"]


class IntegralCreate(BaseModel):
    latex: Latex = Field(description="Integral en LaTeX.",
                         examples=[r"\int_0^1 x^2 \, dx"])


class Source(BaseModel):
    kind: Literal["rest", "chat"] = "rest"
    channel_id: Optional[str] = None
    author_id: Optional[str] = None
    message_id: Optional[str] = None


class Result(BaseModel):
    latex: str = Field(description="Resultado simbólico en LaTeX.")
    numeric: Optional[float] = Field(
        None, description="Valor numérico, solo si el resultado no tiene símbolos libres.")
    indefinite: bool = Field(
        description="Verdadero si la integral es indefinida (el resultado omite la constante +C).")


class ErrorInfo(BaseModel):
    code: ErrorCode
    message: str


class Integral(BaseModel):
    id: str
    latex: str
    status: Literal["calculated", "failed"]
    result: Optional[Result] = None
    error: Optional[ErrorInfo] = None
    source: Source
    duration_ms: int
    created_at: datetime


class IntegralPage(BaseModel):
    items: list[Integral]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Optional[list[dict[str, Any]]] = None
