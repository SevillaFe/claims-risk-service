import pytest
from fastapi.testclient import TestClient

from app import train
from app.model import MODEL_PATH


@pytest.fixture(scope="session")
def client():
    if not MODEL_PATH.exists():  # en CI no hay modelo: lo entrenamos antes de testear
        train.main()
    from app.main import app

    with TestClient(app) as c:  # el "with" dispara el lifespan (carga del modelo)
        yield c
