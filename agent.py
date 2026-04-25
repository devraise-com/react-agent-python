"""Entry point: python agent.py"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so `src.*` imports resolve
sys.path.insert(0, str(Path(__file__).parent))

from src.agent.config import Settings
from src.cli.interface import AgentCLI


def main() -> None:
    settings = Settings()

    if not settings.openai_api_key:
        print(
            "Error: OPENAI_API_KEY is not set.\n"
            "Copy .env.example to .env and add your key.",
            file=sys.stderr,
        )
        sys.exit(1)

    AgentCLI(settings).run()


if __name__ == "__main__":
    main()
