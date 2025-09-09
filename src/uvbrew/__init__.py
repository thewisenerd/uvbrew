import logging
import sys

import structlog

from uvbrew.uvbrew import cli

def main() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
    )
    structlog.stdlib.recreate_defaults(log_level=None)
    cli()
