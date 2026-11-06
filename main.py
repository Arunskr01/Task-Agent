"""Interactive CLI. Run: python main.py"""
import json
from dataclasses import fields

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.agent.agent import Agent
from src.agent.config import Config

HELP = """Commands:
  /reset              start a fresh chat (clears context + usage totals)
  /params             show current LLM settings
  /set <name> <value> change a setting, e.g. /set temperature 0.2 | /set model gpt-4o | /set stop null
  /tools              list available tools
  /help               show this help
  /quit               exit
Anything else is sent to the agent as a task."""


def parse_value(raw: str):
    try:
        return json.loads(raw)       # numbers, true/false, null, lists, quoted strings
    except json.JSONDecodeError:
        return raw                   # plain text (e.g. model names, system prompt)


def handle_command(agent: Agent, line: str) -> bool:
    """Returns False to quit."""
    cmd, _, rest = line.partition(" ")
    if cmd == "/quit":
        return False
    if cmd == "/reset":
        agent.reset()
        print("Chat reset. Fresh context started.")
    elif cmd == "/params":
        for f in fields(agent.config):
            print(f"  {f.name} = {getattr(agent.config, f.name)!r}")
    elif cmd == "/set":
        name, _, raw = rest.partition(" ")
        if name not in {f.name for f in fields(agent.config)} or not raw:
            print("Usage: /set <name> <value>  (see /params for names)")
        else:
            setattr(agent.config, name, parse_value(raw.strip()))
            print(f"{name} = {getattr(agent.config, name)!r}")
    elif cmd == "/tools":
        import src.agent.tools as tools
        for s in tools.get_schemas():
            print(f"  {s['function']['name']}: {s['function']['description']}")
    else:
        print(HELP)
    return True


def main():
    agent = Agent(Config())
    print("Agent ready. Type a task, or /help for commands.\n")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line.startswith("/"):
            if not handle_command(agent, line):
                break
            continue
        try:
            r = agent.run(line)
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}")
            continue
        print(f"\nagent> {r.output}\n")
        tools_str = ", ".join(r.tools_used) or "none"
        print(f"[tokens] input={r.usage.input_tokens} output={r.usage.output_tokens} "
              f"total={r.usage.total_tokens} | steps={r.steps} | tools: {tools_str}")
        c = agent.chat_usage
        print(f"[chat total] input={c.input_tokens} output={c.output_tokens} total={c.total_tokens}\n")


if __name__ == "__main__":
    main()
