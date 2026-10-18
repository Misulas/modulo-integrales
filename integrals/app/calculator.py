import multiprocessing as mp # Un proceso hijo es el que va a calcular la integral
from typing import Any, Callable

TIMEOUT_SECONDS = 10.0

_ctx = mp.get_context("forkserver")
_ctx.set_forkserver_preload(["sympy", "sympy.parsing.latex"])


def _failure(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


def compute(latex: str) -> dict[str, Any]:
    from sympy import E, Integral, Symbol, pi
    from sympy.parsing.latex import parse_latex

    try:
        expression = parse_latex(latex)
    except Exception:
        return _failure("LATEX_INVALID", "No se pudo interpretar el LaTeX.")

    integrals = expression.atoms(Integral)
    if not integrals:
        return _failure("NOT_AN_INTEGRAL", "El texto no contiene una integral (\\int).")

    # Esto es un mini fix para cuando se utiliza e y pi
    variables = {v for item in integrals for v in item.variables}
    constants = {Symbol(name): value for name, value in (("e", E), ("pi", pi))
                 if Symbol(name) not in variables}
    expression = expression.xreplace(constants)
    integrals = expression.atoms(Integral)

    try:
        value = expression.doit()
    except Exception:
        return _failure("UNSOLVABLE", "No se pudo resolver la integral.")
    if value.has(Integral):
        return _failure("UNSOLVABLE", "No se pudo resolver la integral.")

    indefinite = any(len(limit) == 1 for item in integrals for limit in item.limits)
    numeric = None
    if not value.free_symbols:
        try:
            approx = value.evalf()
            if approx.is_real and approx.is_finite:
                numeric = float(approx)
        except Exception:
            numeric = None
    from sympy import latex as to_latex
    return {"ok": True, "result": {"latex": to_latex(value), "numeric": numeric,
                                   "indefinite": indefinite}}


def _worker(latex: str, connection) -> None:
    try:
        connection.send(compute(latex))
    finally:
        connection.close()


def calculate(latex: str, timeout: float = TIMEOUT_SECONDS,
              worker: Callable = _worker) -> dict[str, Any]:
    """Devuelve `{"ok": True, "result": {...}}` o `{"ok": False, "error": {...}}`."""
    receiver, sender = _ctx.Pipe(duplex=False)
    process = _ctx.Process(target=worker, args=(latex, sender), daemon=True)
    process.start()
    sender.close()
    try:
        if receiver.poll(timeout):
            try:
                return receiver.recv()
            except EOFError:
                return _failure("UNSOLVABLE", "El cálculo terminó de forma inesperada.")
        return _failure("TIMEOUT", f"El cálculo superó {timeout:g} s.")
    finally:
        receiver.close()
        if process.is_alive():
            process.kill()
        process.join(1)
