# Code Review — Completed Fixes

**Date:** 2026-06-20 (enumeration); items resolved 2026-06-20 through 2026-06-21.
**Source:** `todo-pendings-fixes.md`
**Scope:** Findings marked **FIXED**, **FALSE-POSITIVE**, or **NO-OP** moved out of the pending enumeration.
**Companion plans:**
- `docs/plans/2026-06-20-p0-verification-and-fix-plan.md`
- `docs/plans/2026-06-20-001-fix-p1-code-review-findings-plan.md`
- `docs/plans/2026-06-20-002-fix-p1-testing-gaps-plan.md`
- `docs/plans/2026-06-20-003-fix-p012-branch-review-findings-plan.md`

---

## P0 — Critical / Must fix

| # | Module | File:Line | Title | Status |
|---|---|---|---|---|
| P0-4 | rag | rag/store.py:100 / rag/indexer.py:256 | Incremental RAG re-index silently destroys unchanged files' chunks+vectors | **FIXED** |
| P0-5 | tools/llm | tools/subagent.py:106 + llm/client.py:24 | wait_for_subagent has no timeout AND is excluded from 60s tool timeout | **FIXED** (configurable stream idle-timeout + retries; root-trigger fix) |
| P0-6 | mcp | mcp/__init__.py:67/138 | MCP startup has no overall timeout — hung server blocks App.on_mount indefinitely | **FIXED** (configurable `mcp_startup_timeout` / `mcp_per_server_timeout`) |
| P0-7 | domain | domain/todo.py:64 | TodoStore state machine has zero direct test coverage | **FIXED** (`tests/test_todo_store.py`, 19 tests) |
| P0-8 | agents | agents/manager.py:201 | SubagentManager.spawn / _run subagent lifecycle has zero direct test coverage | **FIXED** (`tests/test_subagent_manager.py`, 19 tests) |

## P1 — High-impact / Should fix

