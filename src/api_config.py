"""Local API configuration; never expose secrets in messages or logs."""
import os
from pathlib import Path
import tomllib
from urllib.parse import urlsplit

SECRETS_PATH = Path(__file__).resolve().parents[1] / '.streamlit' / 'secrets.toml'


def load_api_config():
    local = {}
    try:
        if SECRETS_PATH.is_file():
            with SECRETS_PATH.open('rb') as stream:
                local = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError):
        return '', '', '', '本地API配置文件不可读取或格式无效；继续使用备用建议。'
    model = os.getenv('AI_MODEL') or local.get('AI_MODEL') or os.getenv('OPENAI_MODEL') or local.get('OPENAI_MODEL', '')
    key = os.getenv('AI_API_KEY') or local.get('AI_API_KEY') or os.getenv('OPENAI_API_KEY') or local.get('OPENAI_API_KEY', '')
    base_url = os.getenv('AI_BASE_URL') or local.get('AI_BASE_URL') or 'https://api.openai.com/v1'
    if not all(isinstance(value, str) for value in (model, key, base_url)):
        return '', '', '', 'API配置必须为字符串；继续使用备用建议。'
    base_url = base_url.strip().rstrip('/')
    parsed = urlsplit(base_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return '', '', '', 'AI_BASE_URL 必须是无凭据、无查询参数的 HTTPS 地址；继续使用备用建议。'
    return model.strip(), key.strip(), base_url, ''
