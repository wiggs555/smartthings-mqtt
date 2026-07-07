"""Application configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LocalProxyConfig(BaseModel):
    """Proxy or relay on the TV VLAN for cross-subnet WebSocket access."""

    host: str
    port: int = 8002
    wol_url: str | None = None


class DeviceOverlay(BaseModel):
    """Per-TV local network overlay merged with SmartThings discovery."""

    ip_address: str
    mac_address: str | None = None
    port: int = 8002
    name: str | None = None
    local_proxy: LocalProxyConfig | None = None
    force_local: bool = False
    wol_broadcast: str | None = None


class Settings(BaseSettings):
    """Environment-backed daemon settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    smartthings_token: str = Field(alias="SMARTTHINGS_TOKEN")
    mqtt_host: str = Field(default="localhost", alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, alias="MQTT_PORT")
    mqtt_username: str | None = Field(default=None, alias="MQTT_USERNAME")
    mqtt_password: str | None = Field(default=None, alias="MQTT_PASSWORD")
    mqtt_topic_prefix: str = Field(default="smartthings/tv", alias="MQTT_TOPIC_PREFIX")
    mqtt_discovery_prefix: str = Field(
        default="homeassistant", alias="MQTT_DISCOVERY_PREFIX"
    )
    poll_interval_seconds: int = Field(default=15, alias="POLL_INTERVAL_SECONDS")
    device_rescan_interval_seconds: int = Field(
        default=300, alias="DEVICE_RESCAN_INTERVAL_SECONDS"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    local_enabled: bool = Field(default=True, alias="LOCAL_ENABLED")
    local_token_dir: Path = Field(
        default=Path.home() / ".smartthings-mqtt" / "tokens",
        alias="LOCAL_TOKEN_DIR",
    )
    devices_config: Path = Field(
        default=Path("config/devices.yaml"), alias="DEVICES_CONFIG"
    )
    wol_retries: int = Field(default=3, alias="WOL_RETRIES")
    wol_retry_interval_seconds: int = Field(default=5, alias="WOL_RETRY_INTERVAL_SECONDS")
    local_connect_timeout_seconds: int = Field(
        default=10, alias="LOCAL_CONNECT_TIMEOUT_SECONDS"
    )


def load_device_overlays(path: Path) -> dict[str, DeviceOverlay]:
    """Load per-TV overlay from YAML; missing file returns empty dict."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}
    devices = data.get("devices", {})
    return {device_id: DeviceOverlay.model_validate(cfg) for device_id, cfg in devices.items()}


def expand_path(path: Path) -> Path:
    """Expand user home in configured paths."""
    return path.expanduser().resolve()
