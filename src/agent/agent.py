"""The agent: runs a task by looping LLM call -> tool calls -> LLM call until a final answer."""
from dataclasses import dataclass, field

from openai import OpenAI

import src.agent.tools as tools 
from src.agent.config import Config


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

    def add(self, other: "Usage"):
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens
        self.cached_tokens += other.cached_tokens


@dataclass
class Result:
    output: str
    usage: Usage                                  # tokens used for this message (all steps combined)
    steps: int = 0                                # number of LLM calls made
    tools_used: list = field(default_factory=list)


class Agent:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.client = OpenAI()  # reads OPENAI_API_KEY from the environment
        self.reset()

    def reset(self):
        """Start a fresh context window (and fresh usage totals)."""
        self.messages = [{"role": "system", "content": self.config.system_prompt}]
        self.chat_usage = Usage()

    def run(self, task: str) -> Result:
        self.messages[0]["content"] = self.config.system_prompt  # pick up prompt edits
        self.messages.append({"role": "user", "content": task})
        usage, used = Usage(), []

        for step in range(1, self.config.max_steps + 1):
            kwargs = self.config.api_params()
            schemas = tools.get_schemas()
            if schemas:
                kwargs.update(tools=schemas, tool_choice=self.config.tool_choice,
                              parallel_tool_calls=self.config.parallel_tool_calls)

            resp = self.client.chat.completions.create(model=kwargs.pop("model"),
                                                       messages=self.messages, **kwargs)
            details = getattr(resp.usage, "prompt_tokens_details", None)
            cached_tokens = getattr(details, "cached_tokens", 0) or 0
            usage.add(Usage(resp.usage.prompt_tokens, resp.usage.completion_tokens,
                            resp.usage.total_tokens, cached_tokens))

            msg = resp.choices[0].message
            entry = {"role": "assistant", "content": msg.content}
            if msg.tool_calls:
                entry["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
            self.messages.append(entry)

            if not msg.tool_calls:
                return self._finish(msg.content or "", usage, step, used)

            for tc in msg.tool_calls:
                used.append(tc.function.name)
                result = tools.call_tool(tc.function.name, tc.function.arguments)
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        return self._finish(f"Stopped: reached max_steps ({self.config.max_steps}).",
                            usage, self.config.max_steps, used)

    def _finish(self, output, usage, steps, used) -> Result:
        self.chat_usage.add(usage)
        return Result(output, usage, steps, used)
