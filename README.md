# SmartThings TV MQTT Daemon

Python daemon that auto-discovers Samsung TVs via SmartThings, exposes them in Home Assistant through native MQTT discovery (`switch`, `number`, `select` entities grouped per TV), and supports local WebSocket control with VLAN proxy and Wake-on-LAN.

## Features

- Auto-discover Samsung TVs from SmartThings cloud API
- Home Assistant MQTT discovery (power, volume, mute, and source entities per TV)
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
| `MQTT_HOST` | MQTT broker hostname (not a URL — use IP/hostname only) |
| `MQTT_PORT` | Default `1883` |
| `MQTT_CONNECT_TIMEOUT_SECONDS` | Broker connect timeout (default 30) |
| `MQTT_CONNECT_RETRY_SECONDS` | Retry interval when broker is unreachable (default 5) |
| `DEVICES_CONFIG` | Path to devices overlay YAML |
| `POLL_INTERVAL_SECONDS` | Status poll interval (default 15) |
| `OFF_ACTION` | What the Power OFF command does: `art_mode` (default, The Frame Art Mode) or `power_off` |

See [`.env.example`](.env.example) for all options.

### Home Assistant Mosquitto broker

Home Assistant's Mosquitto add-on **requires a username and password** — anonymous connections are rejected.

1. **Create MQTT credentials** (choose one):
   - **Settings → People → Users** — create a dedicated user (e.g. `smartthings_mqtt`)
   - **Settings → Add-ons → Mosquitto broker → Configuration** — add under `logins`:
     ```yaml
     logins:
       - username: smartthings_mqtt
         password: your-secure-password
     ```
2. Add to `.env`:
   ```bash
   MQTT_HOST=10.0.1.9
   MQTT_PORT=1883
   MQTT_USERNAME=smartthings_mqtt
   MQTT_PASSWORD=your-secure-password
   ```
3. Do **not** use the reserved usernames `homeassistant` or `addons`.

Test from the same machine running the daemon:

```bash
mosquitto_pub -h 10.0.1.9 -p 1883 -u smartthings_mqtt -P 'your-secure-password' -t test -m hello
```

### MQTT connection troubleshooting

The daemon must reach your MQTT broker over TCP before it starts. A `timed out` error usually means the broker is not reachable at `MQTT_HOST:MQTT_PORT`.

| How you run the daemon | Set `MQTT_HOST` to |
|---|---|
| On the same host as Mosquitto | `localhost` or `127.0.0.1` |
| In Docker Compose (this repo) | `mosquitto` (the service name) |
| On another machine, broker on Home Assistant | Your HA IP (e.g. `192.168.1.10`) |
| Home Assistant add-on broker | HA IP; enable MQTT in HA and check port `1883` |

Verify connectivity before starting:

```bash
nc -zv "$MQTT_HOST" 1883
# or
mosquitto_pub -h "$MQTT_HOST" -p 1883 -t test -m hello
```

The daemon now retries the connection every 5 seconds instead of exiting immediately when the broker is down.

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
| `power/state` | `ON` / `OFF` |
| `power/set` | Power command (`ON` = TV on, `OFF` = Art/Frame Mode by default) |
| `volume/state` | Volume `0`–`100` |
| `volume/set` | Volume command |
| `mute/state` | `ON` / `OFF` |
| `mute/set` | Mute command |
| `source/state` | Active input |
| `source/set` | Input select command |
| `availability` | `online` / `offline` |
| `attributes` | JSON extras (channel, transport) |

Discovery (one config topic per entity):

- `homeassistant/switch/smartthings_tv_{device_id}_power/config`
- `homeassistant/number/smartthings_tv_{device_id}_volume/config`
- `homeassistant/switch/smartthings_tv_{device_id}_mute/config`
- `homeassistant/select/smartthings_tv_{device_id}_source/config` (when inputs are known)

Home Assistant does **not** support native MQTT discovery for `media_player` entities ([core#152085](https://github.com/home-assistant/core/issues/152085)). This daemon publishes supported entity types instead.

### Nothing shows up in Home Assistant?

1. Confirm the daemon log shows `Discovered N TV(s)` with **N > 0** and `Registered TV:` lines.
2. Subscribe to discovery traffic from the daemon host:
   ```bash
   mosquitto_sub -h 10.0.1.9 -u smartthings_mqtt -P 'your-password' -t 'homeassistant/#' -v
   ```
3. In HA: **Settings → Devices & services → MQTT** — discovery must be enabled (default).
4. Restart the daemon after upgrading; old `media_player` discovery messages are ignored by HA.

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
