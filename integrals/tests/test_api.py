from fastapi.testclient import TestClient


def client(app):
    return TestClient(app)


def test_crear_y_consultar(app):
    c = client(app)
    created = c.post("/api/v1/integrals", json={"latex": r"\int_0^1 x^2 dx"})
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "calculated"
    assert body["source"]["kind"] == "rest"
    assert c.get(f"/api/v1/integrals/{body['id']}").json()["id"] == body["id"]


def test_fallo_de_calculo_no_es_error_http(app):
    response = client(app).post("/api/v1/integrals", json={"latex": "bad"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "LATEX_INVALID"
    assert body["result"] is None


def test_validacion_de_forma(app):
    for payload in ({"latex": "   "}, {"latex": "x" * 1001}, {}):
        response = client(app).post("/api/v1/integrals", json=payload)
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"


def test_no_encontrada(app):
    response = client(app).get("/api/v1/integrals/inexistente")
    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND", "message": "Integral not found"}


def test_historial_paginado_y_filtro(app):
    c = client(app)
    for latex in ("a", "b", "bad"):
        c.post("/api/v1/integrals", json={"latex": latex})
    page = c.get("/api/v1/integrals", params={"limit": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    failed = c.get("/api/v1/integrals", params={"status": "failed"}).json()
    assert failed["total"] == 1
    assert c.get("/api/v1/integrals", params={"limit": 0}).status_code == 422


def test_correlation_id(app):
    c = client(app)
    assert c.get("/health", headers={"X-Correlation-ID": "abc"}).headers["X-Correlation-ID"] == "abc"
    assert c.get("/health").headers["X-Correlation-ID"]
