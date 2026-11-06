"""LLM + agent settings. Every field can be edited at runtime with `/set <field> <value>`."""
import os
from dataclasses import dataclass, fields


@dataclass
class Config:
    # --- Sent to the OpenAI API (None = omit, let the API use its default) ---
    model: str = os.getenv("GPT_MODEL", "gpt-4o-mini")
    # temperature: float | None = 0.1        # 0-2, randomness
    top_p: float | None = None             # 0-1, nucleus sampling
    max_tokens: int | None = None          # cap on output tokens (max_completion_tokens)
    frequency_penalty: float | None = None # -2 to 2
    presence_penalty: float | None = None  # -2 to 2
    seed: int | None = None                # best-effort determinism
    stop: list | None = None               # e.g. ["END"]
    reasoning_effort: str | None = None    # "low"|"medium"|"high" (o-series / gpt-5 models only)
    tool_choice: str = "auto"              # "auto" | "none" | "required"
    parallel_tool_calls: bool = True

    # --- Agent-only settings (not sent to the API) ---
    max_steps: int = 10                    # max LLM calls per task (prevents endless loops)
    system_prompt: str = (
        "You are a helpful task-solving agent. Use the provided tools whenever they "
        "help you complete the task accurately. When done, give a clear final answer."
    )

    _AGENT_ONLY = ("max_steps", "system_prompt")

    def api_params(self) -> dict:
        """Parameters for the API call, skipping None values and agent-only fields."""
        skip = self._AGENT_ONLY + ("tool_choice", "parallel_tool_calls", "max_tokens")
        params = {f.name: getattr(self, f.name) for f in fields(self) if f.name not in skip}
        if self.max_tokens is not None:
            params["max_completion_tokens"] = self.max_tokens
        return {k: v for k, v in params.items() if v is not None}
