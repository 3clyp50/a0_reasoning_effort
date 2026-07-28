from helpers.extension import Extension
from usr.plugins.a0_reasoning_effort.helpers.reasoning_effort import get_override


class ReasoningEffortOverride(Extension):
    def execute(self, data: dict = {}, **kwargs):
        model = data.get("result")
        effort = get_override(self.agent) if self.agent and model else ""
        if effort and isinstance(getattr(model, "kwargs", None), dict):
            model.kwargs["reasoning_effort"] = effort
