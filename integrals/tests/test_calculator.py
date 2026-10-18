import time

import pytest

from app.calculator import calculate


@pytest.mark.parametrize("latex, expected, indefinite", [
    (r"\int x^2 dx", "\\frac{x^{3}}{3}", True),
    (r"\int_0^1 x^2 \, dx", "\\frac{1}{3}", False),
    (r"\int_0^\infty e^{-x} dx", "1", False),
    (r"\int_0^1 \int_0^1 xy \, dx \, dy", "\\frac{1}{4}", False),
    (r"\int_0^\pi \sin(x) dx", "2", False),
    (r"\int_{-\infty}^{\infty} e^{-x^2} dx", "\\sqrt{\\pi}", False),
])
def test_calcula_integrales(latex, expected, indefinite):
    outcome = calculate(latex)
    assert outcome["ok"], outcome
    assert outcome["result"]["latex"] == expected
    assert outcome["result"]["indefinite"] is indefinite


def test_valor_numerico_solo_sin_simbolos_libres():
    assert calculate(r"\int_0^1 x^2 dx")["result"]["numeric"] == pytest.approx(1 / 3)
    assert calculate(r"\int x^2 dx")["result"]["numeric"] is None


def test_latex_invalido():
    assert calculate(r"\int_0^ \frac{")["error"]["code"] == "LATEX_INVALID"


def test_integral_sin_solucion():
    assert calculate(r"\int_0^1 \sin(x^x) dx")["error"]["code"] == "UNSOLVABLE"


def test_sin_integral():
    assert calculate(r"x^2 + 1")["error"]["code"] == "NOT_AN_INTEGRAL"


def _slow_worker(latex, connection):
    time.sleep(30)


def test_timeout_termina_el_proceso():
    started = time.time()
    outcome = calculate("x", timeout=0.5, worker=_slow_worker)
    assert outcome["error"]["code"] == "TIMEOUT"
    assert time.time() - started < 5
