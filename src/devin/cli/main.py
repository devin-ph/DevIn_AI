"""
DevIn CLI — Entry point.
"""

import sys
import asyncio
import logging

from devin.cli.renderer import console, print_banner
from devin.cli.loop import run_cli_async

# Force UTF-8 rendering on Windows terminals to prevent rich crashes
if hasattr(sys.stdout, 'reconfigure'):
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.WARNING, format="%(name)s | %(message)s")
logger = logging.getLogger("devin")

def main():
    """Entry point for the devin command."""
    try:
        asyncio.run(run_cli_async())
    except KeyboardInterrupt:
        console.print("\n  [devin.system]👋 Goodbye![/]\n")

if __name__ == "__main__":
    sys.exit(main())
