import os
from dataclasses import dataclass, field


@dataclass
class WeComConfig:
    corpid: str = field(default_factory=lambda: os.getenv("WECOM_CORPID", ""))
    corpsecret: str = field(default_factory=lambda: os.getenv("WECOM_CORPSECRET", ""))
    agentid: int = int(os.getenv("WECOM_AGENTID", "0"))
    token: str = field(default_factory=lambda: os.getenv("WECOM_TOKEN", ""))
    encoding_aes_key: str = field(default_factory=lambda: os.getenv("WECOM_ENCODING_AES_KEY", ""))

    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"))
    system_prompt: str = field(default_factory=lambda: os.getenv(
        "WECOM_SYSTEM_PROMPT",
        "你是一个企业微信群助手，请用简洁专业的中文回答问题。"
    ))

    host: str = field(default_factory=lambda: os.getenv("WECOM_HOST", "0.0.0.0"))
    port: int = int(os.getenv("WECOM_PORT", "8080"))
