# OpenAI Tool-Calling Agent

## Files
| File | Purpose |
|---|---|
| `config.py` | All LLM parameters + agent settings (editable) |
| `tools.py` | Tool definitions (`@tool` decorator auto-builds the schema) |
| `agent.py` | Agent loop, token tracking, `reset()` |
| `main.py` | Interactive CLI |

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env      # then put your real OPENAI_API_KEY in .env
python main.py
```

## Usage
Each line you type is a task. The agent calls tools as needed, then prints the answer plus token usage
(input / output / total for that message, and running totals for the chat).

Commands: `/reset`, `/params`, `/set <name> <value>`, `/tools`, `/help`, `/quit`

Examples:
```
/set temperature 0.2
/set model gpt-4o
/set max_tokens 500
/set stop null
you> Write the result of (123*45)+7 into result.txt, then read it back to me
```

## Adding a tool
In `tools.py`:
```python
@tool
def word_count(text: str) -> str:
    """Count the words in a piece of text."""
    return str(len(text.split()))
```
Use type hints (`str`, `int`, `float`, `bool`) and a docstring; it is picked up automatically.

## Notes
- Parameters set to `None` are not sent, so the API default is used.
- `temperature`, `top_p`, penalties and `seed` are rejected by some reasoning models (o-series / gpt-5);
  set them to `null` and use `reasoning_effort` instead.
- File tools only touch the `workspace/` folder.
