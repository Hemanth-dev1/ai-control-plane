"""Configuration for the tool gateway service."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "tool-gateway"
    host: str = "0.0.0.0"
    port: int = 8002
    log_level: str = "INFO"

    # Backend service URLs
    crm_service_url: str = "http://crm-service:8003"
    ticketing_service_url: str = "http://ticketing-service:8004"
    notification_service_url: str = "http://notification-service:8005"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    # OpenTelemetry
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    # Control plane (for policy checks)
    control_plane_url: str = "http://control-plane:8000"


settings = Settings()