### Correctness / Reliability

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P1-1 | agents | agents/manager.py:150 | Restored PENDING subagents never transition to terminal state (RUNNING→INTERRUPTED fix missed PENDING) — sidebar polls 1Hz forever **[FIXED — U9: PENDING→INTERRUPTED migration]** | correctness, maintainability, adversarial, kieran-python | 75/50 | gated_auto | N |
| P1-2 | agents | agents/manager.py:173 | Cancelling a not-yet-started _run task leaves record stuck in PENDING; saved state diverges silently **[FIXED — U9: cancel decoupled from task liveness]** | correctness | 60 | gated_auto | N |
| P1-3 | agents | agents/manager.py:281 | _run and on_spawn can concurrently mount the same streamed message (race, shared StreamWidgetState) **[FIXED — U9: per-subagent mount lock]** | correctness | 50 | manual | Y |
| P1-4 | llm | llm/client.py:438 | Context-window exhaustion — while-True re-submission loop has no token budget; large tool outputs blow context mid-turn **[FIXED — U8: tool output offload to cache file]** | correctness, adversarial, reliability | 75 | manual | Y |
| P1-5 | llm | llm/client.py:24 | wait_for_subagent and excluded tools can hang the stream indefinitely; msg_q backpressure deadlocks **[FIXED — P0-5 stream idle-timeout + retries]** | adversarial | 75 | manual | Y |
| P1-6 | llm | llm/client.py:348 | Interleaved tool_call index deltas cause a tool_call to be queued for execution multiple times → strict providers 400 **[FIXED — U10: enqueued_tool_calls dedup set]** | correctness | 50 | gated_auto | Y |
| P1-7 | llm | llm/client.py:338 | commit_assistant_with_tool_calls may emit a tool_call with empty id/name if first delta for an index lacks them → strict providers 400 **[FIXED — U10: filter empty id/name at commit]** | correctness, adversarial | 50/75 | gated_auto | Y |
| P1-8 | llm | llm/client.py:284 | Committed assistant message's content in api_messages diverges from persisted history if content deltas arrive after tool_calls started **[FIXED — U10: mutable content holder + no stacked TEXT]** | correctness | 50 | gated_auto | Y |
| P1-9 | llm | llm/client.py:439 | litellm.acompletion streaming call has no explicit timeout — provider stall blocks _stream_task forever **[FIXED — P0-5 stream idle-timeout]** | reliability | 90 | manual | N |
| P1-10 | llm | llm/client.py:295 | Streaming response object never closed via async context manager / aclose — connection pool exhausts under repeated escape **[FIXED — P0-5 _safe_aclose()]** | reliability | 80 | manual | N |
| P1-11 | llm | llm/client.py:467 | No retry, backoff, or jitter on transient LLM errors — single 429/502 aborts the entire agent turn **[FIXED — P0-5 exponential backoff + jitter]** | reliability | 85 | manual | N |
| P1-13 | tools | tools/exec.py:71 | Memory-exhaustion abuse — process.communicate() buffers unbounded stdout/stderr until timeout; yes/cat /dev/urandom OOM-kills the TUI **[FIXED — U4: incremental bounded reads, 1MB cap]** | adversarial, performance | 75/50 | manual | Y |
| P1-14 | tools | tools/file_manipulation.py:206 | edit/write tools are non-atomic and have a read-modify-write TOCTOU; concurrent subagents cause lost updates. Contrast ast.py's existing _atomic_write **[FIXED — U3: reuse _atomic_write]** | adversarial, reliability | 75/80 | manual | N |
| P1-15 | tools | tools/search.py:122 | Grep runs user-supplied regex synchronously in the event loop → ReDoS freezes the TUI. Naive glob→regex mishandles ?/[abc] **[FIXED — U5: executor + fnmatch.translate]** | adversarial, kieran-python | 75/85 | manual | Y |
| P1-16 | tools | tools/skill.py:41 | resolve_skill_dependencies false-positives circular dependency on diamond/shared transitive deps — shared _visited set across siblings **[FIXED — U2: separate stack vs resolved]** | correctness, kieran-python | 75/90 | gated_auto | Y |
| P1-18 | tools | tools/ast.py:679 | find_symbol_references reports 0-indexed line numbers, inconsistent with other AST tools (off-by-one line edits) **[FIXED — U1: +1 at display time]** | correctness | 75 | safe_auto | Y |
| P1-19 | mcp | mcp/schema.py:25 / mcp/__init__.py:144 | Registry name `mcp_{server_name}_{tool_name}` is not injective — silent executor shadowing **[FIXED — U7: mcp::server::tool separator + shadow warning]** | correctness, adversarial, kieran-python | 75/100 | manual | N |
| P1-20 | mcp | mcp/__init__.py:176 | call_tool silently discards all non-text content blocks (images, embedded resources) — agent gets empty string with no error **[FIXED — U6: partition blocks + placeholders + warning]** | correctness | 100 | safe_auto | N |
| P1-21 | mcp | mcp/__init__.py:193 | read_resource joins raw base64 BlobResourceContents.blob into text string — TypeError or garbled output at runtime **[FIXED (false-positive on TypeError; blob is str) — U6: readable placeholder]** | correctness, maintainability, kieran-python | 75/50 | manual | Y |

### Persistence replay

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P1-24 | domain | domain/message.py:143 | Shared-reference mutation: `state.content.tool_calls = msg.tool_calls` aliases caller's list into persisted history **[FALSE-POSITIVE — aliasing is intentional, documented at client.py:459-464; to_storage_dict deep-copies at persist time; each subagent's tool_calls list is independent]** | adversarial | 75 | gated_auto | Y |
| P1-25 | domain | domain/todo.py:76 | Cascade: 8-hex TodoTask ID collision (32-bit entropy) silently overwrites prior task under birthday pressure ~65k tasks **[FIXED — retry loop + RuntimeError on exhaustion]** | adversarial, correctness | 100/75 | manual | Y |
| P1-26 | domain | domain/todo.py:162 | _current_store ContextVar not re-bound on SessionManager.switch/load/create — tool handlers operate on stale store **[FALSE-POSITIVE — rebind was already at all transition sites; centralized into SessionManager._bind_context for maintainability]** | adversarial | 50 | manual | Y |
| P1-27 | domain | domain/message.py:78 | Deserialization fails open: Usage(**data['usage']) rejects forward-compatible extra fields, aborts entire Session load → data loss **[FIXED — explicit .get() extraction with 0 defaults]** | adversarial, reliability, testing | 75 | gated_auto | Y |

