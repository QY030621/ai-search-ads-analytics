"""Keep the regression suite offline even after real credentials are configured."""
import pytest
from src import api_config

@pytest.fixture(autouse=True)
def isolate_api_credentials(monkeypatch,tmp_path):
    for name in ('AI_API_KEY','AI_BASE_URL','AI_MODEL'):
        monkeypatch.delenv(name,raising=False)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.delenv('OPENAI_MODEL',raising=False)
    monkeypatch.setattr(api_config,'SECRETS_PATH',tmp_path/'not-configured.toml')
