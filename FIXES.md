# Fix Plan

## 5. Blocking `os.listdir()` in async event loop

**File:** `src/stupidex/llm/dynamic_system_prompt.py:14`

**Problem:** `directory_tree()` uses synchronous `os.listdir()` recursively and is called from `build_dynamic_system_prompt()`, which runs inside the async `stream_response()` generator on every tool-call loop iteration. This blocks the entire event loop.

**Fix:** Wrap the call in `run_in_executor` and add a short TTL cache:

```python
# dynamic_system_prompt.py
import asyncio
import time

_tree_cache: tuple[float, str] | None = None
_TREE_TTL = 5.0  # seconds

async def build_dynamic_system_prompt() -> Message:
    global _tree_cache
    cfg = get_config()
    cwd = os.getcwd()

    now = time.monotonic()
    if _tree_cache and _tree_cache[0] > now:
        tree = _tree_cache[1]
    else:
        loop = asyncio.get_running_loop()
        tree = await loop.run_in_executor(None, directory_tree, cwd, cfg.directory_tree_depth)
        _tree_cache = (now + _TREE_TTL, tree)

    # ... rest unchanged
```

Update `client.py` to `await` it:

```python
# client.py:27
[await build_dynamic_system_prompt().to_dict()]
```

---

## 7. Malformed tool-call arguments crash the stream

**File:** `src/stupidex/llm/client.py:127`

**Problem:** `json.loads(tc["function"]["arguments"])` with no try/except. A single malformed JSON from the LLM kills the entire conversation.

**Fix:**

```python
# client.py, inside the tool-call loop
for tc in tool_calls:
    name = tc["function"]["name"]
    try:
        args = json.loads(tc["function"]["arguments"])
    except json.JSONDecodeError:
        result = ExecutorResult(
            display=f"Invalid arguments for {name}",
            content=f"Error: Could not parse arguments for tool '{name}': invalid JSON.",
        )
    else:
        if name not in filtered_tools:
            result = ExecutorResult(
                display=f"Unknown tool: {name}",
                content=f"Error: tool '{name}' does not exist. Available tools: {', '.join(filtered_tools.keys())}",
            )
        else:
            executor = filtered_tools[name]["executor"]
            result = await executor(**args)

    yield Message(...)
    api_messages.append(...)
```

---

## 8. Fire-and-forget `create_task(on_spawn)` drops exceptions

**File:** `src/stupidex/agents/manager.py:168`

**Problem:** `asyncio.create_task(self.on_spawn(record))` has no exception handler. If the callback throws, the exception is silently lost and the subagent UI never appears.

**Fix:** Add a helper and use it for all fire-and-forget tasks:

```python
# agents/manager.py
import logging

log = logging.getLogger(__name__)

def _fire_and_forget(coro: Coroutine) -> asyncio.Task:
    """Create a task that logs exceptions instead of silently dropping them."""
    task = asyncio.create_task(coro)
    task.add_done_callback(_log_task_exception)
    return task

def _log_task_exception(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("Unhandled exception in background task: %s", exc, exc_info=exc)
```

Then replace the three call sites:

```python
# line 126
_fire_and_forget(record.on_state_change(record.state))

# line 164
_fire_and_forget(record.on_state_change(record.state))

# line 168
_fire_and_forget(self.on_spawn(record))
```

---

## 9. `read` tool loads entire file into memory

**File:** `src/stupidex/tools/file_manipulation.py:42`

**Problem:** `f.readlines()` loads the whole file, then slices. A 100MB file allocates 100MB to return 100 lines.

**Fix:** Use async line-by-line iteration with `islice`:

