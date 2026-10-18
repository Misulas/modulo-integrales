"""Publicación y consumo de eventos en RabbitMQ."""
import json
import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Optional

import pika

log = logging.getLogger("integrals.events")

EXCHANGE = "integrals"
CHAT_EXCHANGE = "chat"
CHAT_ROUTING_KEY = "chat.message.created"
CHAT_QUEUE = "integrals.chat-commands"


class EventPublisher:
    """
    Publica en el exchange `integrals` con llave de ruteo `integral.<id>.<acción>`.
    """

    def __init__(self, url: Optional[str]):
        self.url = url
        self.recent: deque[dict[str, Any]] = deque(maxlen=100)

    def publish(self, routing_key: str, event: dict[str, Any]) -> None:
        self.recent.append(event)
        if not self.url:
            return
        for attempt in range(3):
            try:
                connection = pika.BlockingConnection(pika.URLParameters(self.url))
                channel = connection.channel()
                channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic",
                                         durable=True)
                channel.basic_publish(
                    exchange=EXCHANGE, routing_key=routing_key,
                    body=json.dumps(event),
                    properties=pika.BasicProperties(content_type="application/json",
                                                    delivery_mode=2))
                connection.close()
                return
            except pika.exceptions.AMQPError:
                log.warning("event_publish_retry",
                            extra={"fields": {"routing_key": routing_key,
                                              "attempt": attempt + 1}})
                time.sleep(0.5 * (attempt + 1))
        log.error("event_publish_failed", extra={"fields": {"routing_key": routing_key}})


class ChatEventConsumer(threading.Thread):
    """
    Consume `chat.message.created` y reconecta si RabbitMQ se cae.
    """

    def __init__(self, url: str, handler: Callable[[dict[str, Any]], None],
                 prepare: Callable[[], None] = lambda: None):
        super().__init__(daemon=True, name="chat-consumer")
        self.url = url
        self.handler = handler
        self.prepare = prepare
        self._stop_requested = threading.Event()

    def stop(self) -> None:
        self._stop_requested.set()

    def run(self) -> None:
        while not self._stop_requested.is_set():
            try:
                self.prepare()
                self._consume()
            except Exception:
                log.exception("consumer_error")
                self._stop_requested.wait(5)

    def _consume(self) -> None:
        connection = pika.BlockingConnection(pika.URLParameters(self.url))
        try:
            channel = connection.channel()
            channel.exchange_declare(exchange=CHAT_EXCHANGE, exchange_type="topic")
            channel.queue_declare(queue=CHAT_QUEUE, durable=True)
            channel.queue_bind(queue=CHAT_QUEUE, exchange=CHAT_EXCHANGE,
                               routing_key=CHAT_ROUTING_KEY)
            channel.basic_qos(prefetch_count=1)
            log.info("consumer_ready")
            for method, _, body in channel.consume(CHAT_QUEUE, inactivity_timeout=1):
                if self._stop_requested.is_set():
                    break
                if method is None:
                    continue
                try:
                    self.handler(json.loads(body))
                    channel.basic_ack(method.delivery_tag)
                except Exception:
                    log.exception("message_handling_failed")
                    channel.basic_nack(method.delivery_tag, requeue=not method.redelivered)
        finally:
            if connection.is_open:
                connection.close()
