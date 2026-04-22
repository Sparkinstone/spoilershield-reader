import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_ping(client):
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_txt(client, tmp_path):
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("Para one.\n\nPara two.\n\nPara three.")
    with open(str(txt_file), "rb") as f:
        response = client.post("/upload", files={"file": ("test.txt", f, "text/plain")}, data={"title": "Test Book"})
    assert response.status_code == 200
    data = response.json()
    assert "book_id" in data
    assert data["total_paragraphs"] == 3
