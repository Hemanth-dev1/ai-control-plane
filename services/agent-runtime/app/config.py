"""Configuration for the agent runtime service."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "agent-runtime"
    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "INFO"

    # Control plane URL
    control_plane_url: str = "http://control-plane:8000"

    # Tool gateway URL
    tool_gateway_url: str = "http://tool-gateway:8002"

    # LLM API
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    # OpenTelemetry
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    # Agent credentials
    agent_client_id: str = "agent-runtime"
    agent_client_secret: str = "change-me-in-production"


settings = Settings()
