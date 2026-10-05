from pathlib import Path

from dotenv import load_dotenv

from .agent import Agent


def ask_approval(path: str, diff: str) -> bool:
    print(f"\nProposed change to {path}:\n{diff or '(no changes)'}")
    return input("Apply this change? [y/N] ").strip().lower() in ("y", "yes")


def main():
    load_dotenv()
    agent = Agent(Path.cwd(), approve=ask_approval)
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
