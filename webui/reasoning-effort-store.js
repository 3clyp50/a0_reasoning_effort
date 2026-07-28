import { createStore } from "/js/AlpineStore.js";
import * as api from "/js/api.js";
import { toastFrontendError } from "/components/notifications/notification-store.js";
import { store as chatsStore } from "/components/sidebar/chats/chats-store.js";

const endpoint = "plugins/a0_reasoning_effort/reasoning_effort";

const model = {
  contextId: "",
  available: false,
  loading: false,
  saving: false,
  model: {},
  options: [],
  selected: "",
  effective: "",
  presetEffort: "",
  source: "provider",
  requestId: 0,

  onMount() {
    return this.refresh(chatsStore.selected || "");
  },

  cleanup() {
    this.requestId += 1;
    this.reset("");
  },

  reset(contextId) {
    this.contextId = contextId;
    this.available = false;
    this.loading = false;
    this.saving = false;
    this.model = {};
    this.options = [];
    this.selected = "";
    this.effective = "";
    this.presetEffort = "";
    this.source = "provider";
  },

  apply(data) {
    this.available = !!data?.available;
    this.model = data?.model || {};
    this.options = Array.isArray(data?.options) ? data.options : [];
    this.selected = data?.selected || "";
    this.effective = data?.effective || "";
    this.presetEffort = data?.preset_effort || "";
    this.source = data?.source || "provider";
  },

  async refresh(contextId) {
    contextId = String(contextId || "");
    const requestId = ++this.requestId;
    if (!contextId) {
      this.reset("");
      return;
    }

    this.contextId = contextId;
    this.loading = true;
    try {
      const response = await api.callJsonApi(endpoint, { action: "get", context_id: contextId });
      if (requestId === this.requestId && contextId === this.contextId) this.apply(response);
    } catch (error) {
      if (requestId === this.requestId) this.reset(contextId);
    } finally {
      if (requestId === this.requestId) this.loading = false;
    }
  },

  async select(effort, custom = false) {
    const contextId = this.contextId;
    if (!contextId || this.saving || chatsStore.selectedContext?.running) return false;

    this.saving = true;
    try {
      const response = await api.callJsonApi(endpoint, { action: "set", context_id: contextId, effort, custom });
      if (contextId === this.contextId) this.apply(response);
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      void toastFrontendError(message, "Reasoning Effort");
      return false;
    } finally {
      this.saving = false;
    }
  },

  label(value) {
    return this.options.find((option) => option.value === value)?.label || value || "Auto";
  },

  customValue() {
    return this.selected && !this.options.some((option) => option.value === this.selected) ? this.selected : "";
  },

  buttonLabel() {
    return this.effective ? this.label(this.effective) : this.available ? "Auto" : "Custom…";
  },

  defaultLabel() {
    return this.presetEffort ? `Use preset (${this.label(this.presetEffort)})` : "Use preset / provider default";
  },

  title() {
    const source = this.source === "chat"
      ? "Chat override"
      : this.source === "preset"
        ? "Preset"
        : this.available
          ? "Provider default"
          : "No values advertised by LiteLLM; enter a custom value";
    const modelName = this.model?.provider && this.model?.name ? ` · ${this.model.provider}/${this.model.name}` : "";
    return `Reasoning effort: ${source}${modelName}`;
  },
};

export const store = createStore("reasoningEffort", model);
