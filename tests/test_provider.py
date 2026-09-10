from src import api_config
from src.recommendations import fingerprint


def test_custom_provider_config_and_environment(tmp_path,monkeypatch):
    path=tmp_path/'secrets.toml'
    monkeypatch.setattr(api_config,'SECRETS_PATH',path)
    path.write_text('AI_API_KEY="test-only"\nAI_BASE_URL="https://api.deepseek.com/"\nAI_MODEL="deepseek-v4-flash"',encoding='utf-8')
    assert api_config.load_api_config()==('deepseek-v4-flash','test-only','https://api.deepseek.com','')
    monkeypatch.setenv('AI_MODEL','override')
    assert api_config.load_api_config()[0]=='override'
    monkeypatch.setenv('AI_BASE_URL','http://insecure.example')
    assert api_config.load_api_config()[3]


def test_provider_change_invalidates_cached_recommendations():
    assert fingerprint({},'model','https://api.deepseek.com')!=fingerprint({},'model','https://api.openai.com/v1')
