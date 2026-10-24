from helpers.extension import Extension
from usr.plugins.a0_reasoning_effort.helpers.reasoning_effort import get_discovered_state


class ReasoningEffortControl(Extension):
    async def execute(self, action, input, controls, result, **kwargs):
        if action == "set":
            if input.get("control_id") != "a0_reasoning_effort":
                return
            from usr.plugins.a0_reasoning_effort.api.reasoning_effort import ReasoningEffort

            response = await ReasoningEffort(None, None).process({
                "action": "set", "context_id": self.agent.context.id,
                "effort": input.get("value"), "custom": input.get("custom", False),
                "model_key": input.get("revision"),
            }, None)
            result["response"] = {"ok": True} if isinstance(response, dict) and response.get("ok") else response
            return

        state = await get_discovered_state(self.agent)
        options = state["options"]
        labels = {option["value"]: option["label"] for option in options}
        effective = state["effective"]
        if state["support"] == "unsupported":
            label = "Unsupported"
            description = "The provider reports no effort support."
        else:
            label = labels.get(effective, effective) if effective else ("Auto" if state["available"] else "Custom…")
            description = "No advertised values. Enter a supported custom value." if state["support"] == "unknown" else ""
        preset = state["preset_effort"]
        default = f"Use preset ({labels.get(preset, preset)})" if preset else "Use preset / provider default"
        controls.append({
            "id": "a0_reasoning_effort", "type": "choice",
            "label": f"Effort: {label}", "title": "Reasoning Effort",
            "value": state["selected"], "revision": state["model"]["key"],
            "options": [{"value": "", "label": default}, *options],
            "custom": state["support"] != "unsupported", "description": description,
        })
