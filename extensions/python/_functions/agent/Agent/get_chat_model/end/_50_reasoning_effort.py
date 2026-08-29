from helpers.extension import Extension
from plugins._model_config.helpers.model_config import get_chat_model_config
from usr.plugins.a0_reasoning_effort.helpers.reasoning_effort import (
    get_override,
    is_zai_glm53,
    prepare_zai_glm53_kwargs,
)


class ReasoningEffortOverride(Extension):
    def execute(self, data: dict = {}, **kwargs):
        model = data.get("result")
        effort = get_override(self.agent) if self.agent and model else ""
        if effort and isinstance(getattr(model, "kwargs", None), dict):
            model.kwargs["reasoning_effort"] = effort
        if isinstance(getattr(model, "kwargs", None), dict) and self.agent:
            config = get_chat_model_config(self.agent)
            if is_zai_glm53(config.get("provider"), config.get("name")):
                prepare_zai_glm53_kwargs(model.kwargs)
