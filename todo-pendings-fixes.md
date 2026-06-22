# Code Review — Complete Findings Enumeration

**Date:** 2026-06-20
**Companion to:** `2026-06-20-full-sweep.md` (which summarizes themes + P0/P1 detail)
**Scope:** 55 subagent dispatches across `domain/`, `agents/`, `tools/`, `llm/`, `mcp/`, `rag/`, `screens/`

## Methodology

- Every finding from every reviewer's JSON return is listed below.
- **Dedup**: findings with matching `normalize(file) + line_bucket(±3) + normalize(title)` fingerprints are merged; contributing reviewers are unioned in the `Reviewers` column; highest severity + highest confidence retained.
- **Severity normalization**: reviewers used heterogeneous labels. Mapped: `critical → P0`, `high → P1`, `medium/warning → P2`, `low/observation → P3`.
- **Confidence** shown as the discrete anchor (`0|25|50|75|100`) from the skill schema.
- **Action** = `autofix_class` from the schema (`safe_auto|gated_auto|manual|advisory`).
- **Pre** = pre-existing (not introduced by a diff): `Y` or `N`.
- Residual risks and testing gaps (advisory-only, no severity) are listed in their own sections at the end.

**Raw dispatch count:** ~500 findings across 55 reviewers.
**After dedup:** below — organized by severity, then module, then file:line.

---

## P0 — Critical / Must fix (3 remaining)

> P0-1, P0-2, P0-3 moved to `README.md` → "P0 - Code Review".
> P0-4 through P0-8 have been **fixed** → moved to `todo-completed-fixes.md` (see `docs/plans/2026-06-20-p0-verification-and-fix-plan.md`).

| # | Module | File:Line | Title | Status |
|---|---|---|---|---|
| P0-1 | tools | tools/web_fetch.py:94 | SSRF — no private-IP/cloud-metadata filter, follow_redirects=True | → README TODO |
| P0-2 | tools | tools/exec.py:52 | Prompt-injection → shell RCE cascade (shell=True default, no sandbox) | → README TODO |
| P0-3 | tools | tools/file_manipulation.py:44 | No path confinement on read/write/edit/glob/replace_symbol | → README TODO |

## P1 — High-impact / Should fix (19 remaining)

> P1-1 through P1-11, P1-13 through P1-21, P1-24 through P1-53 → moved to `todo-completed-fixes.md` (fixed / false-positive).
> P1-12, P1-17, P1-22 moved to `README.md` → "P1 - Code Review".
> P1-23 remains pending (SSE/SSRF validation + read_resource trust).

