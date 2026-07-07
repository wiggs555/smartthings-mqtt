"""CLI entry points."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from smartthings_mqtt.config import Settings, expand_path
from smartthings_mqtt.daemon import run_daemon
from smartthings_mqtt.local.relay import main as relay_main


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def main(argv: list[str] | None = None) -> None:
    """Main CLI: daemon or relay subcommand."""
    parser = argparse.ArgumentParser(prog="smartthings-mqtt")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the MQTT bridge daemon (default)")
    run_parser.set_defaults(command="run")

    subparsers.add_parser("relay", help="Run VLAN TV relay proxy")

    args, remaining = parser.parse_known_args(argv)

    if args.command is None:
        args.command = "run"

    if args.command == "relay":
        sys.argv = ["smartthings-mqtt-relay", *remaining]
        relay_main()
        return

    settings = Settings()  # type: ignore[call-arg]
    _setup_logging(settings.log_level)
    settings.local_token_dir = expand_path(settings.local_token_dir)
    settings.devices_config = expand_path(settings.devices_config)
    asyncio.run(run_daemon(settings))


if __name__ == "__main__":
    main()
