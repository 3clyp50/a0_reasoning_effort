# Reasoning Effort

Adds a reasoning-effort selector between Agent Zero's preset and agent-profile controls.

The plugin asks its authenticated local API for the active chat model's capabilities. The API reads LiteLLM's bundled model registry first, then falls back to live model metadata from Agent Zero API, Venice, and OpenRouter. Provider requests use Agent Zero's server-side configuration and are cached for 15 minutes. Provider-specific labels remain separate from the canonical values passed to LiteLLM.

You can enter a custom value when neither LiteLLM nor the provider publishes a list. Models explicitly marked unsupported by the provider show **Unsupported** instead. A selection applies only to the current chat and model; choosing **Preset / provider default** removes the override.

## Install

Place this directory at `usr/plugins/a0_reasoning_effort` in Agent Zero, then reload the WebUI. No additional dependencies are required.

## Check

From the Agent Zero root:

```bash
python usr/plugins/a0_reasoning_effort/helpers/reasoning_effort.py
```
