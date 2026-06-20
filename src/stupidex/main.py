import os
import sys

from stupidex.app import Stupidex
from stupidex.config import ConfigManager


def main():
    ConfigManager.ensure_home_config()
    ConfigManager.load()
    errors = ConfigManager.errors()
    if errors:
        print("STUPIDEX CONFIGURATION ERRORS:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print(file=sys.stderr)
        print("Fix the errors in ~/.stupidex/config.json or .stupidex.json and try again.", file=sys.stderr)
        sys.exit(1)
    app = Stupidex()
    app.run()
    if app.restart_requested:
        os.execv(sys.executable, [sys.executable, *sys.argv])


if __name__ == "__main__":
    main()
