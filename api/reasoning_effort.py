from agent import AgentContext
from helpers.api import ApiHandler, Request, Response
from helpers.persist_chat import save_tmp_chat
from helpers.state_monitor_integration import mark_dirty_for_context
from usr.plugins.a0_reasoning_effort.helpers.reasoning_effort import CONTEXT_KEY, get_state


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
            return get_state(context.agent0)
        if action != "set":
            return Response(status=400, response=f"Unknown action: {action}")
        if context.is_running():
            return Response(
                status=409,
                response="Reasoning effort can be changed after the current run finishes.",
            )

        effort = str(input.get("effort") or "").strip().lower()
        state = get_state(context.agent0)
        allowed = {option["value"] for option in state["options"]}
        if effort and effort not in allowed:
            return Response(status=400, response=f"Unsupported reasoning effort: {effort}")

        context.set_data(
            CONTEXT_KEY,
            {"model": state["model"]["key"], "effort": effort} if effort else None,
        )
        save_tmp_chat(context)
        mark_dirty_for_context(context.id, reason="reasoning_effort_change")
        return {"ok": True, **get_state(context.agent0)}
