# Reasoning Effort

Adds a reasoning-effort selector between Agent Zero's preset and agent-profile controls, plus an `/effort` slash command.

The plugin asks its authenticated local API for the active chat model's capabilities. The API reads LiteLLM's bundled model registry first, then falls back to live model metadata from Agent Zero API, Venice, and OpenRouter. Provider requests use Agent Zero's server-side configuration and are cached for 15 minutes. Provider-specific labels remain separate from the canonical values passed to LiteLLM.

Compatibility fallbacks cover GLM-5.3 (`low`, `high`, `max`) on Z.AI, Z.AI Coding, Agent Zero API, and Venice, plus `gemini-4-argon` (`low`, `medium`, `high`) on Agent Zero API and Venice. These fill gaps in LiteLLM and gateway metadata; native LiteLLM support takes precedence when available. The selected value is forwarded through `extra_body` so provider adapters cannot drop it; only direct Z.AI requests also enable `thinking`.

Argon's [Google model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon) and [Venice model page](https://venice.ai/models/gemini-4-argon) document these three levels. Venice's catalog currently reports `supportsReasoningEffort: false`; accepting a request does not establish that its upstream provider honors the effort.

You can enter a custom value when neither LiteLLM nor the provider publishes a list. Models explicitly marked unsupported by the provider show **Unsupported** instead. A selection applies only to the current chat and model; choosing **Preset / provider default** removes the override.

You can change reasoning effort while the agent is running. The selection applies to the next model turn; a request already in progress keeps its original effort.

## A0 Connector

Version **0.4.0** registers an **Effort** choice control through Core's scoped `connector_controls` extension point. This requires an Agent Zero Core build advertising the `composer_controls` capability and a compatible `a0-connector` build. Older builds continue to use the WebUI normally.

The anchored popover beside provider/model offers the same advertised values, custom field, and preset/provider default as the WebUI. Labels, choices, validation, and per-chat/model persistence remain in this plugin; the connector only renders generic controls. Requests use Core's authenticated, CSRF-protected control API. Disabling or removing the plugin hides the control. Escape or clicking outside cancels without changing the setting.

## Slash command

Version **0.4.1** adds `/effort` to the WebUI slash picker and A0 CLI command palette when Core's built-in Commands plugin is enabled. It runs entirely in this plugin, without an LLM request or plugin-specific connector code.

- `/effort` shows the current model, effective effort, its source, and available levels.
- `/effort high` selects an advertised level. Use canonical values such as `xhigh` for **Extra** and `none` for **Off**, when available.
- `/effort default` removes the current chat/model override and restores the preset/provider default.
- `/effort custom <value>` uses the same custom-value validation as the popover; it cannot bypass an explicitly unsupported model or compatibility-level restrictions.

Changes share the popover's per-chat/model state and apply to the next model turn. The CLI sends plugin commands through its normal chat path; use the popover to change effort immediately during an active run.

## Install

Place this directory at `usr/plugins/a0_reasoning_effort` in Agent Zero, then reload the WebUI. No additional dependencies are required.

## Check

From the Agent Zero root:

```bash
PYTHONPATH=. python usr/plugins/a0_reasoning_effort/helpers/reasoning_effort.py
PYTHONPATH=. python usr/plugins/a0_reasoning_effort/tests/test_active_run.py
PYTHONPATH=. python usr/plugins/a0_reasoning_effort/tests/test_command.py
node usr/plugins/a0_reasoning_effort/tests/test_active_run.mjs
```