```python
import itertools

async def execute_read_tool(file_path: str, offset: int = 1, limit: int | None = None) -> ExecutorResult:
    if limit is None:
        limit = get_config().read_line_limit
    try:
        lines = []
        line_count = 0
        async with aiofiles.open(file_path) as f:
            # Count total lines and collect the window in one pass
            async for i, line in _async_enumerate(f, start=1):
                if i == offset:
                    line_count = i  # will keep updating
                if i >= offset and i < offset + limit:
                    lines.append((i, line.rstrip()))
                if i < offset:
                    line_count = i  # track for total
                # We still need total line count, so read everything
                # but only store the window
                line_count = i

        if offset > line_count:
            return ExecutorResult(display=f"Offset {offset} out of range", content=f"Offset of {offset} is greater than the file line count {line_count}")

        return ExecutorResult(
            display=f"Read {file_path} lines {offset}-{min(offset + limit - 1, line_count)}",
            content=f"Showing lines {offset}-{min(offset + limit - 1, line_count)} of {line_count}\n" +
            "\n".join(f"{i} | {line}" for i, line in lines)
        )
    except Exception as e:
        return ExecutorResult(display=f"Read error {file_path}", content=f"Error reading file {file_path}: {e}")
```

If the full line count isn't needed, we can skip it and just stream up to `offset + limit` lines, keeping memory bounded to the window size.

---

## 10. Unvalidated tool arguments passed to executors

**File:** `src/stupidex/llm/client.py:127`

**Problem:** `json.loads()` output is splatted directly as `**args` into executor functions. The LLM can pass unexpected keys, wrong types, or extra parameters.

**Fix:** Add a validation step against the tool's `ToolParameter` schema before dispatching:

```python
# In tools/__init__.py or a new tools/validators.py
def validate_tool_args(tool: Tool, args: dict) -> str | None:
    """Return error message if args are invalid, None if ok."""
    # Reject unknown parameters
    known = set(tool.parameters.properties.keys())
    unknown = set(args.keys()) - known
    if unknown:
        return f"Unknown parameters: {', '.join(unknown)}. Expected: {', '.join(known)}"

    # Check required
    for req in tool.parameters.required:
        if req not in args:
            return f"Missing required parameter: {req}"

    return None
```

Then in `client.py`:

```python
if name not in filtered_tools:
    result = ExecutorResult(...)
else:
    tool_def = filtered_tools[name]["tool"]
    error = validate_tool_args(tool_def, args)
    if error:
        result = ExecutorResult(display=f"Invalid args for {name}", content=f"Error: {error}")
    else:
        executor = filtered_tools[name]["executor"]
        result = await executor(**args)
```

---

## 13. Missing error handling around tool executor calls

**File:** `src/stupidex/llm/client.py:136`

**Problem:** If an executor raises an unhandled exception, the entire response stream crashes.

**Fix:** Wrap in try/except:

```python
executor = filtered_tools[name]["executor"]
try:
    result = await executor(**args)
except Exception as e:
    result = ExecutorResult(
        display=f"Error in {name}",
        content=f"Tool '{name}' raised an exception: {type(e).__name__}: {e}",
    )
```

---

## 14. Blocking synchronous HTTP in `list_models()`

**File:** `src/stupidex/llm/models.py:15`

**Problem:** Uses `httpx.Client` (sync) which blocks the TUI event loop when the `/model` command is invoked.

**Fix:** Make it async:

```python
# models.py
import httpx

async def list_models() -> list[Model]:
    cfg = get_config()
    async with httpx.AsyncClient(base_url=cfg.base_url) as client:
        response = await client.get("/models")
        response.raise_for_status()
        data = response.json()
        return [Model(id=model["id"]) for model in data["data"]]
```

Update caller in `session_commands.py`:

```python
# session_commands.py:50
case "/model":
    models = await list_models()  # already in async context
    # ...
```

---

## 16. app.py is a 543-line god object

**File:** `src/stupidex/app.py`

**Problem:** The `Stupidex` class handles: UI composition, streaming, interrupt state machine, subagent UI management, sidebar updates, token display, theme setup, and message mounting.

**Fix:** Extract into focused modules:

```
src/stupidex/
  app.py              (~200 lines) — compose, bindings, top-level actions
  streaming.py        (~80 lines)  — _stream_response logic
  interrupt.py        (~50 lines)  — InterruptState machine
  subagent_ui.py      (~150 lines) — all _on_subagent_* methods, tab sync, timer
```

`subagent_ui.py` example:

