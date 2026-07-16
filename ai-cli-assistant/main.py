#!/usr/bin/env python3
"""Run without installing: `python main.py "your prompt"` or `python main.py` for the REPL."""
import sys

from ai_cli.cli import main

if __name__ == "__main__":
    sys.exit(main())