### Testing gaps (P1-class)

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P1-28 | domain | domain/skill.py:32 | Skill.validate() validation gate entirely untested — _NAME_PATTERN, _MAX_NAME_LEN, _MAX_DESC_LEN, leading/trailing-hyphen cases all enforcement branches **[FIXED — tests/test_skill_domain.py, 21 tests]** | testing | 100 | gated_auto | N |
| P1-29 | domain | domain/chain.py:71 | _reconcile_orphan_tool_results has no direct test for the mutation it performs on persisted message list **[FIXED — tests/test_chain.py, 14 tests]** | testing | 75 | gated_auto | N |
| P1-30 | domain | domain/message.py:40 | Message.to_dict() content=null contract for tool-call-only turns is untested (documented behavioral contract with strict providers) **[FIXED — tests/test_message.py TestMessageToDict, 10 tests]** | testing | 75 | gated_auto | N |
| P1-31 | llm | llm/client.py:438 | stream_response multi-turn tool-call loop is untested — the central agentic behavior (loop termination condition, api_messages growth) **[FIXED — tests/test_streaming_messages.py TestStreamResponseMultiTurn, 3 tests]** | testing | 75 | gated_auto | N |
| P1-32 | llm | llm/client.py:174 | _execute_tool error-path branches have zero direct tests (JSONDecodeError, args-not-a-dict, unknown tool, _validate_tool_args failure, TimeoutError, generic Exception) **[FIXED — tests/test_streaming_messages.py TestExecuteToolErrorPaths, 9 tests]** | testing | 75 | gated_auto | N |
| P1-33 | llm | llm/client.py:74 | _validate_tool_args has no tests despite branching logic (pure function, ideal unit-test target) **[FIXED — tests/test_streaming_messages.py TestValidateToolArgs, 4 tests]** | testing | 75 | gated_auto | N |
| P1-34 | llm | llm/dynamic_system_prompt.py:17 | build_dynamic_system_prompt has no tests — TTL cache, directory_tree execution, XML escaping of subagents/todos **[FIXED — tests/test_dynamic_system_prompt.py, 11 tests]** | testing | 75 | gated_auto | N |
| P1-35 | agents | agents/manager.py:150 | SubagentRecord persistence round-trip and RUNNING→INTERRUPTED migration untested — the persistence-replay entry point **[FIXED — U9 tests]** | testing | 100 | gated_auto | Y |
| P1-36 | agents | agents/manager.py:173 | cancel_one / cancel_all / cancel_running have no tests; behavioral differences unverifiable **[FIXED — U9 tests]** | testing | 100 | gated_auto | Y |
| P1-37 | agents | agents/manager.py:285 | wait() semantics — already-done and unknown-id handling untested **[FIXED — tests/test_subagent_manager.py TestWaitEdgeCases, 4 tests]** | testing | 100 | gated_auto | N |
| P1-38 | agents | agents/manager.py:246 | on_message and on_state_change callback failure-isolation behavior untested **[FIXED — tests/test_subagent_manager.py TestCallbackFailureIsolation, 4 tests]** | testing | 100 | gated_auto | Y |
| P1-39 | mcp | mcp/__init__.py:169 | MCPManager.call_tool has zero test coverage — both branches (session None + happy path joining block.text) **[FIXED — U6/U7 tests]** | testing | 75 | gated_auto | N |
| P1-40 | mcp | mcp/__init__.py:192 | read_resource BlobResourceContents branch untested (and behaviorally suspect) **[FIXED — U6 tests]** | testing | 75 | gated_auto | N |
| P1-41 | mcp | mcp/__init__.py:128 | SSE transport branch in _start_server is never exercised **[FIXED — tests/test_mcp_lifecycle.py TestSSETransport, 2 tests]** | testing | 75 | gated_auto | N |
| P1-42 | mcp | mcp/__init__.py:81 | Per-server failure recovery in _run is untested **[FIXED — tests/test_mcp_lifecycle.py TestStartAllErrorPropagation, 4 tests]** | testing | 75 | gated_auto | N |
| P1-43 | mcp | mcp/__init__.py:68 | start_all startup-error propagation branch untested **[FIXED — tests/test_mcp_lifecycle.py TestStartAllErrorPropagation, 4 tests]** | testing | 75 | gated_auto | N |
| P1-44 | tools | tools/exec.py:41 | execute_command has zero test coverage — timeout/SIGKILL, shell=False, nonzero exit, exception paths **[FIXED — U4 tests]** | testing | 90 | gated_auto | Y |
| P1-45 | tools | tools/search.py:52 | execute_grep_tool has zero test coverage — invalid regex, dir-not-found, binary skip, include_pattern translation, max_results truncation **[FIXED — U5 tests]** | testing | 90 | gated_auto | Y |
| P1-46 | tools | tools/skill.py:197 | execute_skill resource-read path traversal guard is security-critical and untested **[FIXED — tests/test_skill_tools.py TestResourceReadPathTraversal, 14 tests]** | testing | 90 | gated_auto | Y |
| P1-47 | tools | tools/subagent.py:53 | All four subagent executors (delegate, wait, list, interrupt) have zero test coverage **[FIXED — tests/test_subagent_tools.py, 15 tests]** | testing | 90 | gated_auto | Y |
| P1-48 | tools | tools/todo.py:112 | All four todo executors (create, update, list, delete) have zero test coverage **[FIXED — tests/test_todo_tools.py, 15 tests]** | testing | 90 | gated_auto | Y |
| P1-49 | tools | tools/file_manipulation.py:38 | execute_read_tool, execute_write_tool, execute_glob_tool, execute_read_directory_tool all untested; only execute_edit_tool has 2 tests **[FIXED — tests/test_file_manipulation.py, 15 new tests]** | testing | 90 | gated_auto | Y |
| P1-50 | rag | rag/indexer.py:54 | update_file (single-file re-index) is completely untested despite 5 branches **[FIXED — tests/test_rag_indexer.py TestUpdateFile, 6 tests]** | testing | 75 | gated_auto | Y |
| P1-51 | rag | rag/store.py:325 | RAGStore.upsert_file vector-rebuild logic is untested **[FIXED — tests/test_rag_store.py TestUpsertFileVectorRebuild, 7 tests]** | testing | 75 | gated_auto | Y |
| P1-52 | rag | rag/indexer.py:280 | force=True re-index does not remove deleted files — branch and behavior untested **[FIXED — tests/test_rag_indexer.py TestForceReindexDeletedFiles, 4 tests; bug fixed: force=True now removes stale chunks]** | testing | 75 | gated_auto | Y |
| P1-53 | screens | screens/settings.py:852 | Provider/MCP rename flow silently keeps old key untested **[FIXED — tests/test_settings_screen.py, 10 tests; bug fixed: rename to existing alias now rejected with warning]** | testing, correctness | 80/75 | gated_auto | Y |