```python
class SubagentUIManager:
    def __init__(self, app: App) -> None:
        self.app = app
        self._widgets: dict[str, dict] = {}
        self._timer: Timer | None = None

    async def on_spawn(self, record: SubagentRecord) -> None: ...
    async def on_message(self, subagent_id: str, msg: Message) -> None: ...
    async def on_state_change(self, subagent_id: str, state: SubagentState) -> None: ...
    async def sync_tabs(self) -> None: ...
    def manage_timer(self) -> None: ...
```

Then `app.py` delegates:

```python
self._subagent_ui = SubagentUIManager(self)
self.sessions.active.subagent_manager.on_spawn = self._subagent_ui.on_spawn
```

---

## 18. app.py reaches into SubagentManager's private `_subagents` dict

**File:** `src/stupidex/app.py:113, 482, 528`

**Problem:** `self.sessions.active.subagent_manager._subagents.values()` accesses private internals in 3 places.

**Fix:** Add a public accessor to `SubagentManager`:

```python
# agents/manager.py
def all_records(self) -> list[SubagentRecord]:
    return list(self._subagents.values())
```

Replace in `app.py`:

```python
# line 113
return any(r.state not in terminal for r in self.sessions.active.subagent_manager.all_records())

# line 482
for record in manager.all_records():

# line 528
records = list(self.sessions.active.subagent_manager.all_records())
```

---

## 19. Subagent state icons duplicated between app.py and sidebar.py

**File:** `src/stupidex/app.py:492`, `src/stupidex/widgets/sidebar.py:419`

**Problem:** Both files define the same `{"pending": "◌", "running": "●", ...}` mapping independently.

**Fix:** Define once in `agents/manager.py`:

```python
# agents/manager.py
SUBAGENT_INDICATORS: dict[SubagentState, str] = {
    SubagentState.PENDING: "◌",
    SubagentState.RUNNING: "●",
    SubagentState.COMPLETED: "✓",
    SubagentState.FAILED: "✗",
    SubagentState.INTERRUPTED: "⊘",
}
```

Import and use in both files:

```python
from stupidex.agents.manager import SUBAGENT_INDICATORS

# app.py _tab_label
indicator = SUBAGENT_INDICATORS.get(record.state, "?")

# sidebar.py _get_indicator
return SUBAGENT_INDICATORS.get(state, "?")
```

---

## 20. Duplicated streaming widget dispatch for main and subagent messages

**File:** `src/stupidex/app.py:251` and `app.py:351`

**Problem:** `_stream_response()` and `_on_subagent_message()` have near-identical `if msg.type == THINKING / TOOL_CALL / TOOL_RESULT / else` dispatch logic with widget tracking.

**Fix:** Extract a shared handler:

```python
# app.py or a new streaming_widgets.py
from dataclasses import dataclass, field

@dataclass
class WidgetState:
    thinking: ThinkingMessageWidget | None = None
    content: AssistantMessageWidget | None = None
    temp: list[Static] = field(default_factory=list)

async def handle_streamed_message(
    container: Widget,
    msg: Message,
    state: WidgetState,
) -> None:
    if msg.type == MessageType.THINKING:
        if state.thinking is None:
            w = ThinkingMessageWidget(msg)
            await container.mount(w)
            state.thinking = w
            w.scroll_visible()
        else:
            state.thinking.update_content(msg.content)
    elif msg.type == MessageType.TOOL_CALL:
        tool_name = msg.metadata.get("tool_name", "")
        temp = Static(get_tool_action_label(tool_name), classes="temp-tool-message")
        await container.mount(temp)
        temp.scroll_visible()
        state.temp.append(temp)
        state.thinking = None
        state.content = None
    elif msg.type == MessageType.TOOL_RESULT:
        if state.temp:
            await state.temp.pop(0).remove()
        w = ToolResultMessageWidget(msg)
        await container.mount(w)
        w.scroll_visible()
        state.thinking = None
        state.content = None
    else:
        if state.content is None:
            if msg.content:
                w = AssistantMessageWidget(msg)
                await container.mount(w)
                state.content = w
                w.scroll_visible()
        else:
            if msg.content:
                state.content.update_content(msg.content)
```

