"""Full-screen settings modal with tabbed navigation for all config sections."""

from dataclasses import asdict

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, Tab, Tabs

from stupidex.commands.session_commands import _build_model_picker_items
from stupidex.config import (
    Config,
    RAGConfig,
    validate_config,
)
from stupidex.screens.picker import OptionPicker


class NewProviderForm(ModalScreen[dict | None]):
    """Modal form to add or edit a provider entry.

    Per-model attributes are edited inline via a dynamic list of model rows.
    Each row captures ``model_id`` plus the four supported override fields:
    ``max_input_tokens``, ``max_output_tokens``, ``supports_vision``, ``mode``.
    """

    CSS = """
    NewProviderForm {
        align: center middle;
    }
    #provider-form-container {
        width: 76;
        height: auto;
        max-height: 85%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #provider-form-container Input {
        margin-bottom: 1;
    }
    #provider-form-container Label {
        margin-top: 1;
        text-style: bold;
    }
    #provider-form-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #provider-form-buttons Button {
        margin: 0 1;
    }
    #provider-form-error {
        color: $error;
        margin-bottom: 1;
    }
    #pf-models-list {
        margin-top: 1;
        height: auto;
    }
    .pf-model-row {
        height: auto;
        border: solid $surface-lighten-1;
        padding: 0 1;
        margin-bottom: 1;
    }
    .pf-model-row-input {
        width: 1fr;
        margin: 0 1 0 0;
    }
    .pf-model-row-small {
        width: 12;
        margin: 0 1 0 0;
    }
    .pf-model-row-vision {
        width: 16;
        margin: 0 1 0 0;
    }
    .pf-model-row-remove {
        width: auto;
    }
    .pf-model-row-label {
        text-style: bold;
        margin-bottom: 1;
    }
    """

    def __init__(self, title: str, initial: dict | None = None) -> None:
        super().__init__()
        self._title = title
        self._initial = initial or {}
        # Tracking list of model entries for dynamic add/remove.
        # Each entry is a dict: {"model_id": str, "max_input_tokens": str,
        # "max_output_tokens": str, "supports_vision": bool, "mode": str}
        # Values are kept as strings (tokens) / bool / str to round-trip through Inputs.
        self._model_entries: list[dict] = []
        # Track the next available index for unique widget IDs.
        self._model_seq = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="provider-form-container"):
            yield Static(self._title, id="provider-form-title")
            yield Static("", id="provider-form-error")
            yield Label("Alias (e.g. 'work-openai'):")
            yield Input(
                placeholder="my-provider",
                value=self._initial.get("_alias", ""),
                id="pf-alias",
            )
            yield Label("Base URL:")
            yield Input(
                placeholder="https://api.openai.com/v1",
                value=self._initial.get("base_url", ""),
                id="pf-base-url",
            )
            yield Label("API Key:")
            yield Input(
                placeholder="sk-...",
                value=self._initial.get("api_key", ""),
                password=True,
                id="pf-api-key",
            )
            yield Label("API Key Env Var:")
            yield Input(
                placeholder="OPENAI_API_KEY",
                value=self._initial.get("api_key_env", ""),
                id="pf-api-key-env",
            )
            yield Label("LiteLLM Provider:")
            yield Input(
                placeholder="openai",
                value=self._initial.get("litellm_provider", ""),
                id="pf-litellm-provider",
            )
            yield Label("Models:")
            yield Vertical(id="pf-models-list")
            with Horizontal(id="provider-form-buttons"):
                yield Button("Add Model", id="pf-add-model")
                yield Button("Save", variant="primary", id="pf-save")
                yield Button("Cancel", variant="default", id="pf-cancel")

    def on_mount(self) -> None:
        # Seed the models list from the initial config.
        initial_models = self._initial.get("models", {}) if isinstance(self._initial, dict) else {}
        if isinstance(initial_models, dict):
            for model_id, overrides in initial_models.items():
                if not isinstance(overrides, dict):
                    overrides = {}
                self._add_model_entry(model_id=model_id, overrides=overrides)
        # Always ensure at least one empty row when adding a new provider with
        # no models, so the user has a visible place to type.
        if not self._model_entries:
            self._add_model_entry()
        self.query_one("#pf-alias", Input).focus()

    # ── Dynamic model entries ──────────────────────────────────────────

    def _add_model_entry(
        self,
        model_id: str = "",
        overrides: dict | None = None,
    ) -> None:
        """Append a new model row to the form and mount its widgets."""
        overrides = overrides or {}
        idx = self._model_seq
        self._model_seq += 1
        supports_vision = bool(overrides.get("supports_vision", False))
        entry = {
            "idx": idx,
            "model_id": model_id,
            "max_input_tokens": str(overrides.get("max_input_tokens", ""))
            if overrides.get("max_input_tokens") is not None
            else "",
            "max_output_tokens": str(overrides.get("max_output_tokens", ""))
            if overrides.get("max_output_tokens") is not None
            else "",
            "supports_vision": supports_vision,
            "mode": str(overrides.get("mode", "")) if overrides.get("mode") else "",
        }
        self._model_entries.append(entry)
        models_list = self.query_one("#pf-models-list", Vertical)
        models_list.mount(self._build_model_row(entry))
        # Focus the freshly added model_id input to make the entry point obvious.
        try:
            self.query_one(f"#pf-model-id-{idx}", Input).focus()
        except Exception:
            pass

    def _build_model_row(self, entry: dict) -> Vertical:
        idx = entry["idx"]
        vision_select = Select(
            [("false", False), ("true", True)],
            value=entry["supports_vision"],
            id=f"pf-model-vision-{idx}",
            classes="pf-model-row-vision",
        )
        return Vertical(
            Label("Model ID:", classes="pf-model-row-label"),
            Input(
                placeholder="gpt-4o",
                value=entry["model_id"],
                id=f"pf-model-id-{idx}",
                classes="pf-model-row-input",
            ),
            Horizontal(
                Input(
                    placeholder="max_input_tokens",
                    value=entry["max_input_tokens"],
                    id=f"pf-model-mit-{idx}",
                    classes="pf-model-row-small",
                ),
                Input(
                    placeholder="max_output_tokens",
                    value=entry["max_output_tokens"],
                    id=f"pf-model-mot-{idx}",
                    classes="pf-model-row-small",
                ),
                vision_select,
                Input(
                    placeholder="mode (chat)",
                    value=entry["mode"],
                    id=f"pf-model-mode-{idx}",
                    classes="pf-model-row-small",
                ),
                Button("Remove", id=f"pf-model-rm-{idx}", classes="pf-model-row-remove"),
            ),
            classes="pf-model-row",
        )

    def _remove_model_entry(self, idx: int) -> None:
        # Drop the entry from the tracking list and unmount its row.
        self._model_entries = [e for e in self._model_entries if e["idx"] != idx]
        # Find the row container that owns the matching remove button and remove it.
        for row in self.query(".pf-model-row"):
            try:
                row.query_one(f"#pf-model-rm-{idx}", Button)
            except Exception:
                continue
            row.remove()
            break

    # ── Event handlers ─────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "pf-save":
            self._do_save()
        elif btn_id == "pf-cancel":
            self.dismiss(None)
        elif btn_id == "pf-add-model":
            self._add_model_entry()
        elif btn_id.startswith("pf-model-rm-"):
            idx = int(btn_id[len("pf-model-rm-") :])
            self._remove_model_entry(idx)

    def on_input_changed(self, event: Input.Changed) -> None:
        # Keep the in-memory entry dict in sync so save reflects edits.
        input_id = event.input.id or ""
        for entry in self._model_entries:
            i = entry["idx"]
            if input_id == f"pf-model-id-{i}":
                entry["model_id"] = event.value
            elif input_id == f"pf-model-mit-{i}":
                entry["max_input_tokens"] = event.value
            elif input_id == f"pf-model-mot-{i}":
                entry["max_output_tokens"] = event.value
            elif input_id == f"pf-model-mode-{i}":
                entry["mode"] = event.value

    def on_select_changed(self, event: Select.Changed) -> None:
        select_id = event.select.id or ""
        for entry in self._model_entries:
            i = entry["idx"]
            if select_id == f"pf-model-vision-{i}":
                entry["supports_vision"] = bool(event.value)

    def _do_save(self) -> None:
        alias = self.query_one("#pf-alias", Input).value.strip()
        if not alias:
            self.query_one("#provider-form-error", Static).update("Alias is required.")
            return
        if "/" in alias:
            self.query_one("#provider-form-error", Static).update("Alias cannot contain '/'.")
            return

        base_url = self.query_one("#pf-base-url", Input).value.strip()
        api_key = self.query_one("#pf-api-key", Input).value.strip()
        api_key_env = self.query_one("#pf-api-key-env", Input).value.strip()
        litellm_provider = self.query_one("#pf-litellm-provider", Input).value.strip()

        entry: dict = {}
        if base_url:
            entry["base_url"] = base_url
        if api_key:
            entry["api_key"] = api_key
        if api_key_env:
            entry["api_key_env"] = api_key_env
        if litellm_provider:
            entry["litellm_provider"] = litellm_provider

        # Collect model entries into the models dict.
        models: dict[str, dict] = {}
        seen_ids: set[str] = set()
        for entry_data in self._model_entries:
            model_id = entry_data["model_id"].strip()
            if not model_id:
                continue
            if model_id in seen_ids:
                self.query_one(
                    "#provider-form-error", Static
                ).update(f"Duplicate model id: {model_id}")
                return
            seen_ids.add(model_id)
            overrides: dict = {}
            mit = entry_data["max_input_tokens"].strip()
            if mit:
                try:
                    overrides["max_input_tokens"] = int(mit)
                except ValueError:
                    self.query_one(
                        "#provider-form-error", Static
                    ).update(f"max_input_tokens must be an integer for {model_id!r}.")
                    return
            mot = entry_data["max_output_tokens"].strip()
            if mot:
                try:
                    overrides["max_output_tokens"] = int(mot)
                except ValueError:
                    self.query_one(
                        "#provider-form-error", Static
                    ).update(f"max_output_tokens must be an integer for {model_id!r}.")
                    return
            if entry_data["supports_vision"]:
                overrides["supports_vision"] = True
            mode = entry_data["mode"].strip()
            if mode:
                overrides["mode"] = mode
            models[model_id] = overrides
        if models:
            entry["models"] = models

        result = {"_alias": alias, **entry}
        self.dismiss(result)


