from agent import AgentContext
from helpers.api import ApiHandler, Request, Response
from helpers.persist_chat import save_tmp_chat
from helpers.state_monitor_integration import mark_dirty_for_context
from usr.plugins.a0_reasoning_effort.helpers.reasoning_effort import (
    CONTEXT_KEY,
    get_discovered_state,
    is_zai_glm53,
    normalize_effort,
)


class ReasoningEffort(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        context_id = str(input.get("context_id") or "").strip()
        action = str(input.get("action") or "get").strip().lower()
        if not context_id:
            return Response(status=400, response="Missing context_id")

        context = AgentContext.get(context_id)
        if not context:
            return Response(status=404, response="Context not found")
        if action == "get":
            return await get_discovered_state(context.agent0)
        if action != "set":
            return Response(status=400, response=f"Unknown action: {action}")
        if context.is_running():
            return Response(
                status=409,
                response="Reasoning effort can be changed after the current run finishes.",
            )

        raw_effort = str(input.get("effort") or "").strip()
        effort = normalize_effort(raw_effort)
        if raw_effort and not effort:
            return Response(
                status=400,
                response="Reasoning effort must be 1-64 letters, digits, dots, underscores, or hyphens.",
            )

        state = await get_discovered_state(context.agent0)
        if effort and state["support"] == "unsupported":
            return Response(status=400, response="This model does not support reasoning effort.")
        allowed = {option["value"] for option in state["options"]}
        if (
            effort
            and is_zai_glm53(state["model"]["provider"], state["model"]["name"])
            and effort not in allowed
        ):
            return Response(status=400, response=f"Unsupported reasoning effort: {effort}")
        if effort and effort not in allowed and input.get("custom") is not True:
            return Response(status=400, response=f"Unsupported reasoning effort: {effort}")

        context.set_data(
            CONTEXT_KEY,
            {"model": state["model"]["key"], "effort": effort} if effort else None,
        )
        save_tmp_chat(context)
        mark_dirty_for_context(context.id, reason="reasoning_effort_change")
        return {"ok": True, **await get_discovered_state(context.agent0)}
