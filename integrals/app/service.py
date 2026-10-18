"""
Caso de uso: calcular una integral, guardarla y emitir el evento.
"""
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Optional
from uuid import uuid4

from .calculator import calculate
from .events import EventPublisher
from .logging_conf import correlation_id
from .repository import IntegralRepository
from .schemas import Source

log = logging.getLogger("integrals.service")

SCHEMA_VERSION = 1


class IntegralService:
    def __init__(self, repository: IntegralRepository, publisher: EventPublisher,
                 calculator: Callable[[str], dict[str, Any]] = calculate):
        self.repository = repository
        self.publisher = publisher
        self.calculator = calculator

    def process(self, latex: str, source: Source,
                integral_id: Optional[str] = None) -> dict[str, Any]:
        started = perf_counter()
        outcome = self.calculator(latex)
        integral = {
            "id": integral_id or str(uuid4()),
            "latex": latex,
            "status": "calculated" if outcome["ok"] else "failed",
            "result": outcome.get("result"),
            "error": outcome.get("error"),
            "source": source.model_dump(),
            "duration_ms": round((perf_counter() - started) * 1000),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.repository.insert(integral)
        self._emit(integral)
        return integral

    def _emit(self, integral: dict[str, Any]) -> None:
        routing_key = f"integral.{integral['id']}.{integral['status']}"
        self.publisher.publish(routing_key, {
            "type": routing_key,
            "subject_id": integral["id"],
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": SCHEMA_VERSION,
            "correlation_id": correlation_id.get(),
            "data": integral,
        })
        log.info("integral_processed",
                 extra={"fields": {"integral_id": integral["id"],
                                   "status": integral["status"]}})
