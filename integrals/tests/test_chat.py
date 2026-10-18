import pytest

from app.chat_adapter import format_reply, parse_command


@pytest.mark.parametrize("content, expected", [
    (r"/integralcalc \int x dx", r"\int x dx"),
    (r"/integral \int x dx", r"\int x dx"),
    (r"/integralcalc $\int x dx$", r"\int x dx"),
    ("/integralcalc", ""),
    ("/integralcalcx foo", None),
    ("hola /integralcalc x", None),
    (None, None),
])
def test_parse_command(content, expected):
    assert parse_command(content) == expected


def event(content="/integralcalc \\int x dx", author="user-1", message_id="m-1"):
    return {"type": "chat.message.created", "data": {
        "id": message_id, "channel_id": "ch-1", "author_id": author, "content": content}}


def test_comando_calcula_responde_y_emite(chat, publisher, repository):
    chat.handle_event(event())
    replies = [p for url, p in chat.sent if url.endswith("/channels/ch-1/messages")]
    assert len(replies) == 1 and replies[0]["author_id"] == "bot-1"
    assert "\\frac{1}{3}" in replies[0]["content"]
    assert repository.list(10, 0)[1] == 1
    key = list(publisher.recent)[0]["type"]
    assert key.startswith("integral.") and key.endswith(".calculated")
    assert list(publisher.recent)[0]["correlation_id"] == "m-1"


def test_mensaje_duplicado_no_recalcula(chat, repository):
    chat.handle_event(event())
    chat.handle_event(event())
    assert repository.list(10, 0)[1] == 1


def test_ignora_mensajes_del_bot_y_otros(chat, repository):
    chat.handle_event(event())
    sent_before = len(chat.sent)
    chat.handle_event(event(author="bot-1", message_id="m-2"))
    chat.handle_event(event(content="hola", message_id="m-3"))
    assert len(chat.sent) == sent_before
    assert repository.list(10, 0)[1] == 1


def test_comando_sin_latex_responde_uso(chat, repository):
    chat.handle_event(event(content="/integralcalc"))
    assert "Uso:" in chat.sent[-1][1]["content"]
    assert repository.list(10, 0)[1] == 0


def test_fallo_se_informa_en_el_canal(chat):
    chat.handle_event(event(content="/integralcalc bad"))
    assert chat.sent[-1][1]["content"].startswith("No pude calcular")


def test_formato_indefinida():
    integral = {"status": "calculated", "latex": "x", "error": None,
                "result": {"latex": "y", "numeric": None, "indefinite": True}}
    assert format_reply(integral) == "x = y + C"
