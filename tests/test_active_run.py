"""Run from the Agent Zero root against the installed plugin."""

import importlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from openai import AsyncOpenAI

from usr.plugins.a0_reasoning_effort.api import reasoning_effort as api
from usr.plugins.a0_reasoning_effort.helpers import reasoning_effort as helper


class ActiveRunTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        enabled = patch.object(api, "get_enabled_plugins", return_value=["a0_reasoning_effort"])
        enabled.start()
        self.addCleanup(enabled.stop)

    async def test_disabled_plugin_is_unavailable_to_both_clients(self):
        context = SimpleNamespace(agent0=SimpleNamespace())
        with (
            patch.object(api.AgentContext, "get", return_value=context),
            patch.object(api, "get_enabled_plugins", return_value=[]),
            patch.object(api, "get_discovered_state", new_callable=AsyncMock) as discover,
        ):
            handler = api.ReasoningEffort(None, None)
            for action in ("get", "set"):
                response = await handler.process({"context_id": "chat", "action": action, "effort": "high"}, None)
                self.assertEqual(response.status_code, 404)
            discover.assert_not_awaited()

    async def test_model_change_rejects_a_stale_open_menu(self):
        context = SimpleNamespace(agent0=SimpleNamespace(), set_data=Mock())
        with (
            patch.object(api.AgentContext, "get", return_value=context),
            patch.object(api, "get_discovered_state", new_callable=AsyncMock, return_value={"model": {"key": "a0_venice/new-model"}}),
            patch.object(api, "save_tmp_chat") as save,
        ):
            response = await api.ReasoningEffort(None, None).process({
                "action": "set", "context_id": "chat", "effort": "high", "model_key": "a0_venice/old-model",
            }, None)
            self.assertEqual(response.status_code, 409)
            context.set_data.assert_not_called()
            save.assert_not_called()

    async def test_connector_control_reuses_shared_validation_and_per_chat_state(self):
        module = importlib.import_module(
            "usr.plugins.a0_reasoning_effort.extensions.python.connector_controls._50_reasoning_effort"
        )
        data = {}
        context = SimpleNamespace(
            id="connector-test", get_data=data.get,
            set_data=lambda key, value: data.update({key: value}),
        )
        context.agent0 = SimpleNamespace(context=context)
        extension = module.ReasoningEffortControl(context.agent0)
        model_key = "a0_venice/z-ai-glm-5-3"
        with (
            patch.object(api.AgentContext, "get", return_value=context),
            patch.object(api, "save_tmp_chat"),
            patch.object(api, "mark_dirty_for_context"),
            patch.object(helper, "get_chat_model_config", return_value={"provider": "a0_venice", "name": "z-ai-glm-5-3", "kwargs": {}}),
            patch.object(helper, "_supported_efforts", return_value=()),
        ):
            controls = []
            await extension.execute("list", {}, controls, {})
            control = controls[0]
            self.assertEqual(control["type"], "choice")
            self.assertEqual(control["revision"], model_key)
            self.assertEqual([option["value"] for option in control["options"]], ["", "low", "high", "max"])
            for value, revision, expected_status in (("high", model_key, 200), ("medium", model_key, 400), ("low", "old", 409)):
                result = {"response": None}
                await extension.execute("set", {
                    "control_id": control["id"], "value": value,
                    "revision": revision, "custom": True,
                }, [], result)
                response = result["response"]
                self.assertEqual(200 if isinstance(response, dict) else response.status_code, expected_status)
                self.assertEqual(data[helper.CONTEXT_KEY]["effort"], "high")
            result = {"response": None}
            await extension.execute("set", {"control_id": control["id"], "value": "", "revision": model_key}, [], result)
            self.assertEqual(result["response"], {"ok": True})
            self.assertIsNone(data[helper.CONTEXT_KEY])
            result = {"response": None}
            await extension.execute("set", {"control_id": "another-plugin"}, [], result)
            self.assertIsNone(result["response"])

    async def test_connector_control_owns_labels_defaults_and_unsupported_state(self):
        module = importlib.import_module(
            "usr.plugins.a0_reasoning_effort.extensions.python.connector_controls._50_reasoning_effort"
        )
        state = {
            "available": True, "support": "supported", "effective": "xhigh",
            "selected": "", "preset_effort": "xhigh", "model": {"key": "provider/model"},
            "options": [{"value": "xhigh", "label": "Extra"}],
        }
        extension = module.ReasoningEffortControl(SimpleNamespace())
        with patch.object(module, "get_discovered_state", new_callable=AsyncMock, return_value=state):
            controls = []
            await extension.execute("list", {}, controls, {})
            self.assertEqual(controls[0]["label"], "Effort: Extra")
            self.assertEqual(controls[0]["options"][0], {"value": "", "label": "Use preset (Extra)"})
            self.assertTrue(controls[0]["custom"])
            state.update(support="unsupported", options=[], preset_effort="", effective="")
            controls = []
            await extension.execute("list", {}, controls, {})
            self.assertEqual(controls[0]["label"], "Effort: Unsupported")
            self.assertFalse(controls[0]["custom"])

    async def test_compatibility_effort_survives_litellm_request_filtering(self):
        captured = []

        def receive(request):
            body = json.loads(request.content)
            captured.append(body)
            return httpx.Response(200, json={
                "id": "chatcmpl-test", "object": "chat.completion", "created": 1,
                "model": body["model"], "choices": [{
                    "index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }],
            })

        cases = (
            ("a0_venice", "openai", "gemini-4-argon"),
            ("venice", "veniceai", "gemini-4-argon"),
            ("a0_venice", "openai", "z-ai-glm-5-3"),
            ("venice", "veniceai", "z-ai-glm-5-3"),
            ("zai", "zai", "glm-5.3"),
            ("zai_coding", "zai", "glm-5.3"),
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as transport:
            client = AsyncOpenAI(
                api_key="test-only", base_url="https://example.invalid/v1",
                http_client=transport, max_retries=0,
            )
            for provider, adapter, model in cases:
                for effort in helper.compatibility_efforts(provider, model):
                    with self.subTest(provider=provider, model=model, effort=effort):
                        kwargs = {"reasoning_effort": effort, "extra_body": {"metadata": {"retained": True}}}
                        self.assertTrue(helper.prepare_compatibility_kwargs(provider, model, kwargs))
                        await helper.litellm.acompletion(
                            model=model, custom_llm_provider=adapter, client=client, api_key="test-only",
                            messages=[{"role": "user", "content": "test"}],
                            drop_params=True, num_retries=0, **kwargs,
                        )
                        self.assertEqual(captured[-1]["reasoning_effort"], effort)
                        self.assertEqual(captured[-1]["metadata"], {"retained": True})
                        self.assertEqual("thinking" in captured[-1], provider in ("zai", "zai_coding"))

    async def test_argon_gateway_efforts_are_discovered_validated_and_forwarded(self):
        hook = importlib.import_module(
            "usr.plugins.a0_reasoning_effort.extensions.python._functions.agent.Agent.get_chat_model.end._50_reasoning_effort"
        )
        for provider in ("a0_venice", "venice"):
            with self.subTest(provider=provider):
                data = {}
                context = SimpleNamespace(
                    id="argon-chat", is_running=lambda: True,
                    get_data=data.get, set_data=lambda key, value: data.update({key: value}),
                )
                context.agent0 = SimpleNamespace(context=context)
                config = {"provider": provider, "name": "gemini-4-argon", "kwargs": {}}
                handler = api.ReasoningEffort(None, None)
                extension = hook.ReasoningEffortOverride(context.agent0)
                with (
                    patch.object(api.AgentContext, "get", return_value=context),
                    patch.object(api, "save_tmp_chat"),
                    patch.object(api, "mark_dirty_for_context"),
                    patch.object(helper, "get_chat_model_config", return_value=config),
                    patch.object(helper, "_supported_efforts", return_value=()),
                    patch.object(helper, "_provider_models", new_callable=AsyncMock) as fetch,
                    patch.object(hook, "get_chat_model_config", return_value=config),
                ):
                    state = await helper.get_discovered_state(context.agent0)
                    self.assertEqual(state["option_source"], "compatibility")
                    self.assertEqual([option["value"] for option in state["options"]], ["low", "medium", "high"])
                    fetch.assert_not_awaited()
                    for effort in ("low", "medium", "high"):
                        response = await handler.process(
                            {"action": "set", "context_id": context.id, "effort": effort}, None
                        )
                        self.assertTrue(response["ok"])
                        self.assertEqual(response["selected"], effort)
                        next_turn = SimpleNamespace(kwargs={"extra_body": {"metadata": {"key": "value"}}})
                        extension.execute({"result": next_turn})
                        self.assertEqual(next_turn.kwargs, {"extra_body": {
                            "metadata": {"key": "value"}, "reasoning_effort": effort,
                        }})
                    for effort in ("none", "minimal", "xhigh", "max"):
                        rejected = await handler.process(
                            {"action": "set", "context_id": context.id, "effort": effort, "custom": True}, None
                        )
                        self.assertEqual(rejected.status_code, 400)
                        self.assertEqual(data[helper.CONTEXT_KEY]["effort"], "high")
                    with patch.object(helper, "_supported_efforts", return_value=("high",)):
                        native = helper.get_state(context.agent0)
                        self.assertEqual(native["option_source"], "litellm")
                        self.assertEqual([option["value"] for option in native["options"]], ["high"])

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
