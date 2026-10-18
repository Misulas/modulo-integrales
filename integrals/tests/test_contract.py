"""Pruebas de contrato: detectan cambios que rompen la interfaz pública."""
from fastapi.testclient import TestClient


def test_rutas_y_metodos_publicados(app):
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    assert "post" in paths["/api/v1/integrals"]
    assert "get" in paths["/api/v1/integrals"]
    assert "get" in paths["/api/v1/integrals/{integral_id}"]
    assert "get" in paths["/health"]


def test_campos_de_integral_no_se_eliminan(app):
    schema = TestClient(app).get("/openapi.json").json()["components"]["schemas"]["Integral"]
    required_by_v1 = {"id", "latex", "status", "result", "error", "source",
                      "duration_ms", "created_at"}
    assert required_by_v1 <= set(schema["properties"])


def test_version_semantica(app):
    version = TestClient(app).get("/openapi.json").json()["info"]["version"]
    assert [part.isdigit() for part in version.split(".")] == [True] * 3


def test_evento_cumple_convencion_y_sobre(app):
    c = TestClient(app)
    integral = c.post("/api/v1/integrals", json={"latex": "x"}).json()
    event = c.get("/api/v1/events").json()[-1]
    assert event["type"] == f"integral.{integral['id']}.calculated"
    assert {"type", "subject_id", "occurred_at", "schema_version",
            "correlation_id", "data"} <= set(event)
    assert event["data"]["id"] == integral["id"]