### Correctness / Reliability

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P1-12 | llm | llm/client.py:483 | Outer while-True agent loop has no iteration cap — runaway tool loop burns tokens forever | reliability, adversarial | 75 | manual | N | → README TODO |
| P1-17 | tools | tools/subagent.py:64 | Subagent tier override lets the LLM escalate to most expensive model — no least-privilege enforcement | adversarial | 75 | manual | Y | → README TODO |
| P1-22 | mcp | mcp/__init__.py:130 | Project-level MCP server configs spawn arbitrary commands with no trust prompt or attestation → workspace-trust RCE | security | 75 | manual | N | → README TODO |
| P1-23 | mcp | mcp/__init__.py:128/187 | SSE MCP server URLs unvalidated; no scheme/host allowlist; read_resource trusts server-advertised URIs (file://, redirect-to-private-host) | adversarial, security | 100/75 | manual/gated_auto | N |

### Persistence replay

> P1-24 (false-positive), P1-25, P1-26 (false-positive), P1-27 → moved to `todo-completed-fixes.md`.

### Testing gaps (P1-class)

> P1-28 through P1-53 (all fixed / bugs fixed) → moved to `todo-completed-fixes.md`.

## P2 — Moderate (~70 deduplicated)

### domain/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-2 | domain | domain/session.py:65 | SubagentRecord.from_storage_dict direct private-attr access to SubagentManager._subagents | correctness, maintainability, kieran-python | 75 | manual | Y |

| P2-5 | domain | domain/session.py:133 | SessionManager.load doesn't verify loaded session.id matches requested session_id — keying by disk-supplied id | adversarial | 75 | advisory | Y |
| P2-7 | domain | domain/session.py:38 | Concurrentmut — Session.messages property rebuilds list every call during streaming → potential torn snapshot | adversarial | 50 | advisory | Y |
| P2-10 | domain | domain/todo.py:150 | TodoStore.from_storage_dict raises on unknown status — one bad todo aborts session recovery | reliability | 75 | manual | Y |
| P2-11 | domain | domain/agent.py:75 | Inconsistent serialization method naming across domain models (to_dict vs to_storage_dict vs both) | maintainability | 75 | gated_auto | Y |
| P2-12 | domain | domain/session.py:8 | Domain layer imports from agents layer — creating a domain↔agents circular dependency | maintainability | 50 | manual | Y |
| P2-13 | domain | domain/todo.py:162 | get_todo_store silently creates an orphan, unpersisted TodoStore when no store is bound | maintainability | 50 | manual | Y |
| P2-17 | domain | domain/todo.py:150 (alt) | TodoStore.from_storage_dict crashes whole session on a single corrupt status field | testing | 75 | manual | N |

| P2-20 | domain | domain/skill.py:49 | Skill.to_dict silently collapses references/scripts/assets to integer counts (lossy/asymmetric round-trip) | kieran-python | 75 | manual | Y |

### agents/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-21 | agents | agents/manager.py:246 | Exceptions in on_message UI callback silently swallowed, masking persistent mount failures | correctness, maintainability, kieran-python, reliability, agent-native | 75/100 | manual | Y |
| P2-22 | agents | agents/manager.py:236 | Cancelled on_state_change callbacks cannot reach UI if pane not yet mounted; RUNNING transition silently dropped | correctness | 60 | manual | Y |
| P2-25 | agents | agents/manager.py:153 | Restored records have no async_task and no on_message/on_state_change wiring; new spawns depend on sync_tabs re-wiring | correctness | 50 | manual | Y |
| P2-27 | agents | agents/manager.py:181 | cancel_all and cancel_running are near-duplicates with one observable difference (state filter + on_spawn clear) | maintainability, kieran-python | 75 | manual | Y |
| P2-28 | agents | agents/manager.py:233 | spawn()'s _run closure is a 50-line inline lifecycle that cannot be tested in isolation | maintainability | 50 | manual | Y |
| P2-29 | agents | agents/manager.py:201 | spawn() parameter 'agent_type' is misleading — it is actually the registry name lookup key | maintainability | 75 | manual | Y |
| P2-30 | agents | agents/manager.py:282 | Subagent task inherit parent's SubagentManager via ContextVar → lateral privilege escalation + sibling cancellation + unbounded sub-subagent recursion | adversarial, agent-native | 75/65 | manual | Y |
| P2-32 | agents | agents/manager.py:248 | No per-subagent iteration cap or wall-clock timeout — runaway LLM tool-call loop blocks parent indefinitely and grows record.messages unbounded | adversarial, reliability | 75 | manual | Y |
| P2-33 | agents | agents/manager.py:169 | SubagentManager._subagents never pruned — unbounded memory growth and O(N) sidebar rebuild per dynamic-system-prompt call | adversarial | 100 | manual | Y |
| P2-35 | agents | agents/manager.py:120 | Parallel subagent spawn + save_active race: tool_calls list reference snapshot via deepcopy may persist inconsistent message state | adversarial | 50 | advisory | Y |
| P2-37 | agents | agents/manager.py:294 | wait() has no timeout — a hung subagent stream blocks the caller indefinitely | reliability | 75 | manual | N |
| P2-38 | agents | agents/manager.py:243 | messages_mounted counter incremented before on_message awaits, drifts on failure | reliability | 75 | manual | N |
| P2-39 | agents | agents/manager.py:154 | from_storage_dict raises uncaught KeyError on data['id'] and ValueError on unknown state | reliability | 75 | manual | N |
| P2-40 | agents | agents/manager.py:236 | State-change callbacks fired as untracked fire-and-forget tasks — persistence can be lost on shutdown | reliability | 75 | manual | N |
| P2-41 | agents | agents/manager.py:102 | Truthiness check on float start/end_time mishandles epoch 0.0 and is non-idiomatic | kieran-python | 75 | manual | Y |
| P2-42 | agents | agents/manager.py:38 | get_subagent_manager() raises unhandled LookupError when ContextVar is unset | kieran-python | 75 | manual | Y |
| P2-43 | agents | agents/manager.py:32 | _fire_and_forget(coro: Coroutine) uses bare Coroutine with no parameters (typing) | kieran-python | 75 | manual | Y |
| P2-44 | agents | agents/manager.py:298 | get_states() returns list[dict] without value type parameters | kieran-python | 75 | manual | Y |
| P2-45 | agents | agents/manager.py:141 | from_storage_dict swallows all exceptions during agent registry lookup | kieran-python | 75 | manual | Y |
| P2-46 | agents | agents/manager.py:188 | cancel_all() mutates self.on_spawn — unrelated side effect on a cancel path | kieran-python | 75 | manual | Y |
| P2-47 | agents | agents/manager.py:279 | record.async_task = None # set below dead assignment plus timing race during on_spawn | kieran-python, maintainability, agent-native | 75/100 | manual | Y |
| P2-48 | agents | agents/manager.py:191 (alt) | cancel_all and cancel_running duplicate cancel logic — single non-terminal status set diverges silently | kieran-python | 50 | manual | Y |

### tools/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-53 | tools | tools/__init__.py:88 | Skill tool description bakes in the full skill registry, ignoring per-agent allowed_skills at execution time | correctness, agent-native, kieran-python | 75/80 | manual | Y |
| P2-54 | tools | tools/file_manipulation.py:221 | edit and write tools silently swallow post-write callback failures, masking stale AST/RAG indexes (contrast replace_symbol which surfaces them) | correctness, reliability, maintainability | 50/75 | gated_auto | Y |
| P2-55 | tools | tools/subagent.py:106 (alt) | wait_for_subagent in _TOOLS_WITHOUT_TIMEOUT can hang — no timeout path, no cancellation, msg_q backpressure deadlock | reliability | 80 | manual | N |
| P2-56 | tools | tools/rag.py:121 | RAG search returns indexed file bodies to the LLM → poisoning enables indirect prompt injection | adversarial | 50 | advisory | Y |
| P2-57 | tools | tools/mcp_resource.py:19 | read_mcp_resource trusts MCP server output and feeds it to the LLM with no scheme/content guard | adversarial | 50 | advisory | Y |
| P2-58 | tools | tools/todo.py:126 | Shared todo store has no ownership/authz — any agent can delete or rewrite another agent's tasks | adversarial | 50 | advisory | Y |
| P2-59 | tools | tools/web_fetch.py:11 | Module-level os.environ mutation on import (LITELLM_LOCAL_MODEL_COST_MAP) | adversarial, kieran-python | 75 | advisory | Y |
| P2-60 | tools | tools/exec.py:44 | execute_command uses hardcoded default working_directory='.' while sibling tools read defaults from get_config() | maintainability | 65 | manual | Y |
| P2-62 | tools | tools/ast.py:134 | _format_edit_result (ast.py) and _format_edit_result_content (file_manipulation.py) are duplicated formatters with divergent replace_all behavior | maintainability, kieran-python | 90/80 | manual | N |
| P2-63 | tools | tools/file_manipulation.py:221 (alt) | Post-write callback invocation duplicated and behaviorally inconsistent between ast and file_manipulation tools | maintainability | 85 | manual | N |
| P2-64 | tools | tools/ast.py:23 | _get_function_sent_hashes is unbounded module-global state with no reset path | maintainability, performance, kieran-python | 75/50 | manual | Y |
| P2-65 | tools | tools/__init__.py:84 | Inconsistent tool registration pattern: most tools module-level instances, three are builder functions called once | maintainability | 75 | manual | Y |
| P2-66 | tools | tools/ast.py:400 | Escape discipline inconsistent: ast.py mixes _xml_attr and escape in same element; file_manipulation.py escapes nothing in error text | maintainability | 60 | manual | Y |
| P2-68 | tools | tools/search.py:129 | Grep early-break on max_results leaves remaining as_completed tasks running (resource leak / awaited) | correctness, performance | 50 | gated_auto | Y |
| P2-71 | tools | tools/mcp_resource.py:28 | execute_read_mcp_resource has no error handling around manager.read_resource — test enshrines the bug | testing | 85 | manual | Y |
| P2-73 | tools | tests/test_rag_tools.py:85 | Weak assertion in test_rag_search_with_results — `assert "result" in result.content` is vacuous | testing | 75 | advisory | Y |
| P2-74 | tools | tests/test_file_manipulation.py:10 | Brittle implementation-coupled mock patches aiofiles.open with FakeAsyncFile that ignores mode semantics | testing | 60 | advisory | Y |
| P2-75 | tools | tools/web_fetch.py:235 | _choice_content duck-types litellm response as object and falls back to str(response) — leaks ModelResponse repr as the answer | kieran-python | 80 | manual | Y |
| P2-76 | tools | tools/file_manipulation.py:44 (alt) | execute_read_tool and execute_edit_tool open files without explicit UTF-8 encoding — write uses utf-8 but read uses default locale | kieran-python | 90 | manual | Y |
| P2-77 | tools | tools/exec.py:111 | Broad except Exception swallows all errors into ExecutorResult across the tools package — hides programming errors, removes traceback | kieran-python | 75 | manual | Y |

| P2-79 | tools | tools/ast.py:564 | hash_key uses full class_text as a dict key — unbounded memory growth; should hash via _fnv1a | kieran-python | 75 | manual | Y |
| P2-80 | tools | tools/skill.py:9 | ContextVar holds a mutable list — callers can mutate the shared allowed-skills set | kieran-python | 70 | manual | Y |
| P2-81 | tools | tools/__init__.py:88 (alt) | get_skill_tool builds a Tool at import-time via __init__.py without allowed_skills context | kieran-python | 70 | manual | Y |
| P2-82 | tools | tools/ast.py:183 | _find_extended_range contains a no-op ternary that silently skips single-line files | kieran-python | 75 | manual | Y |

### llm/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-83 | llm | llm/providers.py:236 | discover_provider_models caches empty failure result for the entire session, masking transient outages | correctness | 75 | advisory | Y |


| P2-88 | llm | llm/client.py:126 | THINKING replay as assistant content elevates tampered history into a privileged channel | adversarial | 50 | advisory | Y |
| P2-90 | llm | llm/client.py:36 | classify_error echoes raw provider exception text into the TUI — may include URLs, request bodies | kieran-python, adversarial | 50/25 | advisory | Y |
| P2-92 | llm | llm/providers.py:224 | Provider base_url is user-controlled and unvalidated — API key leaked via Authorization header to arbitrary host | security | 50 | manual | Y |
| P2-93 | llm | llm/static_system_prompt.py:9 | User-supplied system_prompt interpolated raw into <instructions> wrapper without escaping | security, kieran-python | 50 | advisory | Y |
| P2-94 | llm | llm/client.py:393 | Tool result content is appended to api_messages without any content framing — indirect prompt-injection sink | security | 50 | advisory | Y |
| P2-96 | llm | llm/client.py:402 | stream_response is a god function mixing 7+ responsibilities | maintainability | 75 | manual | Y |
| P2-97 | llm | llm/client.py:436 | Model-qualification helper `f'{provider}/{model}' if provider else model` is duplicated (client.py:436 + providers.py:144) | maintainability | 85 | manual | Y |
| P2-98 | llm | llm/providers.py:161 | resolve_embedding_ref returns a heterogeneous tuple union that callers must positionally destructure | maintainability | 75 | manual | Y |
| P2-99 | llm | llm/client.py:24 | _TOOLS_WITHOUT_TIMEOUT hardcodes tool identity in the LLM client layer | maintainability | 80 | manual | Y |
| P2-100 | llm | llm/client.py:483 | Loop-continuation decision relies on side-effect flag set in a sibling task (dual signaling via queues+Event) | maintainability | 60 | manual | Y |
| P2-101 | llm | llm/dynamic_system_prompt.py:7 | Cross-module imports: dynamic_system_prompt reaches into agents.manager and domain.todo internals | maintainability | 60 | manual | Y |
| P2-106 | llm | llm/client.py:86 | OpenAI chat-message shape passed around as bare dict[str, Any] — no TypedDict | kieran-python | 50 | manual | Y |
| P2-107 | llm | llm/client.py:179 | _execute_tool accesses typed dict fields without a TypedDict guard (tc["function"]["name"] KeyError-prone) | kieran-python | 50 | manual | Y |
| P2-108 | llm | llm/dynamic_system_prompt.py:13 | Module-level _TREE_CACHE global has no concurrency guard | kieran-python | 50 | manual | Y |
| P2-109 | llm | llm/providers.py:21 | Module import mutates process environment as a side effect (LITELLM_LOCAL_MODEL_COST_MAP) | kieran-python | 50 | manual | Y |
| P2-110 | llm | llm/client.py:420 | Deferred intra-function from fnmatch import fnmatch obscures dependencies (stdlib, no cycle excuse) | kieran-python | 50 | manual | Y |
| P2-111 | llm | llm/client.py:409 | stream_response configures a ContextVar from the caller's task without restoring it | kieran-python | 50 | manual | Y |

### mcp/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-112 | mcp | mcp/__init__.py:139 | Partial start failure leaves tools/sessions registered while status is reported 'failed' | correctness | 75 | manual | Y |
| P2-113 | mcp | mcp/__init__.py:176 (alt) | Inconsistent error propagation: not-connected returns ExecutorResult, but in-flight errors raise from call_tool/read_resource | correctness | 75 | manual | Y |
| P2-114 | mcp | mcp/__init__.py:101 | Concurrent shutdown races in-flight call_tool/read_resource: sessions torn down by exit-stack aclose while awaited | correctness, kieran-python | 50/75 | advisory | Y |
| P2-115 | mcp | mcp/__init__.py:152 | Resource URI mapping overwrites on collision: second server exposing the same URI shadows the first — malicious server can hijack reads | correctness, adversarial, security | 75 | manual | Y |
| P2-116 | mcp | mcp/__init__.py:113 | _await_runner cancel-after-3s can interrupt aclose() mid-teardown, re-introducing dangling-async-generator condition the CancelledError fix was written to prevent | reliability | 55 | manual | Y |
| P2-117 | mcp | mcp/__init__.py:139 (alt) | No server reconnection, liveness check, or stale-session detection after initial connect | reliability | 50 | manual | Y |
| P2-118 | mcp | mcp/mcp/__init__.py:168 | Per-server except Exception in _run swallows startup errors and continues; _server_status records only first 80 chars | reliability | 50 | manual | Y |
| P2-119 | mcp | mcp/__init__.py:144 | input_schema is stored in MCP tool registry entries but never read anywhere (dead speculative state) | maintainability | 90 | manual | Y |
| P2-120 | mcp | mcp/__init__.py:107 | _await_runner is misnamed — it signals stop first, then waits | maintainability | 80 | manual | Y |
| P2-121 | mcp | mcp/__init__.py:144 (alt) | Inconsistent registry entry shape between static tools ('tool','executor') and MCP tools ('tool','executor','input_schema') | maintainability | 80 | manual | Y |
| P2-122 | mcp | mcp/__init__.py:73 | MCPManager._run is a multi-responsibility lifecycle method mixing startup, idle, cancel-handling, and teardown | maintainability | 60 | manual | Y |
| P2-123 | mcp | mcp/__init__.py:45 | _server_status is an implicit string state-machine with no central definition of valid statuses | maintainability | 60 | manual | Y |
| P2-124 | mcp | mcp/__init__.py:188 | MCPManager.read_resource annotates parts: list[str] but appends item.blob (bytes) — type lie | maintainability | 75 | manual | Y |
| P2-125 | mcp | mcp/__init__.py:169/181 | Triple-duplicated 'manager unavailable / server not connected → error ExecutorResult' pattern | maintainability | 60 | manual | Y |
| P2-126 | mcp | mcp/schema.py:50 | make_mcp_executor typed Callable[..., Any], abandoning signature guarantees documented in docstring | maintainability, kieran-python | 55/75 | manual | Y |
| P2-127 | mcp | config.py:88 / mcp/example_server.py | Example MCP server is wired as a production default in user config | maintainability | 60 | manual | Y |
| P2-130 | mcp | mcp/__init__.py:176 (alt) | Tool-call failure semantics undefined and untested — call_tool does not catch exceptions | testing | 75 | manual | Y |
| P2-132 | mcp | mcp/__init__.py:128/187 (alt) | SSE MCP server URLs unvalidated — no scheme/host allowlist | security | 75 | gated_auto | Y |
| P2-134 | mcp | mcp/__init__.py:43 | Loose dict[str, dict] for known tool/server-status shapes; should use TypedDict/dataclass | kieran-python | 75 | manual | Y |
| P2-135 | mcp | mcp/__init__.py:51 | servers: dict[str, dict] config shape not modeled | kieran-python | 75 | manual | Y |
| P2-136 | mcp | mcp/__init__.py:79 | Tool-count prefix matching is fragile across underscore-bearing names | kieran-python | 75 | manual | Y |
| P2-137 | mcp | mcp/__init__.py:176 (alt) | call_tool inconsistency: missing-server returns error result, transport error raises | kieran-python | 50 | manual | Y |
| P2-138 | mcp | mcp/schema.py:9 | convert_mcp_tool annotates mcp_tool: Any instead of the real MCP type | kieran-python | 75 | manual | Y |

### rag/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-139 | rag | rag/indexer.py:184 | Test-embedding pre-check consumes an embedding API call/tokens on every index run | correctness | 75 | advisory | Y |
| P2-142 | rag | rag/store.py:143 | DB commit at upsert succeeds before vectors are written, leaving chunk/vector mismatch on _save_vectors failure | correctness | 50 | manual | Y |
| P2-146 | rag | rag/embedder.py:110 | asyncio.sleep retry without backoff in fastembed path; litellm retry doubles wait but ignores actual exception type | correctness | 50 | manual | Y |
| P2-147 | rag | rag/indexer.py:256 (alt) | Non-destructive upsert should use per-file upsert_file — eliminate the hash-restore band-aid AND the empty-file delete_by_file special-casing | maintainability | 75 | manual | Y |
| P2-148 | rag | rag/embedder.py:51 | Embedder dispatches on ad-hoc tuple arity (len(ref) == 2 vs 4), discarding then re-reading ref[0] | maintainability, kieran-python | 75 | manual | Y |
| P2-150 | rag | rag/indexer.py:28 | Module-global _indexing mutable flag used as a reentrancy guard (not async-safe; not project-scoped) | maintainability, kieran-python | 75 | manual | Y |
| P2-151 | rag | rag/store.py:100 | Duplicated chunk-insertion SQL between store.upsert and store.upsert_file | maintainability | 75 | manual | Y |
| P2-152 | rag | rag/indexer.py:54 (alt) | update_file duplicates the read→chunk→embed→store pipeline of _index_project_impl | maintainability | 50 | manual | Y |
| P2-153 | rag | rag/store.py:65 | init_db and _get_conn duplicate DB-recovery logic; init_db does not enable WAL | maintainability | 50 | manual | Y |
| P2-154 | rag | rag/indexer.py:46 | IndexStatus and StoreStatus are near-identical dataclasses; get_status just re-copies fields | maintainability | 50 | manual | Y |
| P2-155 | rag | rag/store.py:218 | Search reloads entire vectors.npy + all chunks from SQLite on every query, with list↔numpy round-trip (~280MB per query) | performance | 75 | manual | Y |
| P2-156 | rag | rag/chunker.py:105 | Chunker performs O(N) line/char scans inside the chunking loop → O(N²) on large files | performance, kieran-python | 75 | manual | Y |
| P2-157 | rag | rag/store.py:325 (alt) | upsert_file() rebuilds the entire vectors array for a single-file update on every editor save | performance | 75 | manual | Y |
| P2-158 | rag | rag/indexer.py:260 | Indexer opens a fresh SQLite connection per file for update_file_hash, in a loop | performance | 50 | manual | Y |
| P2-159 | rag | rag/indexer.py:257 (alt) | Full index_project flush wipes and re-inserts every chunk even on incremental runs | performance | 50 | manual | Y |
| P2-160 | rag | rag/embedder.py:81 | _embed_fastembed converts each vector to a Python list, then store re-converts to numpy | performance | 50 | manual | Y |
| P2-161 | rag | rag/indexer.py:241 | Per-file embed() calls prevent cross-file batching for API providers | performance | 50 | manual | Y |
| P2-171 | rag | rag/embedder.py:22 | _resolve_ref returns a discriminated-union-of-tuples and call sites dispatch on len(ref) — fragile, untyped shape | kieran-python | 75 | manual | Y |
| P2-172 | rag | rag/indexer.py:210 | Repeated silent except Exception: pass swallows hash-update and progress-callback errors with no diagnostic | kieran-python | 75 | manual | Y |
| P2-173 | rag | rag/indexer.py:105 | progress_callback: Callable | None carries no parameter contract | kieran-python | 75 | manual | Y |
| P2-174 | rag | rag/store.py:189 | _get_all_chunks returns bare list[dict] — untyped row shape permeates the caller | kieran-python | 75 | manual | Y |
| P2-175 | rag | rag/store.py:182 | _load_vectors calls self.clear() on ANY exception during np.load — destroys valid index for transient errors | kieran-python | 75 | manual | Y |
| P2-176 | rag | rag/store.py:100 (alt) | upsert is mis-named — it replaces the entire corpus, not an upsert by key | kieran-python | 75 | manual | Y |
| P2-177 | rag | rag/store.py:139 (alt) | DB commit and vectors.npy write are not atomic — partial-failure leaves inconsistent store | kieran-python | 75 | manual | Y |
| P2-178 | rag | rag/indexer.py:147 | asyncio.get_event_loop() used inconsistently — deprecated and replaced mid-function by cached loop | kieran-python | 75 | manual | Y |
| P2-179 | rag | rag/embedder.py:96 | from litellm import aembedding inside retry loop — re-imported on every attempt | kieran-python | 75 | manual | Y |
| P2-180 | rag | rag/embedder.py:17 | Class-level mutable cache dict typed as dict[str, object] — untyped value, shared across instances | kieran-python | 75 | manual | Y |
| P2-181 | rag | rag/chunker.py:69 | Chunker uses if remaining <= chunk_size: pass elif ... — dead branch + inverted logic obscures intent | kieran-python | 75 | manual | Y |
| P2-182 | rag | rag/indexer.py:184 (alt) | embed(["test"]) probe runs on every index — burns a paid API call before doing useful work | kieran-python | 75 | manual | Y |
| P2-183 | rag | rag/store.py:451 | import fnmatch is inside _match_pattern — re-resolved on every search call | kieran-python | 75 | manual | Y |
| P2-185 | rag | rag/store.py:73 | init_db and _get_conn rebuild DB without clearing stale vectors.npy, leaving inconsistent store | correctness | 50 | manual | Y |
| P2-186 | rag | rag/store.py:405 (alt) | delete_by_file leaves stale vectors when chunk table is empty after deletion | correctness | 45 | manual | Y |

### screens/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-190 | screens | screens/settings.py:19 | _list_fastembed_models swallows every exception with bare except Exception | kieran-python, agent-native | 75 | manual | Y |
| P2-191 | screens | screens/settings.py:219 | _add_model_entry wraps query_one(...).focus() in except Exception: pass (should narrow to NoMatches) | kieran-python | 75 | manual | Y |
| P2-192 | screens | screens/settings.py:267 | _remove_model_entry uses try/except Exception: continue to locate a row | kieran-python | 75 | manual | Y |
| P2-193 | screens | screens/settings.py:1311 | _update_tab_labels silently returns on except Exception | kieran-python | 75 | manual | Y |
| P2-194 | screens | screens/settings.py:128 | Model entries stored as list[dict] where a real dataclass is known | kieran-python | 75 | manual | Y |
| P2-195 | screens | screens/settings.py:815 | Tab rendering dispatched via getattr(self, f'_render_{tab_id.replace('-', '_')}') | kieran-python | 75 | manual | Y |
| P2-196 | screens | screens/settings.py:1314 | tab.label.plain.lstrip('● ').strip() strips any character in the set, not the prefix (bug) | kieran-python | 75 | manual | Y |
| P2-197 | screens | screens/settings.py:1258 | SettingsScreen._do_save mutates ConfigManager._instance directly (private attribute) | maintainability, kieran-python | 75 | manual | Y |
| P2-198 | screens | screens/picker.py:74 | OptionPicker.key_up moves focus to search only when highlighted is at index 0, skipping valid top-of-list case when highlighted is None | correctness | 50 | advisory | Y |
| P2-199 | screens | screens/picker.py:49 | OptionPicker treats empty-string PickerItem.id as 'no selection' and silently ignores it | correctness | 50 | advisory | Y |
| P2-200 | screens | screens/settings.py:1258 (alt) | ConfigManager._instance is reassigned before save(); an exception in save() leaves global singleton pointing at unsaved/invalid config | correctness | 75 | gated_auto | Y |
| P2-201 | screens | screens/settings.py:1082 | ● current-selection marker is duplicated across every picker-opening site | maintainability | 75 | manual | Y |
| P2-202 | screens | screens/settings.py:931 | _render_mcp_list re-implements _render_keyed_list with a different CSS class | maintainability | 75 | manual | Y |
| P2-203 | screens | screens/settings.py:24 | Multiple bare except Exception: pass swallow errors silently across screens module | maintainability | 75 | manual | Y |
| P2-204 | screens | screens/settings.py:764 | Config(**asdict(config)) shallow-copy incantation repeated 4 times | maintainability | 50 | manual | Y |
| P2-205 | screens | screens/settings.py:766 | _items_cache is state-shared between Providers and MCP keyword lists with no guard | maintainability | 50 | manual | Y |
| P2-206 | screens | screens/settings.py:28 (input_modal) | InputModal conform: Pressing Cancel vs submitting empty value both return None (indistinguishable) | correctness, testing | 50 | advisory | Y |
| P2-207 | screens | screens/settings.py:217 | Focus call after mounting model row is swallowed by bare except — newly added model rows are never focused | correctness | 75 | manual | Y |

### Cross-module

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-215 | tools+llm | tools/__init__.py:88 + llm/dynamic_system_prompt.py:30 | No MCP resource discovery — agent has read_mcp_resource but cannot learn which URIs exist; no <mcp_servers> block in dynamic prompt | agent-native (multi-module) | 90/80 | manual | Y |
| P2-216 | tools+llm | tools/__init__.py:88 | Skill tool description advertises every skill globally, ignoring per-agent allowed_skills (Context Parity defect) | agent-native (multi-module), correctness, kieran-python | 80/75 | manual | Y |
| P2-217 | llm | llm/client.py:415 + dynamic_system_prompt.py:30 | Dynamic system prompt omits RAG/AST index status and delegatable subagent types — Context Starvation | agent-native (multi-module) | 75 | manual | Y |
| P2-218 | tools+agents | tools/subagent.py:22 + agents/manager.py:201 | 'Subagents cannot create subagents' claim is enforced only by convention, not code | agent-native (multi-module), adversarial | 75 | manual | Y |
| P2-219 | tools+llm | tools/__init__.py:91 | No AST re-index tool — agent cannot force-rescan the symbol index | agent-native (multi-module) | 80 | manual | Y |
| P2-220 | screens+config | src/stupidex/config.py:388 | Agent-written config changes (via write/edit on config.json) are invisible to running session — ConfigManager singleton not invalidated | agent-native (multi-module) | 75 | manual | Y |
| P2-221 | screens | screens/settings.py:1258 + /src/stupidex/config.py | Settings validation/persist/live-apply logic is private to SettingsScreen._do_save, not a reusable primitive | agent-native (multi-module), maintainability | 75/85 | manual | Y |
| P2-222 | tools | tools/rag.py:43 | rag_index conflates three disjoint primitives behind an action enum (Decision Input) | agent-native (rag) | 72 | manual | Y |
| P2-223 | rag | rag/store.py:209 | No per-agent or per-scope filtering on RAG chunks — shared workspace is correct but undocumented to the agent | agent-native (rag) | 50 | advisory | Y |
| P2-224 | agents | agents/manager.py:263 | record.result is None if subagent ends with a tool call and no trailing TEXT — wait_for_subagent returns ambiguous empty block | agent-native (agents) | 60 | manual | Y |

## P3 — Low / User's discretion (~80 deduplicated)

### domain/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-1 | domain | domain/message.py:148 | TITLE branch in record_streamed_message is unreachable; THINKING content overwrites are not anchored to a turn | correctness | 50 | advisory | Y |
| P3-2 | domain | domain/message.py:44 | Message.to_dict coerces falsy content (including empty TOOL_RESULT content) to None — strict providers may reject | correctness, kieran-python | 50 | advisory | Y |
| P3-3 | domain | domain/chain.py:23 | Chain.start_time/end_time use time.monotonic(), producing meaningless elapsed values after session reload from disk | correctness, kieran-python, maintainability | 75 | manual | Y |
| P3-6 | domain | domain/todo.py:76 (alt) | TodoTask IDs use only 8 hex chars (32 bits) — collision-prone under parallel subagent creation | correctness | 75 | advisory | Y |
| P3-7 | domain | domain/todo.py:116 (alt) | TodoStore.update rejects field-only updates on terminal tasks; spec-vs-behavior mismatch with 'fields other than status' documentation | correctness | 75 | advisory | Y |
| P3-8 | domain | domain/todo.py:33 | VALID_TRANSITIONS omits self-transition for terminal statuses, but update() already short-circuits; OPEN→OPEN etc. is rejected when explicitly requested | correctness | 50 | advisory | Y |
| P3-9 | domain | domain/session.py:37 | Session.messages flattens chains but loses chain boundaries; tool_call/tool_result pairing across chain boundaries is not validated | correctness | 50 | advisory | Y |
| P3-10 | domain | domain/skill.py:49 (alt) | Skill.to_dict emits reference/script/asset COUNTS, not the resources themselves — fields unreadable from serialized form | correctness | 75 | advisory | Y |
| P3-11 | domain | domain/skill.py:32 (alt) | Skill.validate allows 'content', 'requires', 'scripts', 'references', 'assets' to be any type without validation | correctness | 75 | advisory | Y |
| P3-12 | domain | domain/tool.py:33 | Tool.to_dict always emits strict=true and additionalProperties flag; strict=false tools (e.g., MCP) may break provider schema validation | correctness | 50 | advisory | Y |
| P3-14 | domain | domain/message.py:78 (alt) | Usage(**data) in Message.from_storage_dict not resilient to schema drift — untested | testing | 50 | manual | N |
| P3-15 | domain | tests/test_streaming_messages.py:84 | test_record_streamed_message-updates_cumulative_snapshots asserts history length indirectly via list comprehension, not appended-flag returns | testing | 50 | advisory | N |
| P3-16 | domain | domain/todo.py:64 (alt) | Concurrent-access behavior of TodoStore and SessionManager is undocumented and untested | testing | 50 | advisory | N |
| P3-17 | domain | domain/agent.py:10 (alt) | Duplicated from_str pseudo-pattern across AgentTypes, ModelTier, TodoStatus | maintainability | 50 | advisory | Y |
| P3-18 | domain | domain/message.py:44 (alt) | Message.to_dict collapses falsy content to None for ALL roles, not just assistant tool-call-only turns | maintainability | 50 | manual | Y |
| P3-19 | domain | domain/todo.py:174 | Process-global mutable _todo_refresh_callback is inconsistent with the ContextVar pattern used elsewhere | maintainability, adversarial | 50 | manual | Y |
| P3-20 | domain | domain/session.py:89 | SessionManager.switch/delete/load shadow built-in id | kieran-python | 75 | manual | Y |
| P3-21 | domain | domain/session.py:102 | Three lazy from stupidex.storage import calls scattered in SessionManager methods | kieran-python | 50 | manual | Y |
| P3-22 | domain | domain/session.py:137 | session.py list_saved return type unparameterized | kieran-python | 75 | manual | Y |
| P3-23 | domain | domain/chain.py:91 | _reconcile_orphan_tool_results compares string against msg.role.value rather than the enum | kieran-python | 75 | manual | Y |
| P3-24 | domain | domain/agent.py:87 | Agent.from_dict uses hard-keyed [] lookups for required fields without a clear contract | kieran-python | 50 | manual | Y |
| P3-25 | domain | domain/tool.py:35 (alt) | Tool.to_dict returns bare dict with untyped properties accumulator | kieran-python | 75 | manual | Y |
| P3-26 | domain | domain/skill.py:14 | SkillResource.to_dict and Skill.to_dict return bare dict | kieran-python | 75 | manual | Y |
| P3-27 | domain | domain/skill.py:32 (alt) | Skill.validate returns a string instead of raising | kieran-python | 50 | manual | Y |
| P3-28 | domain | domain/todo.py:102 | TodoStore.update returns (task, error) tuple instead of raising or returning a Result type | kieran-python | 50 | manual | Y |
| P3-29 | domain | domain/todo.py:90 | TodoStore.list method shadows the built-in list | kieran-python | 50 | manual | Y |
| P3-30 | domain | domain/chain.py:32 (alt) | Chain.finish silently ignores status transitions when not RUNNING | kieran-python | 50 | manual | Y |
| P3-31 | domain | domain/chain.py:38 | Chain.format_elapsed produces wrong output for >=1h durations | kieran-python | 50 | manual | Y |
| P3-32 | domain | domain/message.py:98 (alt) | record_streamed_message is a function with implicit state mutation across many branches | kieran-python | 50 | manual | Y |
| P3-33 | domain | domain/chain.py:64 | Chain.from_storage_dict passes start_time=0.0 when missing, breaking elapsed | kieran-python | 50 | manual | Y |

### agents/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-34 | agents | agents/manager.py:298 (alt) | get_states() duplicates all_records() with a serialized view that has a single new reader need | maintainability | 50 | advisory | Y |
| P3-35 | agents | agents/manager.py:65 | format_subagent_attrs(id, type, ...) shadow builtins | kieran-python | 50 | manual | Y |
| P3-36 | agents | agents/manager.py:88 | Mutable state used as default for record.messages via field(default_factory=list) is correct, but Bundle of Callable fields with Any Coroutine loses type precision | kieran-python | 50 | manual | Y |

### tools/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-38 | tools | tools/web_fetch.py:11 (alt) | Module-level os.environ mutation on import in web_fetch | adversarial, kieran-python | 75 | advisory | Y |
| P3-39 | tools | tools/ast.py:957 | execute_rename_symbol recomputes _ident_chars set on every call | maintainability | 75 | manual | Y |
| P3-40 | tools | tools/subagent.py:53 (alt) | subagent.py parameter type shadows builtin and is called as positional keyword in registry | maintainability | 60 | manual | Y |
| P3-41 | tools | tools/skill.py:191 | Late local imports in skill.py obscure dependencies | maintainability | 50 | manual | Y |
| P3-42 | tools | tools/subagent.py:116 (alt) | Escape helper aliased to single-letter e inside loop bodies | kieran-python | 75 | manual | Y |
| P3-43 | tools | tools/ast.py:817 | execute_replace_symbol uses zip(..., strict=False) on known-equal-length lists | kieran-python | 75 | manual | Y |
| P3-44 | tools | tools/mcp_resource.py:25 (alt) | Inconsistent error propagation — read_resource not wrapped in try/except (test enshrines the bug) | testing | 85 | manual | Y |
| P3-45 | tools | tools/exec.py:79 | Post-SIGKILL execute_command swallows process.wait() with no deadline | reliability | 50 | manual | Y |
| P3-46 | tools | tools/ast.py:23 (alt) | _get_function_sent_hashes dict grows unbounded across long-lived sessions | performance | 50 | manual | Y |
| P3-47 | tools | tools/file_manipulation.py:44 (alt 2) | execute_read_tool reads the entire file to count total lines even when offset is high | performance | 50 | manual | Y |

### llm/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-48 | llm | llm/static_system_prompt.py:9 (alt) | Static system prompt interpolates system_prompt into XML without escaping | correctness, security | 25 | advisory | Y |
| P3-49 | llm | llm/static_system_prompt.py:7 | static_system_prompt f-string embeds leading indentation into the prompt | kieran-python | 50 | manual | Y |
| P3-50 | llm | llm/providers.py:151 (alt) | resolve_model_metadata and discover_provider_models swallow broad Exception (BLE001 noqa) | kieran-python | 50 | manual | Y |
| P3-51 | llm | llm/client.py:326 (alt) | _stream_task builds tool_calls list with magic index growth loop | kieran-python | 50 | manual | Y |
| P3-52 | llm | llm/client.py:34 | classify_error ordering silently treats ServiceUnavailableError before generic APIError | kieran-python | 50 | manual | Y |
| P3-53 | llm | llm/client.py:415 (alt) | Dynamic system prompt appended after history in api_messages | maintainability | 40 | manual | Y |
| P3-54 | llm | llm/client.py:235 | _stream_task closure-based state machine is hard to unit-test (7 nonlocals) | maintainability | 55 | manual | Y |
| P3-58 | llm | llm/client.py:74 (alt) | _validate_tool_args parameter lacks value-type annotation | kieran-python | 75 | manual | Y |
| P3-59 | llm | llm/client.py:295 (alt) | Streaming response object never closed via async ctx (residual after reliability fix) | maintainability | — | manual | N |
| P3-60 | llm | llm/providers.py:236 (alt) | Discovery cache permanently caches empty list on transient network failure | reliability | 75 | manual | Y |
| P3-61 | llm | llm/client.py:318 | Partial streamed assistant content persisted as a complete message (no marker) | reliability | 70 | manual | Y |
| P3-62 | llm | llm/client.py:391 | Executor appends tool result to api_messages before committing assistant — orphanable under stream error | reliability | 65 | manual | Y |
| P3-63 | llm | llm/client.py:374 | _stream_task finally: ready_q.put(None) on exception path may race executor's pending await | reliability | 60 | manual | Y |
| P3-64 | llm | llm/client.py:471 | Task gather in cancellation branch has no shield against re-cancellation | reliability | 55 | manual | Y |
| P3-65 | llm | llm/client.py:326 (alt 2) | Unclear if API clients (User/PairNone.turn) supportارية-planning transitions precondition (residual) | reliability | — | manual | N |

### mcp/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-66 | mcp | mcp/__init__.py:79 | Tool count uses prefix match startswith("mcp_{server_name}_"), over-counting when one server name is underscore-prefixed substring of another | correctness, kieran-python | 75 | manual | Y |
| P3-68 | mcp | mcp/__init__.py:152 (alt) | Resource URI mapping overwrites on collision (silent) — flYou earlier flagged this as P2-115; lower-tier variants | maintainability | 75 | manual | Y |
| P3-69 | mcp | mcp/example_server.py:65 | example_server read_resource declares Iterable[...] but returns a list | kieran-python | 50 | manual | Y |
| P3-70 | mcp | mcp/example_server.py:75 | Entry-point function named _run despite being the script's main | kieran-python | 25 | manual | Y |
| P3-71 | mcp | mcp/__init__.py:187 | # type: ignore[arg-type] on session.read_resource(uri) masks a real type mismatch (str vs AnyUrl) | kieran-python | 50 | manual | Y |
| P3-72 | mcp | mcp/__init__.py:125 | Deferred import of sibling schema module is unnecessary indirection | kieran-python | 50 | manual | Y |
| P3-73 | mcp | mcp/__init__.py:40 | MCPManager.__init__ missing return type annotation | kieran-python | 100 | manual | Y |
| P3-74 | mcp | mcp/__init__.py:124 | Unparameterized dict annotations on public/internal APIs | kieran-python | 100 | manual | Y |
| P3-75 | mcp | mcp/__init__.py:170/189 | No size/length bounds on tool output or resource contents: malicious server can return arbitrarily large content | adversarial | 100 | advisory | Y |

### rag/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-76 | rag | rag/indexer.py:279 | Incremental path with deleted files skews stats.files_deleted: deletes already-wiped rows from upsert | correctness | 55 | manual | Y |
| P3-80 | rag | rag/indexer.py:184 (alt 2) | Throwaway embed(["test"]) probe runs on every index_project call (advisory — comment documents the deliberate tradeoff) | performance | 25 | advisory | Y |

### screens/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-81 | screens | screens/settings.py:731 | default_model appears in two TAB_FIELDS buckets, causing duplicate dirty indicators and redundant diff work | correctness | 75 | manual | Y |
| P3-82 | screens | screens/settings.py:1334 | ConfirmScreen 'save_close' dismisses the confirm dialog before _do_save runs, so validation failure strands the user | correctness | 50 | advisory | Y |
| P3-83 | screens | screens/settings.py:28 (renamed) | Form classes named New* but they also edit existing entries | maintainability | 50 | manual | Y |
| P3-84 | screens | screens/settings.py:984 | TIERS is a magic list of opaque domain names with no docstring | maintainability | 60 | manual | Y |
| P3-85 | screens | screens/screens/__init__.py:1 | __init__.py for screens package is empty — no public API surface | maintainability | 50 | manual | Y |
| P3-87 | screens | screens/settings.py:453 (alt) | on_button_pressed in NewMCPServerForm treats any non-save button as cancel | maintainability | 50 | manual | Y |
| P3-88 | screens | screens/settings.py:124 | NewProviderForm._initial and NewMCPServerForm._initial typed as bare dict | kieran-python | 50 | manual | Y |
| P3-89 | screens | screens/picker.py:12 | PickerItem.id shadows the id builtin | kieran-python | 50 | manual | Y |
| P3-90 | screens | screens/settings.py:1253 | _do_save constructs error string with a generated bullet but never strips existing bullets | kieran-python | 50 | manual | Y |
| P3-91 | screens | screens/settings.py:931 (alt) | _render_mcp_list duplicates _render_keyed_list with a different action prefix (residual variance) | kieran-python | 50 | manual | Y |
| P3-95 | screens | screens/picker.py:24 | OptionPicker.compose is missing its return type annotation | project-standards | 100 | manual | Y |

## Residual Risks (advisory-only — no severity, no autofix action)

These are concerns surfaced by reviewers that don't fit the finding schema (no concrete code mutation proposed) but warrant inclusion in any work-planning discussion.

### domain/

- `record_streamed_message` assumes cumulative-snapshot streaming (overwrites state.content.content/state.thinking.content). If provider emits delta-style streaming, content is silently truncated. Cannot verify without the streaming layer.
- Chain persistence stores monotonic start_time on disk; long-running chains across restarts report nonsensical elapsed values. Cosmetic only unless timeout logic depends on (end-start) post-reload.
- `SubagentManager` is reconstructed via default_factory on `Session.from_storage_dict` before private `_subagents` backfill; if `__init__` acquires resources (event loops, locks), resources are created once for the session even if restoration subsequently fails.
- `todo._todo_refresh_callback` is a module-level global, not ContextVar. If two concurrent sessions or subagent loops share the module, the last setter wins.
- `_reconcile_orphan_tool_results` mutates messages in place from `Chain.from_storage_dict` on every load. If a session is loaded twice (preview + switch), the second load re-runs reconciliation — benign but wasteful.
- No exception classes are defined for domain errors. As error paths grow, a domain-specific exception hierarchy would beat `(None, str)` tuples and broad `except Exception`.
- `Message.to_dict` (OpenAI wire) vs `to_storage_dict` (disk) is an undocumented convention. A docstring on each would prevent callers from grabbing the wrong one.
- No `from_dict`/`from_storage_dict` symmetry on Skill, Tool, or SkillResource. If these are ever persisted, asymmetric API will force ad-hoc parsing at the call site.
- `time.monotonic()` values in `Chain.start_time`/`end_time` persisted to disk have no meaning across process restarts.
- `TodoTask.id` from `uuid.uuid4().hex[:8]` (32-bit) — collision risk real across thousands of tasks; create path does not check existing.

### agents/

- Subagent isolation depends entirely on AGENT.md frontmatter discipline (allowed_tools list). No structural barrier to a subagent whose tools include delegate_to_subagent gaining access to parent's manager.
- No global cap on subagent recursion depth, turns per subagent, or wall-clock time. A misbehaving model can compound cost and memory indefinitely.
- Persistence layer invariants enforced only for parent chain via `_reconcile_orphan_tool_results`; subagent-record path was omitted, so on-disk representation can drift from the consistency model future features assume.
- `_fire_and_forget` for state/spawn callbacks means the manager cannot deterministically guarantee UI/state propagation: callbacks may be silently dropped on event-loop shutdown.
- `record.async_task` is observable after `spawn()` await, but state may already be RUNNING/COMPLETED by then. Callers checking state synchronously must tolerate async mutation.
- `from_storage_dict` constructs `Agent(tier=PAPUDO)` even when original was higher tier. Restored subagents silently downgrade.

### tools/

- `execute_command` intentionally grants the agent full shell access as the running user. Risk materializes only if LLM is prompt-injected. Mitigation must come from confirmation gates and/or sandboxed runtime outside per-tool code; command allow/deny lists create false security.
- Tool result content fed to LLM. `exec.py` output, `file read`, MCP tool results returned largely verbatim (XML-wrapped only for ast/edit). Inherent injection vector for any agentic tool.
- `mcp_resource.execute_read_mcp_resource` delegates to MCP manager's `read_resource`; URI access gated by `_uri_map` (only URIs a connected server advertised). A malicious MCP server advertising `file://` URIs for sensitive files would expose them. Trust-boundary decision belongs to operator connecting MCP servers.
- `web_fetch` cache filename `_slug_from_url` (lines 151-161) derives a basename via `Path(slug).name[:80]` after stripping `..` — preventing path traversal in the cache write. No finding; recorded as confirmation.
- Skill content itself is untrusted text injected into the LLM context (`skill.py` lines 149-161). Malicious skill file could contain prompt-injection payloads, but skills are loaded from operator-controlled directories (trusted-input boundary, not code vulnerability).
- `post_write_callbacks` is a module-global mutable list that `file_manipulation`, `ast`, and `rag` all mutate at import; import ordering or duplicated registration across reloads could double-fire indexers, causing silent store corruption.

### llm/

- `_stream_task` mutates the shared `tool_calls` list reference after appending it to `api_messages` in `commit_assistant_with_tool_calls`. Intentional (executor reads from ready_q, list is fully populated before next completion round), but the invariant is load-bearing and undocumented.
- `stream_response` is an unbounded `while True` loop. Acceptable for an agent framework but worth a counter + warning log.
- `_TOOLS_WITHOUT_TIMEOUT` hardcoded allowlist. New long-running tools must be added by name; contract between Tool definitions and this set is implicit.
- `dynamic_system_prompt` reads `os.getcwd()` once per build; if process `chdir`s mid-session the cached tree is stale for up to `_TREE_TTL` (5s). Probably fine but undocumented.
- `providers.py` caches (`_metadata_cache`, `_discovery_cache`) are process-global and never expire. Long-running sessions that swap provider configs at runtime serve stale metadata.

### mcp/

- `BlobResourceContents.blob` (base64 per MCP spec) is appended verbatim into a `"\\n".join(parts)` of decoded text strings and returned as `content`/`display`. Large or binary blobs handed to LLM context unbounded.
- `call_tool`/`read_resource` return server-controlled text as both `display` and `content` with no escaping. Fine for TUI; if any future surface renders MCP output as markup/HTML, lack of escaping becomes injection sink.
- MCP SSE transport inherits SDK's default TLS handling (no pinning, no custom CA). For self-hosted servers behind a private CA there is no way to configure verification.
- `example_server.py` explicitly non-production but ships in package. If accidentally registered as stdio server, `echo` tool returns `arguments['message']` verbatim — framable as prompt-injection conduit if the agent later acts on it.

### rag/

- No upper bound on index size is enforced — vectors.npy grows linearly with total chunks and is loaded fully into RAM on every search. At very large scale (100k+ chunks, 1536-dim) this will OOM. Consider external ANN index (faiss, sqlite-vec) beyond a threshold.
- SQLite has no indexes on `chunks.file_path` — `DELETE FROM chunks WHERE file_path = ?` does full table scans.
- The shared class-level `_fastembed_cache` (embedder.py line 17) is process-global and never evicted; if multiple projects use different model configs the cache keeps all of them alive.

### screens/

- Textual `container.mount(widget)` is called synchronously in `on_mount` and `_render_*` callbacks. In newer Textual versions `mount` returns a `MountResult` and is not-awaited — works today, but if app upgrades Textual beyond 0.x, several call sites may need `await`.
- `_dirty_tab_names()` and dirty-tracking rely on `Config(**asdict(config))` round-trip equality. If a future field on Config is not round-trippable through `asdict` (e.g. a Path whose string round-trips but loses type), `_config_differs` will silently always return True (or False), gating the discard-confirmation prompt incorrectly.
- `_on_edit_provider_result` / `_on_add_provider_result` pop `_alias` without a default; a future refactor to NewProviderForm that forgets to set `_alias` would raise KeyError at dismiss rather than typed AttributeError at construction.

---

## Summary Statistics

| Tier | Count |
|---|---|
| P0 | 8 |
| P1 | 53 |
| P2 | 224 |
| P3 | 95 |
| **Total deduplicated findings** | **380** |
| Residual risks (advisory) | ~40 |
| Raw dispatch count (pre-dedup) | ~500 |

**By module (deduped findings):**

| Module | P0 | P1 | P2 | P3 | Total |
|---|---|---|---|---|---|
| `domain/` | 1 | 4 | 20 | 33 | 58 |
| `agents/` | 1 | 12 | 32 | 3 | 48 |
| `tools/` | 3 | 9 | 30 | 11 | 53 |
| `llm/` | 1 | 8 | 29 | 18 | 56 |
| `mcp/` | 1 | 3 | 27 | 10 | 41 |
| `rag/` | 1 | 6 | 49 | 5 | 61 |
| `screens/` | 0 | 1 | 27 | 15 | 43 |
| Cross-module | 0 | 10 | 10 | 0 | 20 |
| **Total** | **8** | **53** | **224** | **95** | **380** |

**By reviewer family (deduped contributions):**

| Reviewer | Modules assigned | Findings contributed (with cross-reviewer dupes) |
|---|---|---|
| ce-correctness-reviewer | 7 | 60 |
| ce-testing-reviewer | 7 | 75 |
| ce-maintainability-reviewer | 7 | 65 |
| ce-project-standards-reviewer | 7 | 5 |
| ce-agent-native-reviewer | 7 | 45 |
| ce-adversarial-reviewer | 5 | 45 |
| ce-security-reviewer | 3 | 14 |
| ce-reliability-reviewer | 5 | 35 |
| ce-performance-reviewer | 2 | 23 |
| ce-kieran-python-reviewer | 7 | 110 |

---

## Notes on This Enumeration

- **Pre-existing vs new:** the overwhelming majority are `pre_existing: true` because this is a full-codebase sweep, not a PR diff review.
- **Severity drift:** where 2+ reviewers flagged the same code region with different severity, the synthesis kept the higher severity and noted the disagreement in the title (e.g., "8-hex ID collision — flagged P1 by adversarial, P3 by correctness"). The `Reviewers` column shows all contributors.
- **Confidence anchors:** the discrete `0|25|50|75|100` from the skill schema. Synthesis applies cross-reviewer promotion (50→75, 75→100) for findings flagged by 2+ independent reviewers; the displayed value is the post-promotion anchor.
- **Action (`autofix_class`) distribution:**

| Action | Count |
|---|---|
| `safe_auto` (would be auto-applied in autofix mode) | ~25 |
| `gated_auto` (concrete fix but crosses behavior boundary) | ~70 |
| `manual` (downstream-resolver actionable work) | ~210 |
| `advisory` (FYI / design decision) | ~75 |

- **No `safe_auto` was applied** — this was a `mode:report-only` sweep. If a follow-up autofix pass is requested, the ~25 `safe_auto` findings should land first (lowest risk, no behavior change), then a targeted review of the `gated_auto` set.
- **Test-coverage findings dominate the P1 bucket** (24 of 53 P1s) — every reviewer in every module flagged gaps. This is systemic; a test-coverage sprint is the single highest-leverage follow-up after the P0 reliability/security fixes.

---

## Branch Review P3 Findings (2026-06-20)

> Source: `docs/code-review-reports/2026-06-20-branch-review.md` (multi-agent review of `fix/a_lot_of_things` branch, 11 reviewers)
> P0/P1/P2 from this review have been **fixed** (see `docs/plans/2026-06-20-003-fix-p012-branch-review-findings-plan.md`, units U1–U13).
> P3 and testing gaps below remain pending.

### P3 — Low-impact / minor

| # | Module | File:Line | Title | Reviewers | Conf | Pre |
|---|---|---|---|---|---|---|
| BR-P3-1 | agents | agents/manager.py:182 | `_cancel_record` double-fires `on_state_change(INTERRUPTED)` — `_cancel_record` fires it, then `_run`'s finally fires it again. Likely idempotent in practice. | correctness | 75 | N |
| BR-P3-2 | agents | agents/manager.py:161 | `from_storage_dict` end_time fallback yields `elapsed=0.0` for records persisted with `end_time=None`. | correctness | 50 | N |
| BR-P3-3 | mcp | mcp/__init__.py:211 | MCP shadow warning fires but later server still overwrites earlier binding — warning only, no prevention. | correctness | 50 | N |
| BR-P3-4 | tools | tools/search.py:243 | `execute_grep` `finally: task.cancel()` cannot cancel in-flight `run_in_executor` futures. Bounded by Semaphore(32) + `_PER_FILE_TIMEOUT`. | correctness | 50 | N |
| BR-P3-5 | tools | tools/exec.py:529 | `_read_bounded` over-trim when `rem > len(stdout_buf)` — `del stdout_buf[len(stdout_buf)-rem:]` removes last k elements (or all if k >= len). Fix: `rem = min(rem, len(stdout_buf))`. | correctness | 75 | N |
| BR-P3-6 | domain | domain/todo.py:91 | `TodoStore.create` `RuntimeError` after 8 retries may propagate uncaught. Verify the `todo_create` tool handler wraps it as `ExecutorResult`. | correctness | 50 | N |
| BR-P3-7 | tools | tools/skill.py:61 | `resolve_skill_dependencies` inner dedup now redundant with `_resolved` memoization. | correctness | 50 | N |
| BR-P3-8 | screens | screens/settings.py:856,981 | Provider/MCP rename-rejected early-returns without `_refresh_tab()`/`_mark_dirty()`. Fix: call them before the early return. | correctness | 75 | N |
| BR-P3-9 | llm | llm/client.py:148-150 | `os.open` / `os.fdopen` pairing can leak an fd if `fdopen` raises between allocation and `with`-block entry. | kieran-python | 50 | N |
| BR-P3-10 | llm | llm/client.py:416-437 | `_idle_timed_stream` calls `_safe_aclose` twice on the timeout path. | kieran-python | 50 | N |
| BR-P3-11 | tools | tools/skill.py:181-195 | Skill resource traversal guard TOCTOU between resolved-skill-dir check and resolved-subdir check. Microsecond window; requires FS attacker inside skill install dir. | adversarial | 50 | N |
| BR-P3-12 | llm | llm/client.py:498-532 | `commit_assistant_with_tool_calls` in-place filter mutates list concurrently iterated by executor task. Correct today because dict identity survives the filter (undocumented invariant). | adversarial | 50 | N |

### Testing Gaps (from branch review)

| # | File:Line | Gap |
|---|---|---|
| BR-TG-1 | tests/test_streaming_messages.py | Stream-idle retry path untested with partial delivery — no test simulates "3 chunks, then stalls > idle_timeout, then retries" and asserts no duplicate messages. |
| BR-TG-2 | tests/test_streaming_messages.py | `commit_assistant_with_tool_calls` all-malformed filter (empty `tool_calls`) untested — whether subsequent tool_call deltas become orphaned tool results. |
| BR-TG-3 | tests/test_mcp_startup_timeout.py:68 | MCP per-server timeout transport-enter hang (`fail_enter=True`) fixture defined but never driven. |
| BR-TG-4 | src/stupidex/tools/exec.py | `_read_bounded` overflow-trim stderr-only sub-branch untested. |
| BR-TG-5 | tests/test_streaming_messages.py | Streaming tests mutate module-global `llm_client._execute_tool` outside `patch` context (7 sites) — brittle under `pytest-timeout`. Use `with patch.object(...)`. |
| BR-TG-6 | tests/test_search.py | `test_max_results_does_not_leak_tasks` tolerates `+1` slack — admits exactly the leak the fix prevents. Tighten to `<= tasks_before`. |
| BR-TG-7 | src/stupidex/llm/client.py | `_maybe_offload_tool_output` `except OSError` cache-write failure branch untested. |
| BR-TG-8 | src/stupidex/domain/todo.py:91 | No test for `TodoStore.create` exhausting 8 retries — verify it propagates as `ExecutorResult`, not an unhandled exception. |
| BR-TG-9 | src/stupidex/config.py | `_check_positive_float` branches and float ENV cast not exercised. |
| BR-TG-10 | tests/test_settings_screen.py | Rename-rejected test doesn't assert pre-edit fields unchanged (P2-B related). |

### Residual Risks (advisory, from branch review)

| # | File | Risk |
|---|---|---|
| BR-RR-1 | llm/client.py:140-171 | Offload recovery depends on no workspace path confinement (P0-3 deferred). The pointer tells the LLM to `read` the cache file at `~/.stupidex/cache/...` — outside the workspace. The moment P0-3 path confinement lands, the agent will be silently unable to read its own offloaded outputs. |
| BR-RR-2 | llm/client.py:107-108 | `session_id` used as path component without uuid validation. Not exploitable across a trust boundary but defense-in-depth: validate uuid format at `load_session` boundary. |
| BR-RR-3 | llm/client.py:707 | `llm_stream_retries` config has no upper bound. `STUPIDEX_LLM_STREAM_RETRIES=30` -> max backoff `0.2*2^29s`. Add `min(retries, 10)`. |
| BR-RR-4 | llm/client.py | Overall agent-turn wall-clock still unbounded (P1-12 deferred). Idle timeout bounds per-chunk latency but a provider emitting one chunk every ~290s for hours won't trip it. |
| BR-RR-5 | llm/client.py:37-44 | `wait_for_subagent` still unbounded and timeout-exempt. A subagent wedged in a `_TOOLS_WITHOUT_TIMEOUT` tool hangs the parent indefinitely. Add a configurable timeout defaulting to `llm_stream_idle_timeout`. |
| BR-RR-6 | mcp/__init__.py:121 | MCP `start_all` implies parallel but is sequential. Worst case N x per_server_timeout (bounded by startup_timeout overall). Not a regression. |
| BR-RR-7 | docs/solutions/ | `docs/solutions/` is essentially empty. This branch's 15+ distinct topics are strong candidates for `/ce-compound` after the work lands. |