Then both callers become:

```python
# _stream_response
ws = WidgetState()
async for msg in stream_response(...):
    # ... append to messages, handle usage ...
    await handle_streamed_message(container, msg, ws)

# _on_subagent_message
ws = widgets.setdefault(subagent_id, WidgetState().__dict__)
# or use the same WidgetState class
```

---

## 21. Subagent XML attribute string built identically in 4 places

**File:** `src/stupidex/tools/subagent.py:82, 122, 165`, `src/stupidex/llm/dynamic_system_prompt.py:30`

**Problem:** The same `f'id="{e(id)}" name="{e(name)}" ...'` pattern is repeated in 4 locations.

**Fix:** Extract a helper:

```python
# tools/subagent.py (or agents/manager.py)
from xml.sax.saxutils import escape

def format_subagent_attrs(
    id: str, name: str, type: str, state: str, elapsed: float | None
) -> str:
    e = escape
    attrs = f'id="{e(id)}" name="{e(name)}" type="{e(type)}" state="{e(state)}"'
    if elapsed is not None:
        attrs += f' elapsed="{elapsed}s"'
    return attrs
```

Replace all 4 call sites:

```python
# subagent.py:82
attrs = format_subagent_attrs(record.id, name, type, "pending", None)

# subagent.py:122
attrs = format_subagent_attrs(sid, record.name, record.type, status, elapsed)

# subagent.py:165
attrs = format_subagent_attrs(s["id"], s["name"], s["type"], s["state"], s["elapsed"])

# dynamic_system_prompt.py:30
attrs = format_subagent_attrs(s["id"], s["name"], s["type"], s["state"], s["elapsed"])
```

---

## 22. Config file created world-readable (644)

**File:** `src/stupidex/config.py:133`

**Problem:** `json.dump()` creates the file with default permissions (644), readable by all local users.

**Fix:** Set restrictive permissions after creation:

```python
# config.py, in ensure_home_config()
@classmethod
def ensure_home_config(cls) -> None:
    HOME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(str(HOME_CONFIG_DIR), 0o700)
    if not HOME_CONFIG_PATH.exists():
        defaults = Config()
        with open(HOME_CONFIG_PATH, "w") as f:
            json.dump(asdict(defaults), f, indent=2)
        os.chmod(str(HOME_CONFIG_PATH), 0o600)
    # ... rest unchanged
```

Also in `save()`:

```python
# config.py, in save()
os.replace(tmp, HOME_CONFIG_PATH)
os.chmod(str(HOME_CONFIG_PATH), 0o600)
```

---

## 23. `write` tool creates arbitrary directory trees

**File:** `src/stupidex/tools/file_manipulation.py:249`

**Problem:** `path.parent.mkdir(parents=True, exist_ok=True)` creates directories anywhere on the filesystem.

**Fix:** Constrain to project root (same mitigation as finding 2 — path canonicalization):

```python
import os

def _resolve_safe_path(file_path: str) -> Path | ExecutorResult:
    """Resolve path and ensure it stays within the project root."""
    project_root = Path.cwd().resolve()
    resolved = (project_root / file_path).resolve()
    if not str(resolved).startswith(str(project_root)):
        return ExecutorResult(
            display=f"Path outside project: {file_path}",
            content=f"Error: Path '{file_path}' resolves outside the project directory.",
        )
    return resolved

async def execute_write_tool(file_path: str, content: str) -> ExecutorResult:
    try:
        safe = _resolve_safe_path(file_path)
        if isinstance(safe, ExecutorResult):
            return safe
        path = safe
        path.parent.mkdir(parents=True, exist_ok=True)
        # ... rest unchanged
```

Apply the same `_resolve_safe_path` to `execute_read_tool`, `execute_edit_tool`, `execute_glob_tool`, and `execute_read_directory_tool`.

---

## 25. grep creates `set()` from `ignored_dirs` on every directory

**File:** `src/stupidex/tools/search.py:54`

**Problem:** `_should_skip_dir()` is called for every directory during `os.walk` and does `set(get_config().ignored_dirs)` each time.

