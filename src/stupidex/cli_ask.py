#!/usr/bin/env python3
"""CLI tool to invoke the ask_question modal from the terminal.

Usage:
    # Pass questions as JSON via argument
    stupidex-ask '{"questions": [{"title": "Favorite color?", "choices": ["Red", "Blue", "Green"]}]}'

    # Pass via stdin (pipe)
    echo '{"questions": [{"title": "Pick one", "choices": ["A", "B"]}]}' | stupidex-ask

    # Interactive: no args opens a demo question
    stupidex-ask
"""
from __future__ import annotations

import json
import sys
from typing import Any

from textual.app import App, ComposeResult

from stupidex.screens.question_modal import QuestionAnswer, QuestionModal, QuestionSpec
from stupidex.tools.ask_question import _format_answers_xml


class AskQuestionApp(App):
    """Minimal Textual app that pushes the QuestionModal and returns results."""

    CSS_PATH = None

    def __init__(self, specs: list[QuestionSpec], header: str = "Questions") -> None:
        super().__init__()
        self._specs = specs
        self._header = header
        self._result: list[QuestionAnswer | None] | None = None

    def compose(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        self.push_screen(QuestionModal(self._specs, header=self._header), self._on_result)

    def _on_result(self, result: list[QuestionAnswer | None] | None) -> None:
        self._result = result
        self.exit(result)


def _parse_questions_from_json(data: dict[str, Any]) -> tuple[list[QuestionSpec], str]:
    """Parse a JSON dict into QuestionSpec list and header string."""
    header = data.get("context", "Questions")
    raw_questions = data.get("questions", [])
    specs: list[QuestionSpec] = []
    for q in raw_questions:
        title = str(q.get("title", "") or "").strip()
        if not title:
            continue
        description = str(q.get("description", "") or "")
        choices_raw = q.get("choices")
        choices: list[str] | None = None
        if isinstance(choices_raw, list):
            choices = [str(c) for c in choices_raw if c is not None]
            if not choices:
                choices = None
        specs.append(QuestionSpec(title=title, description=description, choices=choices))
    return specs, header


def _demo_specs() -> tuple[list[QuestionSpec], str]:
    """Return a built-in demo question for interactive mode."""
    return (
        [
            QuestionSpec(
                title="Preferred Programming Language",
                description="Which language do you prefer for this project?",
                choices=["Python", "TypeScript", "Rust", "Go"],
            ),
            QuestionSpec(
                title="UI Framework",
                description="Pick a frontend framework (or skip for backend-only).",
                choices=["React", "Vue", "Svelte", "None"],
            ),
        ],
        "Project Setup",
    )


def _format_human_readable(result: list[QuestionAnswer | None] | None) -> str:
    """Format result as human-readable text."""
    if result is None:
        return "Skipped."
    parts: list[str] = []
    for i, ans in enumerate(result):
        if ans is None:
            parts.append(f"Q{i + 1}: (skipped)")
        else:
            pieces: list[str] = []
            if ans.choice:
                pieces.append(f"choice={ans.choice}")
            if ans.free_text:
                pieces.append(f"text={ans.free_text}")
            parts.append(f"Q{i + 1}: {', '.join(pieces) or '(empty)'}")
    return "\n".join(parts)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    # Read input
    raw_input: str | None = None
    if len(sys.argv) > 1:
        raw_input = " ".join(sys.argv[1:])
    elif not sys.stdin.isatty():
        raw_input = sys.stdin.read().strip()

    # Parse
    if raw_input:
        try:
            data = json.loads(raw_input)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON input.\n{e}", file=sys.stderr)
            sys.exit(1)
        specs, header = _parse_questions_from_json(data)
        if not specs:
            print("Error: No questions with valid titles provided in JSON.", file=sys.stderr)
            sys.exit(1)
    else:
        # Interactive demo mode
        specs, header = _demo_specs()

    # Launch modal
    app = AskQuestionApp(specs, header=header)
    result = app.run()

    # Output both human-readable and XML for LLM consumption
    human = _format_human_readable(result)
    xml = '<ask_question_result answered="false" />' if result is None else _format_answers_xml(result)

    print("\n--- Answer ---")
    print(human)
    print("\n--- XML (for LLM) ---")
    print(xml)


if __name__ == "__main__":
    main()
