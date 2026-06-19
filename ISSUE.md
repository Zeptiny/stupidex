## Bugs Found and Fixed

A full codebase audit revealed several issues, two critical. All have been fixed locally but are not yet committed.

### 🔴 Critical: `directory_tree()` ignore filtering is broken

**`src/stupidex/utils.py:115-117`**

The list comprehension logic is inverted — uses `or` instead of `and`:

```python
# Before (broken)
entries = [e for e in entries if e not in ignored or not e.startswith(".")]

# After (fixed)
entries = [e for e in entries if e not in ignored and not e.startswith(".")]
```

**Impact:** The `ignored_dirs` config (`.git`, `node_modules`, `__pycache__`, `venv`, `dist`, etc.) has **zero effect**. Every non-dot-prefixed entry passes through, bloating the dynamic system prompt sent to the LLM with build artifacts, virtualenvs, and cache directories.

---

### 🔴 Critical: `glob` tool crashes at runtime

**`src/stupidex/tools/file_manipulation.py:200-203`**

`glob.glob()` is called with a non-existent `include_hidden` parameter:

```python
# Before (crashes)
glob_module.glob(full_pattern, recursive=True, include_hidden=include_hidden)

# After (fixed)
results = glob_module.glob(full_pattern, recursive=True)
if not include_hidden:
    results = [m for m in results if not any(
        p.startswith('.') for p in Path(m).parts
    )]
```

**Impact:** Every call to the `glob` tool raises `TypeError: glob() got an unexpected keyword argument 'include_hidden'`.

---

### 🟡 Deprecated `asyncio.get_event_loop()`

**`src/stupidex/tools/file_manipulation.py:194`** and **`src/stupidex/tools/search.py:108`**

Both files use the deprecated `asyncio.get_event_loop()` instead of `asyncio.get_running_loop()`. The same file already uses `get_running_loop()` correctly in another location.

---

### 🟡 Typo in error message

**`src/stupidex/tools/file_manipulation.py:221`**

`"apttern"` → `"pattern"` in the glob error handler.

---

### 🟡 Unnecessary `pathlib` dependency

**`pyproject.toml`**

`pathlib` is listed as a dependency but has been part of the Python standard library since Python 3.4. The project requires Python ≥3.11.

---

### 🟢 Lint warning: unused loop variable

**`src/stupidex/widgets/command_picker.py:34`**

`desc` in `for cmd, desc in ...` was unused. Fixed to `_desc` (ruff B007).

---

### Additional Notes

- No test suite exists in the project. A basic test harness would help catch issues like the glob crash earlier.
- `list_models()` in `src/stupidex/llm/models.py` makes a synchronous HTTP call that blocks the event loop.