**Fix:** Build the set once and pass it in:

```python
# search.py
async def execute_grep_tool(...) -> ExecutorResult:
    # ... at the start of the function
    ignored = frozenset(get_config().ignored_dirs)

    def _should_skip_dir(dirname: str) -> bool:
        if dirname in ignored:
            return True
        return bool(dirname.startswith("."))

    def _collect_files():
        collected = []
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if not _should_skip_dir(d)]
            # ...
```

This eliminates the per-directory `set()` allocation by closing over a single `frozenset`.

---

## 26. grep reads files sequentially

**File:** `src/stupidex/tools/search.py:111`

**Problem:** Files are processed one at a time in a sequential for-loop. Each file gets an async open, a binary check (which opens the file again), then line-by-line iteration.

**Fix:** Use bounded concurrency:

```python
import asyncio

async def execute_grep_tool(...) -> ExecutorResult:
    # ... setup unchanged ...

    semaphore = asyncio.Semaphore(32)

    async def search_file(file_path: str) -> list[str] | None:
        if await _is_binary(file_path):
            return None
        async with semaphore:
            try:
                relative_path = os.path.relpath(file_path, base_path)
                matches = []
                async with aiofiles.open(file_path, encoding="utf-8", errors="ignore") as f:
                    line_num = 0
                    async for line in f:
                        line_num += 1
                        if regex.search(line):
                            matches.append(f"{relative_path}:{line_num}: {line.rstrip()}")
                            if len(matches) + total_matches >= max_results:
                                break
                return matches
            except (PermissionError, OSError):
                return None

    tasks = [search_file(fp) for fp in file_paths]
    for coro in asyncio.as_completed(tasks):
        matches = await coro
        if matches:
            results.extend(matches)
            if len(results) >= max_results:
                break
```

Alternatively, move the entire scan into `run_in_executor` with a synchronous implementation for simplicity.

---

## 29. Dead code: `get_skill()`

**File:** `src/stupidex/skills/__init__.py:76`

**Problem:** `get_skill()` is defined but never imported or called anywhere.

**Fix:** Delete it:

```python
# Remove these lines (76-78):
def get_skill(name: str) -> Skill | None:
    registry = get_skill_registry()
    return registry.get(name)
```

---

## 30. Four near-identical picker screens

**File:** `src/stupidex/screens/*.py`

**Problem:** `ModelPicker`, `SessionPicker`, `PersonalityPicker`, and `ThemePicker` are nearly identical — they all compose an `OptionList`, handle `on_option_list_option_selected`, and dismiss.

**Fix:** Create a generic picker:

```python
# screens/picker.py
from dataclasses import dataclass
from textual.screen import Screen
from textual.widgets import OptionList
from textual.widgets.option_list import Option


@dataclass
class PickerItem:
    label: str
    id: str


class OptionPicker(Screen[str]):
    def __init__(self, items: list[PickerItem], title: str = "") -> None:
        super().__init__()
        self._items = items

    def compose(self):
        yield OptionList(*[Option(item.label, id=item.id) for item in self._items])

    def on_option_list_option_selected(self, event):
        self.dismiss(event.option.id)
```

Then each picker becomes a one-liner or thin wrapper:

```python
# session_commands.py
from stupidex.screens.picker import OptionPicker, PickerItem

case "/switch":
    sessions = list(app.sessions.sessions.values())
    items = [PickerItem(label=s.name, id=s.id) for s in sessions]
    async def on_picked(result: str | None):
        if result:
            app.sessions.switch(result)
            await app.rerender_all()
    app.push_screen(OptionPicker(items), on_picked)
```

Delete `model_picker.py`, `session_picker.py`, `personality_picker.py`, `theme_picker.py`.

---

## 31. `get_tool_registry()` rebuilds on every call

**File:** `src/stupidex/tools/__init__.py:33`

**Problem:** Every call to `get_tool_registry()` creates new `Tool` objects (including `build_delegate_tool()` and `build_skill_tool()` which trigger agent/skill registry loading).

**Fix:** Cache the result:

