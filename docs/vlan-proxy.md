# Cross-VLAN / Cross-Subnet Local TV Control

Samsung TVs reject WebSocket connections from hosts on a different subnet. This document covers three ways to get local control working when the daemon and TV are on separate VLANs.

## Topology

```
Daemon (VLAN A)  --->  Relay/Proxy (VLAN B)  --->  TV (VLAN B)
```

## Option 1: Built-in Relay (Recommended)

Deploy on any host on the TV's VLAN (Raspberry Pi, Docker on IoT network, etc.):

```bash
smartthings-mqtt-relay \
  --tv-host 192.168.2.116 \
  --listen-host 0.0.0.0 \
  --listen-port 8002 \
  --listen-port-alt 8001 \
  --wol-port 8080
```

Configure the daemon in `config/devices.yaml`:

```yaml
devices:
  "your-smartthings-device-id":
    ip_address: "192.168.2.116"
    mac_address: "AA:BB:CC:DD:EE:FF"
    local_proxy:
      host: "192.168.2.254"
      port: 8002
      wol_url: "http://192.168.2.254:8080/wol"
```

WOL magic packets do not cross VLANs. The relay sends WOL on the TV subnet when the daemon POSTs to `/wol`.

### Docker relay on IoT VLAN

```yaml
# docker-compose.relay.yml
services:
  tv-relay:
    image: smartthings-mqtt:latest
    command:
      - smartthings-mqtt-relay
      - --tv-host=192.168.2.116
      - --listen-host=0.0.0.0
      - --listen-port=8002
      - --wol-port=8080
    network_mode: host
```

## Option 2: nginx WebSocket Proxy

Install nginx on a host in the TV VLAN:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

upstream tv_ws {
    server 192.168.2.116:8002;
}

server {
    listen 8002;
    location / {
        proxy_pass https://tv_ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_ssl_verify off;
    }
}
```

Point `local_proxy.host` at the nginx server IP.

## Option 3: Traefik TCP Passthrough

```toml
# tv.toml
[tcp.routers.tv]
  entryPoints = ["ws2"]
  rule = "HostSNI(`*`)"
  service = "tv"

[tcp.services.tv.loadBalancer]
  [[tcp.services.tv.loadBalancer.servers]]
    address = "192.168.2.116:8002"
```

## Option 4: Router IP Masquerading

Advanced: configure NAT on your router so connections from the daemon appear to originate on the TV's subnet.

### UniFi

1. Create a NAT masquerade rule on the TV destination VLAN
2. Source: daemon IP or home VLAN subnet
3. Destination: TV IP or IoT VLAN
4. Some setups also require **Proxy ARP** on the router

### EdgeRouter

```bash
set nat source rule 100 description 'HA to TV masquerade'
set nat source rule 100 outbound-interface eth2
set nat source rule 100 source address 192.168.1.200
set nat source rule 100 destination address 192.168.2.116
set nat source rule 100 translation address masquerade
```

When using router masquerading without a proxy, set in `devices.yaml`:

```yaml
force_local: true
```

This skips the subnet check so the daemon connects directly to the TV IP.

## References

- [Home Assistant Samsung TV VLAN issue](https://github.com/home-assistant/core/issues/35049)
- [Traefik VLAN proxy write-up](https://realmenweardress.es/2022/04/vlans-and-samsung-tvs/)
- [HA community masquerading guide](https://community.home-assistant.io/t/samsung-tv-documentation-update/404435)