## P2 — Moderate

### domain/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-1 | domain | domain/session.py:95 | SessionManager.delete mutates in-memory state before disk deletion; partial failure leaves ghost session **[FIXED — Batch B 2026-06-21: disk-first delete ordering]** | correctness, reliability | 75 | gated_auto | Y |
| P2-19 | domain | domain/message.py:38 | tool_calls modeled as list[dict[str, Any]] instead of a dataclass **[WONTFIX — Batch 1 execution 2026-06-21: dataclass extraction contradicts the dict pass-through design (storage==wire==in-memory==working buffer, zero conversion boundaries); adding a dataclass adds conversion layers on the path U1/U2/U3 just stabilized, plus ~30 test-site churn. A TypedDict overlay would fit; a dataclass does not.]** | kieran-python | 75 | manual | Y |
| P2-3 | domain | domain/chain.py:90 | _reconcile_orphan_tool_results does not deduplicate repeated TOOL_RESULT with same tool_call_id **[FIXED — Batch 1 2026-06-21: added seen_result_ids set; duplicates dropped at replay to prevent strict-provider HTTP 400]** | correctness | 50 | advisory | Y |
| P2-85 | llm | llm/client.py:326 | Streaming desync: missing tc_delta.index (None) causes TypeError mid-stream, aborting turn with partial tool calls already on disk **[FIXED — Batch 1 2026-06-21: coerce None to len(tool_calls) before the while-loop; Anthropic/Bedrock adapters with index-less deltas no longer crash mid-stream]** | adversarial | 50 | manual | Y |
| P2-87 | llm | llm/client.py:284 | Shared mutable tool_calls list: executor reads tc['id'] before stream finalizes it, producing tool_call_id mismatch on replay **[FIXED — Batch 1 2026-06-21: copy.deepcopy(tc) in maybe_enqueue snapshots at transition time; executor no longer races with the stream loop's in-place += on function.arguments]** | adversarial | 50 | manual | Y |
| P2-4 | domain | domain/message.py:110 | record_streamed_message silently discards TOOL_CALL MessageType messages, risking orphaned TOOL_RESULT on replay **[FALSE-POSITIVE — Batch 1 verification 2026-06-21: TOOL_CALL MessageType is a display-only "Calling tool: X" notification emitted without tool_calls; actual tool_calls persisted via MessageType.TEXT anchoring at message.py:179-184]** | correctness | 50 | advisory | Y |
| P2-6 | domain | domain/message.py:100 | THINKING-typed stream chunk silently drops tool_calls, orphans subsequent TOOL_RESULT and triggers reconcile-prune **[FALSE-POSITIVE — Batch 1 verification 2026-06-21: producer never sets tool_calls on THINKING messages; tool_calls only emitted via commit_assistant_with_tool_calls on TEXT-typed Message at client.py:545-550]** | adversarial | 50 | advisory | Y |
| P2-84 | llm | llm/client.py:415 | Dynamic system prompt is appended as a trailing system message after the full conversation history **[INTENDED DESIGN — Batch 1 verification 2026-06-21: trailing position is by design; not a defect]** | correctness | 50 | advisory | Y |
| P2-86 | llm | llm/client.py:326 (alt) | tool_call_id empty-string collision: provider deltas without id produce duplicate tool_call_ids that strict providers 400 on **[FALSE-POSITIVE — Batch 1 verification 2026-06-21: commit_assistant_with_tool_calls filter (client.py:528-531) drops entries lacking id; maybe_enqueue (client.py:583) refuses to enqueue empty-id tool_calls; empty-id entries never reach persistence or execution]** | adversarial | 75 | manual | Y |
| P2-8 | domain | domain/session.py:56 | Chain deserialization in Session.from_storage_dict not individually guarded — one corrupt chain aborts whole session load **[FIXED — Batch B 2026-06-21: per-chain try/except]** | reliability | 75 | gated_auto | Y |
| P2-9 | domain | domain/message.py:76 | Message.from_storage_dict raises on unknown role/type or usage schema drift — single malformed message kills session recovery **[FIXED — Batch B 2026-06-21: enum tolerance, role→SYSTEM, type→TEXT, metadata warning]** | reliability | 75 | gated_auto | Y |
| P2-14 | domain | domain/chain.py:32 | Chain.finish() idempotency guard and format_elapsed boundaries untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | N |
| P2-15 | domain | domain/agent.py:10 | AgentTypes/ModelTier from_str error paths and Agent dict round-trip untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | N |
| P2-16 | domain | domain/session.py:40 | Session.to/from_storage_dict round-trip and corrupt-subagent resilience untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | N |
| P2-18 | domain | domain/tool.py:35 | Tool.to_dict() OpenAI function-schema serialization untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | N |

### agents/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-23 | agents | agents/manager.py:101 | Restored INTERRUPTED records with end_time=None produce forever-growing elapsed_seconds **[FIXED — Batch B 2026-06-21: end_time/start_time normalization on INTERRUPTED migration]** | correctness | 75 | gated_auto | Y |
| P2-24 | agents | agents/manager.py:141 | from_storage_dict outer except replays the same failing AgentTypes.from_str call as the try block **[FIXED — Batch B 2026-06-21: _restore_agent helper with isolated AgentTypes.from_str try]** | correctness | 75 | gated_auto | Y |
| P2-26 | agents | agents/manager.py:124 | Duplicated fallback Agent construction in SubagentRecord.from_storage_dict; try/except is dead **[FIXED — Batch B 2026-06-21: consolidated into _restore_agent helper]** | maintainability, kieran-python | 75 | gated_auto | Y |
| P2-31 | agents | agents/manager.py:163 | SubagentRecord.from_storage_dict bypasses orphan reconciliation that recent fix (commit 406e032) applied only to parent chains **[FIXED — Batch B 2026-06-21: _reconcile_orphan_tool_results now applied to subagent messages]** | adversarial | 75 | gated_auto | Y |
| P2-34 | agents | agents/manager.py:191 | cancel_running/cancel_one return before cancellation cleanup completes → fire-and-forget on_state_change(INTERRUPTED) races UI teardown **[FIXED — Batch B 2026-06-21: flush_state_callbacks() primitive + async caller updates]** | adversarial | 75 | gated_auto | Y |
| P2-36 | agents | agents/manager.py:150 (alt) | Persistence replay silently accepts state=PENDING → restored record stays non-terminal forever → _tick_timer runs indefinitely **[FIXED — duplicate of P1-1, characterized in Batch B 2026-06-21: PENDING→INTERRUPTED migration verified by characterization test]** | adversarial | 50 | gated_auto | Y |
| P2-49 | agents | agents/manager.py:63 | format_subagent_attrs escape + elapsed branches untested; security boundary for XML injection **[FIXED — Batch C 2026-06-21: `"` now escaped via `entities={'"': '&quot;'}`]** | testing | 100 | gated_auto | Y |
| P2-50 | agents | agents/manager.py:101 (alt) | elapsed_seconds property has three branches, none tested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 100 | gated_auto | Y |
| P2-51 | agents | agents/manager.py:263 | Empty/blank content handling in result assignment not pinned by test **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-52 | agents | agents/manager.py:188 (alt) | cancel_all clearing on_spawn=None is an unobserved side effect with no test **[FIXED — testing-gap sweep 2026-06-21]** | testing | 100 | gated_auto | Y |

### tools/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-61 | tools | tools/ast.py:61 | Duplicated XML helper functions across ast.py and file_manipulation.py — _xml_attr, _cdata_text, _count_diff_changes **[FIXED — safe_auto sweep 2026-06-21]** | maintainability, kieran-python | 100/80 | safe_auto | N |
| P2-67 | tools | tools/file_manipulation.py:307 | glob_tool description claims results sorted by modification time but code sorts alphabetically **[FIXED — safe_auto sweep 2026-06-21]** | correctness | 75 | safe_auto | Y |
| P2-69 | tools | tools/file_manipulation.py:38 (alt) | execute_read_tool treats offset=0 silently and lacks validation for non-positive offset/limit **[FIXED — safe_auto sweep 2026-06-21]** | correctness | 50 | safe_auto | Y |
| P2-70 | tools | tools/file_manipulation.py:162 | execute_edit_tool replace_all=true branch, multiple_matches branch, and generic Exception error path untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 80 | gated_auto | Y |
| P2-72 | tools | tools/rag.py:107 | execute_rag_search ValueError branch and generic Exception embedding branch untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |

### llm/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-89 | llm | llm/dynamic_system_prompt.py:22 | Dynamic system prompt cache keys on time but not cwd — stale directory tree after chdir within 5s window **[FIXED — Batch C 2026-06-21: cache now keys on (cwd, expiry, tree)]** | adversarial | 75 | gated_auto | Y |
| P2-91 | llm | llm/dynamic_system_prompt.py:32 | Directory tree and cwd injected raw into system prompt — file/path names can break XML framing **[FIXED — Batch C 2026-06-21: cwd and tree now XML-escaped]** | security | 75 | gated_auto | Y |
| P2-95 | llm | llm/client.py:467 | Redundant except branch: CancelledError is fully subsumed by BaseException (byte-identical bodies) **[FIXED — safe_auto sweep 2026-06-21]** | maintainability | 95 | safe_auto | Y |
| P2-102 | llm | llm/static_system_prompt.py:22 | build_static_system_prompt and _get_os_info OS branches untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-103 | llm | llm/client.py:56 | classify_error missing BadGatewayError branch test **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-104 | llm | llm/client.py:114 | _history_to_api_messages THINKING-between-tool_calls-and-result invariant untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-105 | llm | llm/client.py:210 | _TOOLS_WITHOUT_TIMEOUT bypass branch in _execute_tool untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |

### mcp/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-128 | mcp | mcp/__init__.py:113 (alt) | _await_runner timeout/cancel branch untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-129 | mcp | mcp/example_server.py:44 | example_server.py has zero test coverage despite being the MCP integration entrypoint **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-131 | mcp | mcp/schema.py:30 | convert_mcp_tool defaults missing type in property schema to "string", misrepresenting schema to the LLM **[FIXED — safe_auto sweep 2026-06-21]** | correctness | 75 | safe_auto | Y |
| P2-133 | mcp | mcp/__init__.py:82 | Truncated exception text stored in _server_status may leak command/path/env fragments locally **[FIXED — safe_auto sweep 2026-06-21]** | security | 50 | safe_auto | Y |

### rag/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-140 | rag | rag/store.py:178 | np.load on vectors file does not set allow_pickle=False — malicious pickle RCE primitive **[FIXED — safe_auto sweep 2026-06-21]** | correctness, security | 60 | safe_auto | Y |
| P2-141 | rag | rag/store.py:325 | upsert_file appends new embeddings in arbitrary order when a file's chunks interleave with others — vector/content mismatch **[FIXED — Batch C 2026-06-21: uses `_chunk_ids_for_file` to scope new embeddings]** | correctness | 60 | gated_auto | Y |
| P2-143 | rag | rag/chunker.py:85 | Chunker end_line off-by-one when chunk boundary aligns exactly with a newline **[FIXED — Batch C 2026-06-21: check `content[end_char - 1]` not `content[end_char]`]** | correctness | 75 | gated_auto | Y |
| P2-144 | rag | rag/indexer.py:87 | update_file fails to persist new hash after embedding failure, freezing the file out of future re-index **[FALSE-POSITIVE — Batch C 2026-06-21: old hash ≠ new content hash triggers re-index on next `index_project` run]** | correctness | 65 | gated_auto | Y |
| P2-145 | rag | rag/indexer.py:156 | Indexing with empty discovered-files result wipes the existing index **[FIXED — Batch C 2026-06-21: removed `store.clear()`, now just touches `last_indexed`]** | correctness | 70 | gated_auto | Y |
| P2-149 | rag | rag/indexer.py:161 | Dead assignment: Embedder constructed in empty-files branch of _index_project_impl is never used **[FIXED — safe_auto sweep 2026-06-21]** | maintainability | 100 | safe_auto | Y |
| P2-162 | rag | rag/store.py:236 | search dimension-mismatch error path is untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-163 | rag | rag/store.py:226 | search vector/chunk count mismatch (stale-index truncation) is untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-164 | rag | rag/indexer.py:190 | Embedding pre-check unexpected format branch in index_project is untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-165 | rag | rag/embedder.py:105 | Litellm ImportError branch in _embed_litellm is untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-166 | rag | rag/embedder.py:104 | aembedding returning empty/malformed response.data is untested (would surface as ValueError deep in store) **[FIXED — Batch C 2026-06-21: empty response.data now raises EmbeddingError]** | testing | 75 | gated_auto | Y |
| P2-167 | rag | rag/embedder.py:49 | Embedding batching (BATCH_SIZE=100) never tested with >100 texts **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-168 | rag | rag/indexer.py:392 | _read_and_hash max_file_size branch is untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-169 | rag | rag/indexer.py:120 | _indexing re-entrancy guard returns empty IndexResult with no test **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-170 | rag | rag/store.py:405 | delete_by_file vector-realignment branch (len mismatch) untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P2-184 | rag | rag/chunker.py:100 | chunk_overlap >= chunk_size makes chunker effectively stall (advances 1 char per iteration) **[FIXED — safe_auto sweep 2026-06-21]** | correctness | 60 | gated_auto | Y |
| P2-187 | rag | rag/embedder.py:128 | embed_single on empty text raises IndexError (embed returns [] unconditionally) **[FIXED — Batch C 2026-06-21: embed_single now raises EmbeddingError, not IndexError]** | correctness | 50 | manual | Y |

### screens/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P2-188 | screens | screens/settings.py:852 | Editing a provider/MCP entry and changing its alias/name leaves the stale old entry behind **[FIXED — duplicate of P1-53, verified in Batch C 2026-06-21]** | correctness, testing | 75/80 | gated_auto | Y |
| P2-189 | screens | screens/settings.py:902 | Renaming a provider/MCP to an alias that already exists silently overwrites the other entry **[FIXED — duplicate of P1-53, verified in Batch C 2026-06-21]** | correctness | 75 | gated_auto | Y |
| P2-208 | screens | screens/input_modal.py:7 | InputModal has zero test coverage (all branches) **[FIXED — testing-gap sweep 2026-06-21]** | testing | 100 | gated_auto | Y |
| P2-209 | screens | screens/picker.py:15 | OptionPicker has zero test coverage **[FIXED — testing-gap sweep 2026-06-21]** | testing | 100 | gated_auto | Y |
| P2-210 | screens | screens/settings.py:282 | NewProviderForm model-row removal branch is untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 90 | gated_auto | Y |
| P2-211 | screens | screens/settings.py:286 | NewProviderForm on_input_changed / on_select_changed state-sync untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 85 | gated_auto | Y |
| P2-212 | screens | screens/settings.py:541 | ConfirmScreen 'Close and Save' path and _on_confirm_discard('save_close') untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 85 | gated_auto | Y |
| P2-213 | screens | screens/settings.py:859 | SettingsScreen.on_button_pressed routing branches untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 80 | gated_auto | Y |
| P2-214 | screens | screens/settings.py:1064 | SettingsScreen picker flows (theme/personality/default_model/embedding) untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |

## P3 — Low / User's discretion

### domain/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-4 | domain | domain/agent.py:94 | Agent.from_dict raises KeyError on missing 'allowed_tools' despite defaulting siblings ('allowed_skills') — inconsistent strictness **[FIXED — safe_auto sweep 2026-06-21]** | correctness | 100 | safe_auto | Y |
| P3-5 | domain | domain/agent.py:19 | AgentTypes.from_str error message lists t.value.lower() but other from_str variants list raw values; misleading on failure **[FIXED — safe_auto sweep 2026-06-21]** | correctness | 100 | safe_auto | Y |
| P3-13 | domain | domain/message.py:148 (alt) | record_streamed_message SYSTEM-role and catch-all branches untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 50 | gated_auto | N |

### agents/

(none)

### tools/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-37 | tools | tools/ast.py:423 | execute_get_file_skeleton has a no-op parent_node reassignment (dead code path) **[FIXED — safe_auto sweep 2026-06-21]** | correctness, maintainability, kieran-python | 75/100 | safe_auto | Y |

### llm/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-55 | llm | tests/test_streaming_messages.py | _history_to_api_messages orphan/tool_calls invariants untested **[FIXED — testing-gap sweep 2026-06-21]** | maintainability (testing) | 65 | gated_auto | Y |
| P3-56 | llm | llm/client.py:34 (alt) | classify_error exception-type ladder is exercised by neither test nor type discipline **[FIXED — testing-gap sweep 2026-06-21]** | maintainability (testing) | 55 | gated_auto | Y |
| P3-57 | llm | llm/client.py:467 (alt) | Stream-cancel propagation path (the duplicated except block) has no concurrency test **[FIXED — testing-gap sweep 2026-06-21]** | maintainability (testing) | 60 | gated_auto | Y |

### mcp/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-67 | mcp | mcp/__init__.py:62 | _server_status is never cleared, leaving stale entries across restarts and removed servers **[FIXED — safe_auto sweep 2026-06-21]** | correctness | 75 | safe_auto | Y |

### rag/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-77 | rag | rag/store.py:313 | record_index_duration is never directly tested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 50 | gated_auto | Y |
| P3-78 | rag | rag/embedder.py:128 (alt) | embed_single public method is untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |
| P3-79 | rag | rag/store.py:273 | _cosine_similarity zero-vector guard is untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 75 | gated_auto | Y |

### screens/

| # | Module | File:Line | Title | Reviewers | Conf | Action | Pre |
|---|---|---|---|---|---|---|---|
| P3-86 | screens | screens/picker.py:29 | OptionPicker builds Option(...) objects twice from the same items (compose + filter) **[FIXED — safe_auto sweep 2026-06-21]** | maintainability | 75 | safe_auto | Y |
| P3-92 | screens | screens/settings.py:453 (Cancel branch untested) | NewMCPServerForm Cancel button and Escape paths untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 90 | gated_auto | Y |
| P3-93 | screens | screens/settings.py:1274 | key_ctrl_s save-in-place path untested **[FIXED — testing-gap sweep 2026-06-21]** | testing | 85 | gated_auto | Y |
| P3-94 | screens | screens/settings.py:773 | SIM117: nested with statements should be combined into a single with — pyproject.toml ruff violation **[NO-OP — safe_auto sweep 2026-06-21: already combined into `with Vertical(...), Horizontal(...):` form]** | project-standards | 100 | safe_auto | N |

---

## Summary of Moved Items

| Tier | FIXED | FALSE-POSITIVE | NO-OP | Total |
|---|---|---|---|---|
| P0 | 5 | 0 | 0 | 5 |
| P1 | 32 | 2 | 0 | 34 |
| P2 | 41 | 1 | 0 | 42 |
| P3 | 14 | 0 | 1 | 15 |
| **Total** | **92** | **3** | **1** | **96** |
