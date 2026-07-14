"""Configuration for the control plane service."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Service identity
    service_name: str = "control-plane"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://controlplane:controlplane@localhost:5432/controlplane"
    database_url_sync: str = "postgresql://controlplane:controlplane@localhost:5432/controlplane"

    # Redis (rate limiting)
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_seconds: int = 3600

    # OPA
    opa_url: str = "http://localhost:8181"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    # OpenTelemetry
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    # Admin credentials for initial setup
    admin_username: str = "admin"
    admin_password: str = "admin"


settings = Settings()
