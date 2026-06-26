---
title: "feat: Proactive ask_question escalation during brainstorming"
type: feat
date: 2026-06-25
---

# Proactive ask_question escalation during brainstorming

## Summary

Add agent-level guidance so the AI proactively uses `ask_question` at significant decision points during brainstorming — escalating from chat-based questions to the modal with curated choices when the decision is consequential enough to warrant focused user input.

## Problem Frame

The `ask_question` tool exists and works: it pushes a `QuestionModal` with radio buttons, free text, and skip support. The tool is registered as an allowed tool for the general agent. But the agent has zero guidance on *when* to reach for it. The tool description says "Use when you need a decision, clarification, or feedback from the user before proceeding" — too vague to trigger proactive use. During brainstorming, the agent defaults to presenting choices as numbered lists in chat text, even for significant decisions where a focused modal interaction would produce better input.

## Requirements

R1. The general agent's system prompt includes a section describing when to proactively call `ask_question`, with concrete trigger scenarios (approach selection, scope decisions, design direction).

R2. The guidance specifies an escalation threshold: lightweight clarifications stay in chat; significant decisions escalate to the modal. "Significant" means the choice has meaningful trade-offs, would change the direction of subsequent work, or is difficult to reverse.

R3. The agent formulates 2-4 curated choices when calling `ask_question`, not just free-text prompts. Choices represent genuinely distinct options.

R4. The brainstorm skill's interaction rule #4 remains the default for lightweight questions. The new guidance overrides it only for significant decision points.

R5. The `ask_question` tool description mentions proactive use during brainstorming workflows.

## Key Technical Decisions

- **Guidance lives in AGENT.md, not in the tool.** The tool is a dumb executor; behavioral guidance belongs in the agent's system prompt. Keeps the tool generic while guidance is agent-specific.
- **Escalation, not replacement.** Chat-based questions remain the default. The modal is reserved for decisions where focused input matters.
- **No code changes to the tool or modal.** The existing `ask_question` tool and `QuestionModal` are sufficient. This is a guidance-only change.

## Implementation Units

### U1. Add ask_question guidance to AGENT.md

**Goal:** Give the agent concrete instructions on when to proactively call `ask_question`.

**Files:**
- `src/stupidex/agents/defaults/general/AGENT.md` (modify)

**Approach:** Add a new "## Interactive Decision Points" section after "## Tool Usage". Describe the escalation principle, concrete trigger scenarios, how to formulate curated choices, and `context` parameter usage.

**Test scenarios:**
- Agent reads AGENT.md and the new section is present and coherent
- No contradictions with existing rules

**Verification:** Read modified AGENT.md and confirm natural integration.

### U2. Update brainstorm SKILL.md interaction rules

**Goal:** Make the brainstorm skill's interaction rules coherent with escalation guidance.

**Files:**
- `src/stupidex/skills/defaults/brainstorm/SKILL.md` (modify)

**Approach:** Add a note to interaction rule #4 acknowledging that for significant decision points, the agent escalates to the `ask_question` modal. Keep the rule's default behavior unchanged.

**Test scenarios:**
- Interaction rules remain internally consistent
- Rule #4 still governs lightweight questions; escalation is clearly scoped

**Verification:** Read modified SKILL.md and confirm no contradictions.

### U3. Update ask_question tool description

**Goal:** Align the tool description with the new proactive usage pattern.

**Files:**
- `src/stupidex/tools/ask_question.py` (modify)

**Approach:** Update the `description` field to mention brainstorming workflows and curated choices. Keep it concise.

**Test scenarios:**
- Tool description accurately describes capabilities
- Description reinforces AGENT.md guidance

**Verification:** Read modified description and confirm coherence.

## Scope Boundaries

- No changes to QuestionModal UI or XML format
- No changes to tool execution logic
- No changes to other agents' AGENT.md files
- No automatic triggering — agent decides when to call `ask_question`

## Risks & Dependencies

- **Over-triggering risk.** Too aggressive guidance = annoying modals. Mitigation: explicit escalation threshold.
- **Under-triggering risk.** Too conservative guidance = agent defaults to chat. Mitigation: concrete trigger scenarios.

## Sources / Research

- `src/stupidex/tools/ask_question.py` — tool definition
- `src/stupidex/screens/question_modal.py` — modal UI
- `src/stupidex/agents/defaults/general/AGENT.md` — agent system prompt
- `src/stupidex/skills/defaults/brainstorm/SKILL.md` — brainstorm rules
- Brainstorm dialogue: user selected "Escalate" approach
