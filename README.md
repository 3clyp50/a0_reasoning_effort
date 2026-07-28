# Reasoning Effort

Adds a reasoning-effort selector after Agent Zero's preset and agent-profile controls.

The plugin asks its authenticated local API for the active chat model's capabilities. The API reads LiteLLM's bundled model registry, returns only supported effort values, and keeps provider-specific labels separate from the canonical values passed to LiteLLM. A selection applies only to the current chat and model; choosing **Preset / provider default** removes the override.

Models that LiteLLM cannot identify keep using Agent Zero's **Extra parameters** configuration and do not show the selector.

## Install

Place this directory at `usr/plugins/a0_reasoning_effort` in Agent Zero, then reload the WebUI. No additional dependencies or provider API calls are required.

## Check

From the Agent Zero root:

```bash
python usr/plugins/a0_reasoning_effort/helpers/reasoning_effort.py
```
