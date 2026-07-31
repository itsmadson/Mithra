import pytest
from bina_api.config import Settings


def test_settings_reads_mapillary_token(monkeypatch):
    monkeypatch.setenv("MAPILLARY_TOKEN", "MLY|test|secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://bina:bina@localhost/bina")
    s = Settings()
    assert s.mapillary_token.get_secret_value() == "MLY|test|secret"


def test_settings_never_leaks_token_in_repr(monkeypatch):
    monkeypatch.setenv("MAPILLARY_TOKEN", "MLY|test|secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://bina:bina@localhost/bina")
    s = Settings()
    assert "secret" not in repr(s)


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("MAPILLARY_TOKEN", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://bina:bina@localhost/bina")
    # _env_file=None ignores the developer's real .env, which would otherwise
    # supply the token and make this assertion depend on whether the machine
    # running the tests happens to have credentials configured.
    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_token_must_have_the_mapillary_prefix(monkeypatch):
    monkeypatch.setenv("MAPILLARY_TOKEN", "not-a-mapillary-token")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://bina:bina@localhost/bina")
    with pytest.raises(Exception):
        Settings(_env_file=None)
