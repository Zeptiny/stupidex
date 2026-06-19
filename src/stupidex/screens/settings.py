"""Full-screen settings modal with tabbed navigation for all config sections."""

from dataclasses import asdict

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, Tab, Tabs

from stupidex.config import (
    Config,
    RAGConfig,
    validate_config,
)


class NewProviderForm(ModalScreen[dict | None]):
    """Modal form to add or edit a provider entry."""

    CSS = """
    NewProviderForm {
        align: center middle;
    }
    #provider-form-container {
        width: 60;
        height: auto;
        max-height: 80%;
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
    """

    def __init__(self, title: str, initial: dict | None = None) -> None:
        super().__init__()
        self._title = title
        self._initial = initial or {}

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
            yield Label("Models (comma-separated):")
            yield Input(
                placeholder="gpt-4o, gpt-4o-mini",
                value=self._initial.get("_models_str", ""),
                id="pf-models",
            )
            with Horizontal(id="provider-form-buttons"):
                yield Button("Save", variant="primary", id="pf-save")
                yield Button("Cancel", variant="default", id="pf-cancel")

    def on_mount(self) -> None:
        self.query_one("#pf-alias", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pf-save":
            self._do_save()
        else:
            self.dismiss(None)

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
        models_str = self.query_one("#pf-models", Input).value.strip()

        entry: dict = {}
        if base_url:
            entry["base_url"] = base_url
        if api_key:
            entry["api_key"] = api_key
        if api_key_env:
            entry["api_key_env"] = api_key_env
        if litellm_provider:
            entry["litellm_provider"] = litellm_provider
        models = {}
        if models_str:
            for m in models_str.split(","):
                m = m.strip()
                if m:
                    models[m] = {}
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
        height: 3;
        padding: 1 2;
        align: center middle;
    }

    #settings-footer Button {
        margin: 0 1;
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
            with Horizontal(id="settings-footer"):
                yield Static("", id="settings-error")
                yield Button("Save", variant="primary", id="settings-save")
                yield Button("Cancel", variant="default", id="settings-cancel")

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

        btn_row = Horizontal(classes="settings-row")
        btn_row.mount(Button("Add Provider", variant="primary", id="providers-add"))
        container.mount(btn_row)

    def _on_provider_action(self, alias: str, action: str) -> None:
        if action == "edit":
            entry = self._config.providers.get(alias, {})
            models = list(entry.get("models", {}).keys())
            initial = {
                "_alias": alias,
                **entry,
                "_models_str": ", ".join(models),
            }
            self.push_screen(
                NewProviderForm(f"Edit Provider: {alias}", initial),
                self._on_edit_provider_result,
            )
        elif action == "delete":
            self._config.providers.pop(alias, None)
            self._refresh_tab()

    def _on_edit_provider_result(self, result: dict | None) -> None:
        if result is not None:
            alias = result.pop("_alias")
            result.pop("_models_str", "")
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

        # ── Other buttons ────────────────────────────────
        if btn_id == "providers-add":
            self.push_screen(NewProviderForm("Add Provider"), self._on_add_provider_result)
        elif btn_id == "mcp-add":
            self.push_screen(NewMCPServerForm("Add MCP Server"), self._on_add_mcp_result)
        elif btn_id == "settings-save":
            self._do_save()
        elif btn_id == "settings-cancel":
            self.dismiss(None)

    def _on_add_provider_result(self, result: dict | None) -> None:
        if result is not None:
            alias = result.pop("_alias")
            result.pop("_models_str", None)
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

        btn_row = Horizontal(classes="settings-row")
        btn_row.mount(Button("Add MCP Server", variant="primary", id="mcp-add"))
        container.mount(btn_row)

    def _on_mcp_action(self, name: str, action: str) -> None:
        if action == "edit":
            entry = self._config.mcp_servers.get(name, {})
            initial = {"_name": name, **entry}
            self.push_screen(
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

    def _render_tier_models(self, container: ScrollableContainer) -> None:
        container.mount(Static("Tier Models", classes="settings-section-title"))
        container.mount(Static("Map each agent tier to a model (alias/model format).", classes="settings-list-item-detail"))

        tiers = ["tolo", "tainha", "papudo", "papaca"]
        for tier in tiers:
            current = self._config.tier_models.get(tier, self._config.default_model)
            row = Horizontal(classes="settings-row")
            row.mount(Label(f"  {tier}:", classes="settings-label"))
            inp = Input(
                value=current,
                placeholder="alias/model-id",
                id=f"tier-{tier}",
                classes="settings-input",
            )
            row.mount(inp)
            container.mount(row)

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
            row = Horizontal(classes="settings-row")
            row.mount(Label(f"  {label}:", classes="settings-label"))
            inp = Input(value=value, id=f"rag-{field_id}", classes="settings-input")
            row.mount(inp)
            container.mount(row)

        row = Horizontal(classes="settings-row")
        row.mount(Label("  Embedding Model:", classes="settings-label"))
        inp = Input(
            value=self._config.rag.embedding_model,
            id="rag-embedding_model",
            classes="settings-input",
        )
        row.mount(inp)
        container.mount(row)

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
            row = Horizontal(classes="settings-row")
            row.mount(Label(f"  {label}:", classes="settings-label"))
            inp = Input(value=value, id=f"gen-{field_id}", classes="settings-input")
            row.mount(inp)
            container.mount(row)

        row = Horizontal(classes="settings-row")
        row.mount(Label("  Theme:", classes="settings-label"))
        inp = Input(value=self._config.theme, id="gen-theme", classes="settings-input")
        row.mount(inp)
        container.mount(row)

        row = Horizontal(classes="settings-row")
        row.mount(Label("  Personality:", classes="settings-label"))
        inp = Input(value=self._config.personality, id="gen-personality", classes="settings-input")
        row.mount(inp)
        container.mount(row)

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
        """Read all input fields and produce a modified Config."""
        cfg = self._config

        # Tier models
        for tier in ["tolo", "tainha", "papudo", "papaca"]:
            inp = self.query_one(f"#tier-{tier}", Input)
            if inp:
                cfg.tier_models[tier] = inp.value.strip() or cfg.default_model

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

    def key_escape(self) -> None:
        self.dismiss(None)