class NewMCPServerForm(ModalScreen[dict | None]):
    """Modal form to add or edit an MCP server entry."""

    CSS = NewProviderForm.CSS.replace("#provider-form-container", "#mcp-form-container").replace(
        "#provider-form-error", "#mcp-form-error"
    )

    def __init__(self, title: str, initial: dict | None = None) -> None:
        super().__init__()
        self._title = title
        self._initial = initial or {}

    def compose(self) -> ComposeResult:
        with Vertical(id="mcp-form-container"):
            yield Static(self._title, id="mcp-form-title")
            yield Static("", id="mcp-form-error")
            yield Label("Name (e.g. 'my-server'):")
            yield Input(
                placeholder="my-server",
                value=self._initial.get("_name", ""),
                id="mf-name",
            )
            yield Label("Command:")
            yield Input(
                placeholder="node",
                value=self._initial.get("command", ""),
                id="mf-command",
            )
            yield Label("Args (comma-separated):")
            yield Input(
                placeholder="server.js, --port, 3000",
                value=", ".join(self._initial.get("args", [])) if self._initial.get("args") else "",
                id="mf-args",
            )
            yield Label("URL (for SSE servers, leave command/args blank):")
            yield Input(
                placeholder="http://localhost:3000/sse",
                value=self._initial.get("url", ""),
                id="mf-url",
            )
            with Horizontal(id="provider-form-buttons"):
                yield Button("Save", variant="primary", id="mf-save")
                yield Button("Cancel", variant="default", id="mf-cancel")

    def on_mount(self) -> None:
        self.query_one("#mf-name", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "mf-save":
            self._do_save()
        else:
            self.dismiss(None)

    def _do_save(self) -> None:
        name = self.query_one("#mf-name", Input).value.strip()
        if not name:
            self.query_one("#mcp-form-error", Static).update("Name is required.")
            return

        command = self.query_one("#mf-command", Input).value.strip()
        args_str = self.query_one("#mf-args", Input).value.strip()
        url = self.query_one("#mf-url", Input).value.strip()

        entry: dict = {}
        if url:
            entry["url"] = url
        elif command:
            entry["command"] = command
            if args_str:
                entry["args"] = [a.strip() for a in args_str.split(",") if a.strip()]
            else:
                entry["args"] = []
        else:
            self.query_one("#mcp-form-error", Static).update("Either command or url is required.")
            return

        result = {"_name": name, **entry}
        self.dismiss(result)


class SettingsScreen(ModalScreen[Config | None]):
    """Full-screen settings modal with tabbed navigation.

    Returns the modified `Config` on Save, or `None` on Cancel.
    """

    CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-container {
        width: 90%;
        height: 90%;
        border: thick $primary;
        background: $surface;
        padding: 0;
    }

    #settings-header {
        dock: top;
        height: 3;
        padding: 1 2;
        background: $primary-darken-2;
    }

    #settings-tabs {
        dock: top;
        width: 100%;
    }

    #settings-content {
        height: 1fr;
        padding: 1 2;
    }

    #settings-footer {
        dock: bottom;
        height: auto;
        padding: 1 2;
        background: $primary-darken-2;
    }

    #settings-footer-buttons {
        height: auto;
        align: center middle;
    }

    #settings-footer-buttons Button {
        margin: 0 1;
    }

    #settings-footer-hint {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }

    #settings-save {
        text-style: bold;
    }

    #settings-error {
        color: $error;
        margin: 1 0;
        text-style: bold;
    }

    .settings-section-title {
        text-style: bold;
        margin-bottom: 1;
    }

    .settings-row {
        height: auto;
        margin-bottom: 1;
    }

    .settings-label {
        width: 30;
        padding: 0 1;
    }

    .settings-input {
        width: 1fr;
    }

    .settings-picker-button {
        width: 1fr;
    }

    .settings-list-item {
        margin-bottom: 1;
        border: solid $surface-lighten-1;
        padding: 0 1;
    }

    .settings-list-item-label {
        text-style: bold;
    }

    .settings-list-item-detail {
        color: $text-muted;
    }

    .tier-row {
        height: auto;
        margin-bottom: 1;
        align-vertical: middle;
    }

    .tier-label {
        width: 20;
        padding: 0 1;
        text-style: bold;
    }

    .tier-current {
        width: 1fr;
        padding: 0 1;
        color: $text-muted;
    }

    .item-actions {
        dock: right;
        width: auto;
    }

    .item-actions Button {
        margin: 0 1;
    }
    """

    TABS = ["Providers", "MCP Servers", "Tier Models", "RAG", "General"]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = Config(**asdict(config))  # deep copy
        self._items_cache: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-container"):
            yield Static("Settings", id="settings-header")
            yield Tabs(*[Tab(name, id=name.lower().replace(" ", "-")) for name in self.TABS], id="settings-tabs")
            yield ScrollableContainer(id="settings-content")
            with Vertical(id="settings-footer"):
                with Horizontal(id="settings-footer-buttons"):
                    yield Static("", id="settings-error")
                    yield Button("Save [Ctrl+S]", variant="primary", id="settings-save")
                    yield Button("Cancel [Esc]", variant="default", id="settings-cancel")
                yield Static(
                    "Press Ctrl+S to save changes, Esc to cancel.",
                    id="settings-footer-hint",
                )

    def on_mount(self) -> None:
        self._render_tab("providers")

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id or "providers"
        self._render_tab(tab_id)

    def _render_tab(self, tab_id: str) -> None:
        container = self.query_one("#settings-content", ScrollableContainer)
        container.remove_children()
        getattr(self, f"_render_{tab_id.replace('-', '_')}")(container)

    # ── Providers tab ─────────────────────────────────────────────────

    def _render_providers(self, container: ScrollableContainer) -> None:
        container.mount(Static("Providers", classes="settings-section-title"))
        container.mount(Static("Configure API providers and their models.", classes="settings-list-item-detail"))

        items = []
        for alias, entry in self._config.providers.items():
            models = list(entry.get("models", {}).keys())[:3]
            models_str = ", ".join(models) if models else "no models"
            detail = f"{entry.get('base_url', '') or entry.get('litellm_provider', 'unknown')} — {models_str}"
            items.append((alias, detail))

        self._render_keyed_list(container, items, "prov")

        container.mount(Horizontal(
            Button("Add Provider", variant="primary", id="providers-add"),
            classes="settings-row",
        ))

    def _on_provider_action(self, alias: str, action: str) -> None:
        if action == "edit":
            entry = self._config.providers.get(alias, {})
            initial = {
                "_alias": alias,
                **entry,
            }
            self.app.push_screen(
                NewProviderForm(f"Edit Provider: {alias}", initial),
                self._on_edit_provider_result,
            )
        elif action == "delete":
            self._config.providers.pop(alias, None)
            self._refresh_tab()

    def _on_edit_provider_result(self, result: dict | None) -> None:
        if result is not None:
            alias = result.pop("_alias")
            self._config.providers[alias] = result
            self._refresh_tab()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""

        # ── Provider list actions ────────────────────────
        if btn_id.startswith("prov-edit-") or btn_id.startswith("prov-del-"):
            idx = int(btn_id.split("-")[-1])
            if 0 <= idx < len(self._items_cache):
                alias = self._items_cache[idx][0]
                if btn_id.startswith("prov-edit-"):
                    self._on_provider_action(alias, "edit")
                else:
                    self._on_provider_action(alias, "delete")
            return

        # ── MCP list actions ─────────────────────────────
        if btn_id.startswith("mcp-edit-") or btn_id.startswith("mcp-del-"):
            idx = int(btn_id.split("-")[-1])
            if 0 <= idx < len(self._items_cache):
                name = self._items_cache[idx][0]
                if btn_id.startswith("mcp-edit-"):
                    self._on_mcp_action(name, "edit")
                else:
                    self._on_mcp_action(name, "delete")
            return

        # ── Tier model change buttons ────────────────────
        if btn_id.startswith("tier-change-"):
            tier = btn_id[len("tier-change-") :]
            self._open_tier_model_picker(tier)
            return

        # ── Other buttons ────────────────────────────────
        if btn_id == "providers-add":
            self.app.push_screen(NewProviderForm("Add Provider"), self._on_add_provider_result)
        elif btn_id == "mcp-add":
            self.app.push_screen(NewMCPServerForm("Add MCP Server"), self._on_add_mcp_result)
        elif btn_id == "settings-save":
            self._do_save()
        elif btn_id == "settings-cancel":
            self.dismiss(None)

    def _on_add_provider_result(self, result: dict | None) -> None:
        if result is not None:
            alias = result.pop("_alias")
            self._config.providers[alias] = result
            self._refresh_tab()

    def _refresh_tab(self) -> None:
        tabs = self.query_one("#settings-tabs", Tabs)
        active = tabs.active
        if active:
            self._render_tab(active)

    # ── MCP Servers tab ───────────────────────────────────────────────

    def _render_mcp_servers(self, container: ScrollableContainer) -> None:
        container.mount(Static("MCP Servers", classes="settings-section-title"))
        container.mount(Static("Configure MCP tool servers.", classes="settings-list-item-detail"))

        items = []
        for name, entry in self._config.mcp_servers.items():
            if "url" in entry:
                detail = f"SSE: {entry['url']}"
            else:
                detail = f"{entry.get('command', '?')} {' '.join(entry.get('args', []))}"
            items.append((name, detail))

        self._render_keyed_list(container, items, "mcp")

        container.mount(Horizontal(
            Button("Add MCP Server", variant="primary", id="mcp-add"),
            classes="settings-row",
        ))

    def _on_mcp_action(self, name: str, action: str) -> None:
        if action == "edit":
            entry = self._config.mcp_servers.get(name, {})
            initial = {"_name": name, **entry}
            self.app.push_screen(
                NewMCPServerForm(f"Edit MCP Server: {name}", initial),
                self._on_edit_mcp_result,
            )
        elif action == "delete":
            self._config.mcp_servers.pop(name, None)
            self._refresh_tab()

    def _on_edit_mcp_result(self, result: dict | None) -> None:
        if result is not None:
            name = result.pop("_name")
            self._config.mcp_servers[name] = result
            self._refresh_tab()

    def _on_add_mcp_result(self, result: dict | None) -> None:
        if result is not None:
            name = result.pop("_name")
            self._config.mcp_servers[name] = result
            self._refresh_tab()

    # ── Tier Models tab ───────────────────────────────────────────────

    TIERS = ["tolo", "tainha", "papudo", "papaca"]

    def _render_tier_models(self, container: ScrollableContainer) -> None:
        container.mount(Static("Tier Models", classes="settings-section-title"))
        container.mount(
            Static(
                "Map each agent tier to a model (alias/model format). "
                "Click Change to pick from configured providers.",
                classes="settings-list-item-detail",
            )
        )

        # Build the available picker items once per render to know whether any models exist.
        picker_items = _build_model_picker_items(self._config)
        if not picker_items:
            container.mount(
                Static(
                    "No models available. Add providers and models in the Providers tab first.",
                    classes="settings-list-item-detail",
                )
            )
            return

        for tier in self.TIERS:
            current = self._config.tier_models.get(tier, self._config.default_model)
            container.mount(
                Horizontal(
                    Label(f"  {tier}:", classes="tier-label"),
                    Static(current or "—", classes="tier-current"),
                    Button("Change", id=f"tier-change-{tier}"),
                    classes="tier-row",
                )
            )

    def _open_tier_model_picker(self, tier: str) -> None:
        """Push the OptionPicker to select a model assignment for `tier`."""
        items = _build_model_picker_items(self._config)
        if not items:
            return

        def _on_picked(selected: str | None) -> None:
            if not selected:
                return
            self._config.tier_models[tier] = selected
            self._refresh_tab()

        self.app.push_screen(OptionPicker(items), _on_picked)

    # ── RAG tab ───────────────────────────────────────────────────────

    def _render_rag(self, container: ScrollableContainer) -> None:
        container.mount(Static("RAG Settings", classes="settings-section-title"))
        container.mount(Static("Configure retrieval-augmented generation parameters.", classes="settings-list-item-detail"))

        fields = [
            ("chunk_size", "Chunk Size", str(self._config.rag.chunk_size)),
            ("chunk_overlap", "Chunk Overlap", str(self._config.rag.chunk_overlap)),
            ("top_k", "Top K", str(self._config.rag.top_k)),
            ("max_file_size", "Max File Size (bytes)", str(self._config.rag.max_file_size)),
        ]
        for field_id, label, value in fields:
            container.mount(Horizontal(
                Label(f"  {label}:", classes="settings-label"),
                Input(value=value, id=f"rag-{field_id}", classes="settings-input"),
                classes="settings-row",
            ))

        container.mount(Horizontal(
            Label("  Embedding Model:", classes="settings-label"),
            Input(
                value=self._config.rag.embedding_model,
                id="rag-embedding_model",
                classes="settings-input",
            ),
            classes="settings-row",
        ))

    # ── General tab ───────────────────────────────────────────────────

    def _render_general(self, container: ScrollableContainer) -> None:
        container.mount(Static("General Settings", classes="settings-section-title"))
        container.mount(Static("Default model, directory options, and timeouts.", classes="settings-list-item-detail"))

        fields = [
            ("default_model", "Default Model", self._config.default_model),
            ("command_timeout", "Command Timeout (s)", str(self._config.command_timeout)),
            ("read_line_limit", "Read Line Limit", str(self._config.read_line_limit)),
            ("grep_max_results", "Grep Max Results", str(self._config.grep_max_results)),
            ("directory_tree_depth", "Directory Tree Depth", str(self._config.directory_tree_depth)),
            ("ast_max_file_size", "AST Max File Size (bytes)", str(self._config.ast_max_file_size)),
        ]
        for field_id, label, value in fields:
            container.mount(Horizontal(
                Label(f"  {label}:", classes="settings-label"),
                Input(value=value, id=f"gen-{field_id}", classes="settings-input"),
                classes="settings-row",
            ))

        container.mount(Horizontal(
            Label("  Theme:", classes="settings-label"),
            Input(value=self._config.theme, id="gen-theme", classes="settings-input"),
            classes="settings-row",
        ))

        container.mount(Horizontal(
            Label("  Personality:", classes="settings-label"),
            Input(value=self._config.personality, id="gen-personality", classes="settings-input"),
            classes="settings-row",
        ))

    # ── Helpers ───────────────────────────────────────────────────────

    def _render_keyed_list(
        self,
        container: ScrollableContainer,
        items: list[tuple[str, str]],
        action_prefix: str,
    ) -> None:
        """Render a list of named items with Edit/Delete buttons.

        `action_prefix` is used in button IDs as `{prefix}-edit-{index}` and
        `{prefix}-del-{index}`. The index is looked up in `items` when clicked.
        """
        self._items_cache = items
        for idx, (key, detail) in enumerate(items):
            item = Vertical(
                Static(key, classes="settings-list-item-label"),
                Static(detail, classes="settings-list-item-detail"),
                Horizontal(
                    Button("Edit", id=f"{action_prefix}-edit-{idx}", classes="small"),
                    Button("Delete", id=f"{action_prefix}-del-{idx}", classes="small"),
                    classes="item-actions",
                ),
                classes="settings-list-item",
            )
            container.mount(item)

    def _collect_modified_config(self) -> Config:
        """Read all input fields and produce a modified Config.

        Tier models are stored directly on `self._config.tier_models` by the
        OptionPicker callbacks, so they are not re-read from Inputs here.
        """
        cfg = self._config

        # RAG
        rag_fields = {
            "rag-chunk_size": ("chunk_size", int),
            "rag-chunk_overlap": ("chunk_overlap", int),
            "rag-top_k": ("top_k", int),
            "rag-max_file_size": ("max_file_size", int),
            "rag-embedding_model": ("embedding_model", str),
        }
        rag_kw = {}
        for widget_id, (field_name, cast_type) in rag_fields.items():
            try:
                inp = self.query_one(f"#{widget_id}", Input)
                val = inp.value.strip()
                if cast_type is int:
                    val = int(val) if val else 0
                elif cast_type is str:
                    val = val if val else cfg.rag.embedding_model
                rag_kw[field_name] = val
            except Exception:
                pass
        if rag_kw:
            cfg.rag = RAGConfig(**{**asdict(cfg.rag), **rag_kw})

        # General
        gen_int_fields = {
            "gen-command_timeout": "command_timeout",
            "gen-read_line_limit": "read_line_limit",
            "gen-grep_max_results": "grep_max_results",
            "gen-directory_tree_depth": "directory_tree_depth",
            "gen-ast_max_file_size": "ast_max_file_size",
        }
        for widget_id, field_name in gen_int_fields.items():
            try:
                inp = self.query_one(f"#{widget_id}", Input)
                val = inp.value.strip()
                if val:
                    setattr(cfg, field_name, int(val))
            except Exception:
                pass

        gen_str_fields = {
            "gen-default_model": "default_model",
            "gen-theme": "theme",
            "gen-personality": "personality",
        }
        for widget_id, field_name in gen_str_fields.items():
            try:
                inp = self.query_one(f"#{widget_id}", Input)
                val = inp.value.strip()
                if val:
                    setattr(cfg, field_name, val)
            except Exception:
                pass

        return cfg

    def _do_save(self) -> None:
        config = self._collect_modified_config()
        errors = validate_config(config)
        if errors:
            err_widget = self.query_one("#settings-error", Static)
            err_widget.update("Errors:\n" + "\n".join(f"• {e}" for e in errors))
            return
        self.dismiss(config)

    # ── Keyboard shortcuts ────────────────────────────────────────────

    def key_ctrl_s(self) -> None:
        """Ctrl+S saves the current settings."""
        self._do_save()

    def key_escape(self) -> None:
        self.dismiss(None)
