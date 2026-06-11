from stupidex.agents import load_agents
from stupidex.app import Stupidex
from stupidex.config import ConfigManager


def main():
    ConfigManager.ensure_home_config()
    load_agents()
    app = Stupidex()
    app.run()


if __name__ == "__main__":
    main()
