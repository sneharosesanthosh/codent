import os
from pathlib import Path

import anthropic

from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, run_tool

MAX_ITERATIONS = 20


class Agent:
    def __init__(self, root: Path, client=None, model: str | None = None, approve=None):
        self.root = root.resolve()
        self.approve = approve  # approve(path, diff) -> bool; None means deny all writes
        self.client = client or anthropic.Anthropic()
        self.model = model or os.getenv("CODENT_MODEL", "claude-sonnet-5-5")
        self.messages: list[dict] = []

    def turn(self, user_input: str) -> str:
        """Run one user turn through the tool loop; return the final text."""
        self.messages.append({"role": "user", "content": user_input})
        for _ in range(MAX_ITERATIONS):
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOL_SCHEMAS,
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                return "".join(b.text for b in resp.content if b.type == "text")

            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    print(f"  [tool] {block.name}({block.input})")
                    output, is_error = run_tool(self.root, block.name, block.input, self.approve)
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": output,
                            "is_error": is_error,
                        }
                    )
            self.messages.append({"role": "user", "content": results})
        return "(stopped: too many tool iterations)"
