from fastapi.testclient import TestClient


TOKEN_INTEGRACION_FICTICIO = "I" * 43
TOKEN_BOT_FICTICIO = "B" * 43


def cliente_contabilidad(app):
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN_INTEGRACION_FICTICIO}"})
