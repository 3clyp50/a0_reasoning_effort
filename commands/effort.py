from helpers.api import Response
from usr.plugins.a0_reasoning_effort.api.reasoning_effort import ReasoningEffort


async def run(payload):
    arguments = payload.get("arguments") or {}
    args = arguments.get("positional") or []
    custom = bool(args and args[0].lower() == "custom")
    if (
        arguments.get("flags")
        or len(args) > (2 if custom else 1)
        or (custom and len(args) != 2)
        or (args and not args[-1].strip())
    ):
        return _error("Usage: /effort [<level>|default|custom <value>]")

    request = {
        "context_id": (payload.get("context") or {}).get("context_id"),
        "action": "set" if args else "get",
    }
    if args:
        request.update(
            effort="" if not custom and args[0].lower() == "default" else args[-1],
            custom=custom,
        )
    state = await ReasoningEffort(None, None).process(request, None)
    if isinstance(state, Response):
        return _error(state.get_data(as_text=True))

    current = f"`{state['effective']}` ({state['source']})" if state["effective"] else "provider default"
    lines = [f"Model: `{state['model']['key']}`", f"Current effort: {current}"]
    if state["support"] == "unsupported":
        lines.append("This model does not support reasoning effort.")
    else:
        levels = ", ".join(f"`{option['value']}`" for option in state["options"])
        lines.append(f"Available levels: {levels}" if levels else "No advertised levels; use a supported custom value.")
    lines.append("Usage: `/effort <level>`, `/effort custom <value>`, `/effort default`.")
    if args:
        lines.append("Applies to the next model turn; in-flight requests are unchanged.")
    return {"text": "", "effects": [{
        "type": "show_markdown", "title": "Reasoning Effort", "content": "\n\n".join(lines),
    }]}


def _error(message):
    return {"text": "", "effects": [{"type": "toast", "level": "error", "message": message}]}
