import sys
from pathlib import Path

import mongomock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.chat_adapter import ChatAdapter  # noqa: E402
from app.events import EventPublisher  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repository import IntegralRepository  # noqa: E402
from app.service import IntegralService  # noqa: E402


def fake_calculator(latex: str) -> dict:
    if "bad" in latex:
        return {"ok": False, "error": {"code": "LATEX_INVALID", "message": "No se pudo interpretar el LaTeX."}}
    return {"ok": True, "result": {"latex": "\\frac{1}{3}", "numeric": 1 / 3, "indefinite": False}}


@pytest.fixture
def repository():
    return IntegralRepository(mongomock.MongoClient().test)


@pytest.fixture
def publisher():
    return EventPublisher(url=None)


@pytest.fixture
def service(repository, publisher):
    return IntegralService(repository, publisher, calculator=fake_calculator)


@pytest.fixture
def chat(repository, service, monkeypatch):
    adapter = ChatAdapter(repository, service, "http://users", "http://messages",
                          retry_delay=0)
    adapter.sent = []
    monkeypatch.setattr("app.chat_adapter._post_json", lambda url, payload, timeout=3: (
        adapter.sent.append((url, payload)) or {"id": "bot-1"}))
    return adapter


@pytest.fixture
def app(repository, publisher, service, chat):
    return create_app(repository, publisher, service, chat)
