import pytest

from mcp_server import config, database


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Chaque test a sa propre base SQLite et son propre index ChromaDB."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "club.db")
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")
    database.init_db()
    return tmp_path
