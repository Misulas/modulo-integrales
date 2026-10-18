import json
import logging
import re
import time
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5

from .logging_conf import correlation_id
from .repository import DuplicateIntegral, IntegralRepository
from .schemas import Source
from .service import IntegralService

log = logging.getLogger("integrals.chat")

BOT_NAME = "integralbot"
MAX_REPLY = 4_000
USAGE = "Uso: /integralcalc <latex>. Ejemplo: /integralcalc \\int_0^1 x^2 \\, dx"
COMMAND = re.compile(r"^/(?:integralcalc|integral)(?=\s|$)\s*(.*)$", re.DOTALL)


def parse_command(content: Any) -> Optional[str]:
    """Devuelve el LaTeX del comando, "" si falta, o None si no es un comando."""
    if not isinstance(content, str):
        return None
    match = COMMAND.match(content.strip())
    if match is None:
        return None
    latex = match.group(1).strip()
    if len(latex) >= 2 and latex.startswith("$") and latex.endswith("$"):
        latex = latex.strip("$").strip()
    return latex


def format_reply(integral: dict[str, Any]) -> str:
    if integral["status"] == "failed":
        text = f"No pude calcular la integral: {integral['error']['message']}"
    else:
        result = integral["result"]
        text = f"{integral['latex']} = {result['latex']}"
        if result["indefinite"]:
            text += " + C"
        if result["numeric"] is not None:
            text += f" ≈ {result['numeric']:.10g}"
    return text[:MAX_REPLY]


def _post_json(url: str, payload: dict[str, Any], timeout: float = 3) -> dict[str, Any]:
    request = Request(url, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json",
                               "X-Correlation-ID": correlation_id.get() or ""},
                      method="POST")
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


class ChatAdapter:
    def __init__(self, repository: IntegralRepository, service: IntegralService,
                 users_url: str, messages_url: str, retry_delay: float = 1.0):
        self.repository = repository
        self.service = service
        self.users_url = users_url
        self.messages_url = messages_url
        self.retry_delay = retry_delay

    def ensure_bot_id(self) -> str:
        """Crea el bot una sola vez: `users` no permite buscar por nombre."""
        bot_id = self.repository.get_bot_id()
        if bot_id is None:
            bot_id = _post_json(f"{self.users_url}/api/v1/users",
                                {"display_name": BOT_NAME})["id"]
            self.repository.set_bot_id(bot_id)
            log.info("bot_created", extra={"fields": {"bot_id": bot_id}})
        return bot_id

    def handle_event(self, event: dict[str, Any]) -> None:
        data = event.get("data") or {}
        latex = parse_command(data.get("content"))
        if latex is None or not data.get("id") or not data.get("channel_id"):
            return
        if data.get("author_id") == self.ensure_bot_id():
            return
        correlation_id.set(data["id"])
        channel_id = data["channel_id"]
        if latex == "":
            self._reply(channel_id, USAGE)
            return

        integral_id = str(uuid5(NAMESPACE_URL, f"chat-message:{data['id']}"))
        if self.repository.get(integral_id) is not None:
            log.info("duplicate_message", extra={"fields": {"message_id": data["id"]}})
            return
        source = Source(kind="chat", channel_id=channel_id,
                        author_id=data.get("author_id"), message_id=data["id"])
        try:
            integral = self.service.process(latex, source, integral_id)
        except DuplicateIntegral:
            return
        self._reply(channel_id, format_reply(integral))

    def _reply(self, channel_id: str, content: str) -> None:
        url = f"{self.messages_url}/api/v1/channels/{channel_id}/messages"
        for attempt in range(3):
            try:
                _post_json(url, {"author_id": self.ensure_bot_id(), "content": content})
                return
            except (URLError, OSError, ValueError):
                log.warning("reply_retry", extra={"fields": {"attempt": attempt + 1}})
                time.sleep(self.retry_delay * (attempt + 1))
        log.error("reply_failed", extra={"fields": {"channel_id": channel_id}})
