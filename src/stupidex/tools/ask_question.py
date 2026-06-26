from __future__ import annotations

import asyncio
import logging
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties
from stupidex.screens.question_modal import QuestionAnswer, QuestionModal, QuestionSpec

log = logging.getLogger(__name__)


ask_question_tool = Tool(
    name="ask_question",
    description=(
        "Ask the user one or more multiple-choice questions in a single call. "
        "Each question may have a title, description, and a list of choices. "
        "The user can always submit a free-text answer instead of (or in "
        "addition to) selecting a choice, and may skip any question. "
        "Use when you need a decision, clarification, or feedback from the "
        "user before proceeding. "
        "Especially useful during brainstorming for significant decision "
        "points — provide 2-4 curated choices and use the context parameter "
        "to explain why the question is being asked."
    ),
    parameters=ToolParameter(
        properties={
            "questions": ToolParameterProperties(
                type="array",
                description=(
                    "List of questions to ask. Each question is an object with: "
                    "title (str), description (str, optional), choices (list[str], optional). "
                    "If choices is omitted or empty, the question is free-text only."
                ),
                items={"type": "object"},
            ),
            "context": ToolParameterProperties(
                type="string",
                description=(
                    "Optional context explaining why the questions are being asked, "
                    "shown as the modal header."
                ),
            ),
        },
        required=["questions"],
    ),
    action_label="Asking...",
)


def _escape(s: str | None) -> str:
    return escape(s or "")


def _format_answers_xml(answers: list[QuestionAnswer | None]) -> str:
    parts = []
    for i, ans in enumerate(answers):
        if ans is None:
            parts.append(
                f'  <question index="{i}" answered="false" />'
            )
            continue
        attrs = 'answered="true"'
        if ans.choice:
            attrs += f" choice={quoteattr(ans.choice)}"
        if ans.free_text:
            parts.append(
                f'  <question index="{i}" {attrs}>\n'
                f'    <free_text>{_escape(ans.free_text)}</free_text>\n'
                f'  </question>'
            )
        else:
            parts.append(
                f'  <question index="{i}" {attrs} />'
            )
    return "<ask_question_result>\n" + "\n".join(parts) + "\n</ask_question_result>"


def _question_specs_from_args(questions: list[dict[str, Any]]) -> list[QuestionSpec]:
    specs: list[QuestionSpec] = []
    for q in questions:
        title = str(q.get("title", "") or "")
        description = str(q.get("description", "") or "")
        choices_raw = q.get("choices")
        choices: list[str] | None = None
        if isinstance(choices_raw, list):
            choices = [str(c) for c in choices_raw if c is not None]
            if not choices:
                choices = None
        specs.append(QuestionSpec(title=title, description=description, choices=choices))
    return specs


async def execute_ask_question(
    questions: list[dict[str, Any]],
    context: str | None = None,
) -> ExecutorResult:
    if not questions:
        return ExecutorResult(
            display="No questions provided",
            content="Error: ask_question requires at least one question.",
        )

    specs = _question_specs_from_args(questions)
    if not any(s.title for s in specs):
        return ExecutorResult(
            display="Invalid questions",
            content="Error: at least one question must have a non-empty title.",
        )

    try:
        from textual._context import active_app
        app = active_app.get()
        if app is None:
            raise LookupError("no active app")
    except Exception as exc:
        log.debug("ask_question: no active textual app: %s", exc)
        return ExecutorResult(
            display="User unavailable",
            content=(
                "<ask_question_result answered=\"false\">\n"
                "  User is not available to answer questions in this context "
                "(no interactive app). Proceed without a user answer.\n"
                "</ask_question_result>"
            ),
        )

    loop = asyncio.get_running_loop()
    future: asyncio.Future[list[QuestionAnswer | None] | None] = loop.create_future()

    def _on_result(result: list[QuestionAnswer | None] | None) -> None:
        if not future.done():
            if result is None:
                future.set_result(None)
            else:
                future.set_result(list(result))

    modal = QuestionModal(specs, header=context or "Questions")
    app.push_screen(modal, _on_result)

    try:
        result = await future
    except Exception as exc:
        log.debug("ask_question: error awaiting modal: %s", exc)
        return ExecutorResult(
            display="Question failed",
            content=f"<ask_question_result error=\"true\">Error presenting questions: {_escape(str(exc))}</ask_question_result>",
        )

    if result is None:
        return ExecutorResult(
            display="User skipped",
            content=(
                "<ask_question_result answered=\"false\">\n"
                "  The user skipped all questions.\n"
                "</ask_question_result>"
            ),
        )

    xml = _format_answers_xml(result)
    answered_count = sum(1 for a in result if a is not None)
    return ExecutorResult(
        display=f"User answered {answered_count}/{len(result)} question(s)",
        content=xml,
    )
