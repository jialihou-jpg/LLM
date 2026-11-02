import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("MCP_HOST", "127.0.0.1")
    port: int = int(os.getenv("MCP_PORT", "8000"))
    pet_hospital_base_url: str = os.getenv("PET_HOSPITAL_BASE_URL", "http://127.0.0.1:8080")
    request_timeout: float = 10.0
    max_retries: int = 2
    default_page_size: int = 20


def get_settings() -> Settings:
    return Settings()
