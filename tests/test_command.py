"""Run from the Agent Zero root against the installed plugin."""

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from plugins._commands.helpers import commands
from usr.plugins.a0_reasoning_effort.api import reasoning_effort as api
from usr.plugins.a0_reasoning_effort.helpers import reasoning_effort as helper


class EffortCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.data = {}
        self.context = SimpleNamespace(
            id="effort-command-test", is_running=lambda: True,
            get_data=self.data.get,
            set_data=lambda key, value: self.data.update({key: value}),
        )
        self.context.agent0 = SimpleNamespace(context=self.context)
        self.config = {"provider": "openai", "name": "o3", "kwargs": {"reasoning_effort": "medium"}}
        patches = (
            patch.object(api.AgentContext, "get", return_value=self.context),
            patch.object(api, "get_enabled_plugins", return_value=["a0_reasoning_effort"]),
            patch.object(api, "save_tmp_chat"),
            patch.object(api, "mark_dirty_for_context"),
            patch.object(helper, "get_chat_model_config", return_value=self.config),
            patch.object(helper, "_supported_efforts", return_value=("low", "medium", "high")),
            patch.object(helper, "_provider_models", new_callable=AsyncMock, return_value=None),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    async def resolve(self, text):
        resolution = await commands.resolve_message_command(text, context_id=self.context.id)
        self.assertIsNotNone(resolution)
        self.assertEqual(resolution["command"]["source_plugin"], "a0_reasoning_effort")
        self.assertEqual(resolution["result"]["text"], "")
        return resolution["result"]["effects"][0]

    async def test_command_is_discovered_and_status_does_not_write(self):
        catalog, _ = commands.list_effective_commands()
        entry = next(item for item in catalog if item["name"] == "effort")
        self.assertEqual(entry["source_plugin"], "a0_reasoning_effort")
        self.assertIn("/effort", entry["argument_hint"])
        effect = await self.resolve("/effort")
        self.assertEqual(effect["type"], "show_markdown")
        for expected in ("openai/o3", "`medium` (preset)", "`low`, `medium`, `high`"):
            self.assertIn(expected, effect["content"])
        self.assertEqual(self.data, {})
        api.save_tmp_chat.assert_not_called()

    async def test_set_and_default_share_popover_state(self):
        effect = await self.resolve("/effort HIGH")
        self.assertIn("`high` (chat)", effect["content"])
        self.assertIn("next model turn", effect["content"])
        self.assertEqual(self.data[helper.CONTEXT_KEY], {"model": "openai/o3", "effort": "high"})
        state = await api.ReasoningEffort(None, None).process({"context_id": self.context.id}, None)
        self.assertEqual(state["selected"], "high")
        api.save_tmp_chat.assert_called_once_with(self.context)
        api.mark_dirty_for_context.assert_called_once_with(self.context.id, reason="reasoning_effort_change")

        effect = await self.resolve("/effort default")
        self.assertIn("`medium` (preset)", effect["content"])
        self.assertIsNone(self.data[helper.CONTEXT_KEY])

    async def test_invalid_arguments_and_levels_do_not_change_state(self):
        await self.resolve("/effort low")
        for text in ("/effort high extra", "/effort --force high", "/effort custom", '/effort ""',
                     "/effort maximum", '/effort custom "bad value"'):
            with self.subTest(text=text):
                effect = await self.resolve(text)
                self.assertEqual(effect["level"], "error")
                self.assertEqual(self.data[helper.CONTEXT_KEY]["effort"], "low")
        api.save_tmp_chat.assert_called_once()

    async def test_custom_unknown_model_and_explicit_unsupported_model(self):
        self.config.update(provider="other", name="unknown", kwargs={})
        with patch.object(helper, "_supported_efforts", return_value=()):
            effect = await self.resolve("/effort")
            self.assertIn("No advertised levels", effect["content"])
            effect = await self.resolve("/effort experimental")
            self.assertEqual(effect["level"], "error")
            effect = await self.resolve("/effort custom experimental")
            self.assertIn("`experimental` (chat)", effect["content"])
            self.assertEqual(self.data[helper.CONTEXT_KEY]["effort"], "experimental")

            with patch.object(helper, "_provider_discovery", return_value=("unsupported", ())):
                effect = await self.resolve("/effort")
                self.assertIn("does not support", effect["content"])
                effect = await self.resolve("/effort custom high")
                self.assertEqual(effect["level"], "error")
                effect = await self.resolve("/effort default")
                self.assertIn("provider default", effect["content"])
                self.assertIsNone(self.data[helper.CONTEXT_KEY])

    async def test_custom_cannot_bypass_compatibility_levels(self):
        self.config.update(provider="a0_venice", name="z-ai-glm-5-3", kwargs={})
        with patch.object(helper, "_supported_efforts", return_value=()):
            effect = await self.resolve("/effort custom medium")
            self.assertEqual(effect["level"], "error")
            api.save_tmp_chat.assert_not_called()
            effect = await self.resolve("/effort max")
            self.assertIn("`max` (chat)", effect["content"])

    async def test_disabled_plugin_and_missing_context_cannot_write(self):
        with patch.object(api, "get_enabled_plugins", return_value=[]):
            effect = await self.resolve("/effort high")
            self.assertEqual(effect["level"], "error")
            self.assertIn("not enabled", effect["message"])
        with patch.object(api.AgentContext, "get", return_value=None):
            effect = await self.resolve("/effort high")
            self.assertEqual(effect["level"], "error")
            self.assertIn("Context not found", effect["message"])
        api.save_tmp_chat.assert_not_called()

    async def test_incoming_command_stops_before_the_agent(self):
        module = importlib.import_module(
            "plugins._commands.extensions.python._functions.agent.AgentContext._process_chain.start._10_resolve_slash_command"
        )
        message = SimpleNamespace(message="/effort high")
        data = {"args": (self.context, None, message)}
        await module.ResolveSlashCommand(agent=None).execute(data=data)
        self.assertIn("`high` (chat)", data["result"])
        self.assertEqual(message.message, "/effort high")


if __name__ == "__main__":
    unittest.main()
