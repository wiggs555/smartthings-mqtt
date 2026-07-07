# SmartThings TV MQTT Daemon

Python daemon that auto-discovers Samsung TVs via SmartThings, exposes them as Home Assistant `media_player` entities through MQTT discovery, and supports local WebSocket control with VLAN proxy and Wake-on-LAN.

## Features

- Auto-discover Samsung TVs from SmartThings cloud API
- Home Assistant MQTT discovery (`media_player`)
- Hybrid control: local WebSocket (fast) with SmartThings cloud fallback
- Wake-on-LAN for power-on
- Built-in VLAN relay proxy for cross-subnet local control
- Per-TV overlay config for IP, MAC, and proxy settings

## Requirements

- Python 3.13+
- MQTT broker (e.g. Mosquitto)
- SmartThings [Personal Access Token](https://account.smartthings.com/tokens) with `r:devices:*` and `x:devices:*`

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# Edit .env with SMARTTHINGS_TOKEN and MQTT_HOST

cp config/devices.yaml.example config/devices.yaml
# Add your TV device_id, IP, and MAC

python -m smartthings_mqtt
```

## Configuration

### Environment (`.env`)

| Variable | Description |
|---|---|
| `SMARTTHINGS_TOKEN` | SmartThings PAT (required) |
| `MQTT_HOST` | MQTT broker hostname |
| `MQTT_PORT` | Default `1883` |
| `DEVICES_CONFIG` | Path to devices overlay YAML |
| `POLL_INTERVAL_SECONDS` | Status poll interval (default 15) |

See [`.env.example`](.env.example) for all options.

### Per-TV overlay (`config/devices.yaml`)

Map SmartThings device IDs to local network details:

```yaml
devices:
  "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx":
    ip_address: "192.168.1.50"
    mac_address: "AA:BB:CC:DD:EE:FF"
    port: 8002
    name: "Living Room TV"
```

Find your device ID:

```bash
curl -H "Authorization: Bearer $SMARTTHINGS_TOKEN" \
  https://api.smartthings.com/v1/devices
```

### Cross-VLAN setup

See [docs/vlan-proxy.md](docs/vlan-proxy.md) for relay, nginx, Traefik, and router masquerading options.

## Commands

```bash
# Run daemon (default)
smartthings-mqtt
python -m smartthings_mqtt

# Run VLAN relay on TV subnet
smartthings-mqtt-relay --tv-host 192.168.2.116 --listen-port 8002 --wol-port 8080
```

## Docker

```bash
docker compose up -d
```

## MQTT Topics

Per TV (`smartthings/tv/{device_id}/`):

| Topic | Description |
|---|---|
| `state` | JSON state (power, volume, source) |
| `set` | Command topic |
| `availability` | `online` / `offline` |
| `source_list` | JSON array of inputs |
| `attributes` | Extra attributes (channel, transport) |

Discovery: `homeassistant/media_player/smartthings_tv_{device_id}/config`

## systemd

```ini
[Unit]
Description=SmartThings TV MQTT Bridge
After=network.target mosquitto.service

[Service]
Type=simple
User=smartthings
EnvironmentFile=/etc/smartthings-mqtt/env
ExecStart=/opt/smartthings-mqtt/.venv/bin/python -m smartthings_mqtt
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## License

MIT
