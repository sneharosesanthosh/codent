from pathlib import Path

from dotenv import load_dotenv

from .agent import Agent


def main():
    load_dotenv()
    agent = Agent(Path.cwd())
    print(f"codent — working in {agent.root}. Type 'exit' to quit.")
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line in ("exit", "quit"):
            break
        if line:
            print(agent.turn(line))


if __name__ == "__main__":
    main()
