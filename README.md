# Reasoning Effort

Adds a reasoning-effort selector after Agent Zero's preset and agent-profile controls.

The plugin asks its authenticated local API for the active chat model's capabilities. The API reads LiteLLM's bundled model registry, returns supported effort values, and keeps provider-specific labels separate from the canonical values passed to LiteLLM. You can also enter a custom value for providers or model aliases that LiteLLM does not describe. A selection applies only to the current chat and model; choosing **Preset / provider default** removes the override.

For models that LiteLLM cannot identify, the selector remains visible as **Custom…** and explains that the provider must support the value you enter.

## Install

Place this directory at `usr/plugins/a0_reasoning_effort` in Agent Zero, then reload the WebUI. No additional dependencies or provider API calls are required.

## Check

From the Agent Zero root:

```bash
python usr/plugins/a0_reasoning_effort/helpers/reasoning_effort.py
```
