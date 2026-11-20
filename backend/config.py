from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VENDOROPS_", env_file=".env", extra="ignore")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    backend_url: str = "http://127.0.0.1:8000"
    request_timeout_seconds: float = Field(default=60, gt=0)
    data_dir: Path = Path("data")
    provider: str = "fixture"
    max_model_characters: int = Field(default=24000, gt=0)
    live_calls_enabled: bool = False
    live_send_enabled: bool = False
    aws_region: str = "us-east-1"
    model_id: str = "us.amazon.nova-lite-v1:0"
    operator: str = "demo-operator"
    recipient_allowlist: str = "reviewer@example.test"


settings = Settings()
