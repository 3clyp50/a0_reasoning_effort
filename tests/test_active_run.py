"""Run from the Agent Zero root against the installed plugin."""

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from usr.plugins.a0_reasoning_effort.api import reasoning_effort as api
from usr.plugins.a0_reasoning_effort.helpers import reasoning_effort as helper


class ActiveRunTest(unittest.IsolatedAsyncioTestCase):
    async def test_running_chat_accepts_changes_for_the_next_model_turn(self):
        data = {}
        context = SimpleNamespace(
            id="active-chat", is_running=lambda: True,
            get_data=data.get, set_data=lambda key, value: data.update({key: value}),
        )
        context.agent0 = SimpleNamespace(context=context)
        config = {"provider": "openai", "name": "o3", "kwargs": {"reasoning_effort": "medium"}}
        hook = importlib.import_module(
            "usr.plugins.a0_reasoning_effort.extensions.python._functions.agent.Agent.get_chat_model.end._50_reasoning_effort"
        )
        discover = AsyncMock(side_effect=lambda agent: helper.get_state(agent))
        handler = api.ReasoningEffort(None, None)
        extension = hook.ReasoningEffortOverride(context.agent0)
        current = SimpleNamespace(kwargs=dict(config["kwargs"]))
        with (
            patch.object(api.AgentContext, "get", return_value=context),
            patch.object(api, "get_discovered_state", discover),
            patch.object(api, "save_tmp_chat") as save,
            patch.object(api, "mark_dirty_for_context") as dirty,
            patch.object(helper, "get_chat_model_config", return_value=config),
            patch.object(helper, "_supported_efforts", return_value=("low", "medium", "high")),
            patch.object(hook, "get_chat_model_config", return_value=config),
        ):
            response = await handler.process({"action": "set", "context_id": context.id, "effort": "low"}, None)
            self.assertTrue(response["ok"])
            self.assertEqual(response["selected"], "low")
            self.assertEqual(data[helper.CONTEXT_KEY], {"model": "openai/o3", "effort": "low"})
            save.assert_called_once_with(context)
            dirty.assert_called_once_with(context.id, reason="reasoning_effort_change")
            self.assertEqual(current.kwargs["reasoning_effort"], "medium")
            next_turn = SimpleNamespace(kwargs=dict(config["kwargs"]))
            extension.execute({"result": next_turn})
            self.assertEqual(next_turn.kwargs["reasoning_effort"], "low")

            for effort in ("bad value", "max"):
                rejected = await handler.process({"action": "set", "context_id": context.id, "effort": effort}, None)
                self.assertEqual(rejected.status_code, 400)
                self.assertEqual(data[helper.CONTEXT_KEY]["effort"], "low")
            save.assert_called_once()
            cleared = await handler.process({"action": "set", "context_id": context.id, "effort": ""}, None)
            self.assertTrue(cleared["ok"])
            self.assertEqual(cleared["selected"], "")
            self.assertIsNone(data[helper.CONTEXT_KEY])
            next_turn = SimpleNamespace(kwargs=dict(config["kwargs"]))
            extension.execute({"result": next_turn})
            self.assertEqual(next_turn.kwargs["reasoning_effort"], "medium")


if __name__ == "__main__":
    unittest.main()