```python
# tools/__init__.py
_TOOL_REGISTRY: dict[str, dict] | None = None

def get_tool_registry() -> dict[str, dict]:
    global _TOOL_REGISTRY
    if _TOOL_REGISTRY is not None:
        return _TOOL_REGISTRY
    _TOOL_REGISTRY = {
        "read": {"tool": read_tool, "executor": execute_read_tool},
        # ... same entries ...
    }
    return _TOOL_REGISTRY

def reset_tool_registry() -> None:
    """Call after agents/skills change to rebuild on next access."""
    global _TOOL_REGISTRY
    _TOOL_REGISTRY = None
```

Call `reset_tool_registry()` in `load_agents()` and `load_skills()` after updating their registries.

---

## 32. Inconsistent config validation between theme and personality

**File:** `src/stupidex/config.py:186` vs `config.py:198`

**Problem:** `set_current_theme` validates via `registry.get(name)` (raises `ValueError`). `set_current_personality` validates by manually checking the global dict and building its own error message.

**Fix:** Add a `get_personality_registry()` function with a `.get()` method, matching the theme pattern:

```python
# personality/__init__.py
class PersonalityRegistry:
    def __init__(self) -> None:
        self._personalities: dict[str, str] = {}

    def load(self) -> None:
        # ... existing load_personalities logic ...
        self._personalities = personalities

    def get(self, name: str) -> str:
        if name not in self._personalities:
            raise ValueError(
                f"Unknown personality: '{name}'. "
                f"Available: {', '.join(sorted(self._personalities))}"
            )
        return self._personalities[name]

    def list_names(self) -> list[str]:
        return list(self._personalities.keys())

_REGISTRY: PersonalityRegistry | None = None

def get_personality_registry() -> PersonalityRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = PersonalityRegistry()
    return _REGISTRY
```

Then in `config.py`:

```python
def set_current_personality(name: str) -> None:
    from stupidex.personality import get_personality_registry
    get_personality_registry().get(name)  # raises ValueError for unknown
    cfg = get_config()
    cfg.personality = name
    ConfigManager.save()
```

---

## 33. Elapsed time calculation duplicated

**File:** `src/stupidex/agents/manager.py:185`, `src/stupidex/widgets/sidebar.py:428`

**Problem:** Both `SubagentManager.get_states()` and `Sidebar._get_elapsed()` compute elapsed time with the same logic.

**Fix:** Add a property to `SubagentRecord`:

```python
# agents/manager.py
@dataclass
class SubagentRecord:
    # ... existing fields ...

    @property
    def elapsed_seconds(self) -> float | None:
        if self.end_time:
            return round(self.end_time - self.start_time, 1)
        elif self.start_time:
            return round(time.time() - self.start_time, 1)
        return None
```

Use in both places:

```python
# manager.py get_states()
elapsed = record.elapsed_seconds

# sidebar.py _get_elapsed()
elapsed = record.elapsed_seconds
if elapsed is None:
    return None
if elapsed < 60:
    return f"{elapsed:.0f}s"
# ...
```

---

## 34. Error messages leak command strings and file paths

**File:** `src/stupidex/tools/exec.py:114`, `src/stupidex/tools/file_manipulation.py:58`

**Problem:** Error messages include the full command string, which may contain secrets (API keys, passwords in connection strings).

**Fix:** Sanitize error output:

```python
# exec.py
import re

def _sanitize_command_for_display(command: str) -> str:
    """Remove potential secrets from command for display."""
    # Mask anything that looks like a key/password/token
    sanitized = re.sub(r'(--?(?:password|token|key|secret|api[_-]?key)[= ])\S+', r'\1***', command, flags=re.IGNORECASE)
    sanitized = re.sub(r'(?<=://)[^:@]+:[^@]+@', '***:***@', sanitized)
    return sanitized

# In execute_command exception handler:
except Exception as e:
    safe_cmd = _sanitize_command_for_display(command)
    return ExecutorResult(
        display=f"{description} - Execution error",
        content=f"Error executing command '{safe_cmd}': {type(e).__name__}",
    )
```

For file operations, avoid leaking full paths in error messages — use just the filename or a truncated path.
