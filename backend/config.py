from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VENDOROPS_", env_file=Path(__file__).parent / ".env", extra="ignore"
    )
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    backend_url: str = "http://127.0.0.1:8000"
    request_timeout_seconds: float = Field(default=60, gt=0)
    data_dir: Path = Path(__file__).parent / "data"
    provider: Literal["fixture", "bedrock"] = "fixture"
    max_model_characters: int = Field(default=24000, gt=0)
    live_calls_enabled: bool = False
    live_send_enabled: bool = False
    aws_region: str = "us-east-1"
    aws_profile: str = ""
    bedrock_region: str = ""
    model_id: str = "amazon.nova-lite-v1:0"
    embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    ocr_provider: Literal["local", "textract", "disabled"] = "local"
    tesseract_command: str = "tesseract"
    ocr_page_timeout_seconds: int = Field(default=60, gt=0, le=300)
    operator: str = "demo-operator"
    recipient_allowlist: str = "reviewer@example.test"
    approved_monthly_budget_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    daily_model_calls: int = Field(default=50, ge=0)
    daily_ocr_jobs: int = Field(default=5, ge=0)
    daily_email_sends: int = Field(default=5, ge=0)
    max_document_pages: int = Field(default=20, gt=0)
    max_output_tokens: int = Field(default=2000, gt=0, le=4096)
    s3_bucket: str = ""
    sns_topic_arn: str = ""
    textract_role_arn: str = ""
    sqs_queue_url: str = ""
    ses_sender: str = ""
    storage_mode: Literal["local", "s3"] = "local"
    chroma_host: str = ""
    chroma_port: int = 8000
    vector_store: Literal["chroma", "sqlite"] = "chroma"


settings = Settings()
