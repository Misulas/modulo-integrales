import logging
import os
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from .chat_adapter import ChatAdapter
from .events import ChatEventConsumer, EventPublisher
from .logging_conf import configure_logging, correlation_id
from .repository import IntegralRepository
from .schemas import ErrorResponse, Integral, IntegralCreate, IntegralPage, Source
from .service import IntegralService

log = logging.getLogger("integrals.api")

DESCRIPTION = """Calcula integrales a partir de texto LaTeX.

Cada cálculo se guarda y emite un evento en el exchange `integrals`
(`integral.<id>.calculated` o `integral.<id>.failed`). Un cálculo que no se pudo
resolver **no es un error HTTP**: se registra con `status = failed` y el detalle
en `error`. Versión de la API: `/api/v1`."""


def create_app(repository: Optional[IntegralRepository] = None,
               publisher: Optional[EventPublisher] = None,
               service: Optional[IntegralService] = None,
               chat: Optional[ChatAdapter] = None,
               rabbitmq_url: Optional[str] = None) -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        consumer = None
        if rabbitmq_url:
            consumer = ChatEventConsumer(rabbitmq_url, app.state.chat.handle_event,
                                         prepare=app.state.chat.ensure_bot_id)
            consumer.start()
        yield
        if consumer:
            consumer.stop()

    app = FastAPI(title="Integral Calculator", version="1.0.0",
                  description=DESCRIPTION, lifespan=lifespan)

    repository = repository or IntegralRepository(
        MongoClient(os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
                    ).integrals_service)
    publisher = publisher or EventPublisher(rabbitmq_url)
    service = service or IntegralService(repository, publisher)
    chat = chat or ChatAdapter(
        repository, service,
        users_url=os.environ.get("USERS_URL", "http://users:8000"),
        messages_url=os.environ.get("MESSAGES_URL", "http://messages:8000"))
    app.state.repository, app.state.publisher = repository, publisher
    app.state.service, app.state.chat = service, chat

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        correlation_id.set(request.headers.get("X-Correlation-ID") or str(uuid4()))
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id.get()
        log.info("request", extra={"fields": {
            "method": request.method, "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((perf_counter() - started) * 1000)}})
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse({"code": code, "message": str(exc.detail)},
                            status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc: RequestValidationError):
        details = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                   for e in exc.errors()]
        return JSONResponse({"code": "VALIDATION_ERROR",
                             "message": "La solicitud no es válida.",
                             "details": details}, status_code=422)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/v1/integrals", status_code=status.HTTP_201_CREATED,
              response_model=Integral,
              responses={422: {"model": ErrorResponse}},
              summary="Calcular una integral",
              description="Calcula (máximo 10 s) y registra la integral. "
                          "Si no se puede resolver, responde 201 con `status = failed`.")
    def create_integral(body: IntegralCreate):
        return service.process(body.latex, Source(kind="rest"))

    @app.get("/api/v1/integrals/{integral_id}", response_model=Integral,
             responses={404: {"model": ErrorResponse}},
             summary="Consultar una integral")
    def get_integral(integral_id: str):
        integral = repository.get(integral_id)
        if integral is None:
            raise HTTPException(status_code=404, detail="Integral not found")
        return integral

    @app.get("/api/v1/integrals", response_model=IntegralPage,
             summary="Historial de integrales (más recientes primero)")
    def list_integrals(limit: int = Query(20, ge=1, le=100),
                       offset: int = Query(0, ge=0),
                       status: Optional[Literal["calculated", "failed"]] = None):
        items, total = repository.list(limit, offset, status)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/v1/events", summary="Eventos recientes (solo exploración local)")
    def list_events():
        return list(publisher.recent)

    return app


app = create_app(rabbitmq_url=os.environ.get("RABBITMQ_URL"))
