from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RadioButton, RadioSet


@dataclass
class QuestionSpec:
    title: str
    description: str = ""
    choices: list[str] | None = None


@dataclass
class QuestionAnswer:
    choice: str | None = None
    free_text: str | None = None


QuestionModalResult = list[QuestionAnswer | None] | None


class QuestionModal(ModalScreen[QuestionModalResult]):
    """Modal that asks the user one or more multiple-choice questions.

    Each question renders a title, description, an optional set of choices
    (radio buttons), and a free-text input that is always available. The
    modal is dismissed with a list of answers (one per question) or ``None``
    if the user skips/cancels.
    """

    CSS = """
    QuestionModal {
        align: center middle;
    }

    #question-modal-container {
        width: 72;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #question-modal-header {
        text-style: bold;
        color: $text-muted;
        margin-bottom: 1;
        border-bottom: solid $primary;
        width: 100%;
    }

    #question-modal-scroll {
        height: 1fr;
        margin-bottom: 1;
    }

    .question-block {
        padding: 0 0 1 0;
        border-bottom: dashed $primary 50%;
        margin-bottom: 1;
    }

    .question-block:last-child {
        border-bottom: none;
    }

    .question-title {
        text-style: bold;
        margin-bottom: 0;
    }

    .question-desc {
        color: $text-muted;
        margin-bottom: 1;
    }

    .question-radioset {
        margin-bottom: 1;
    }

    .question-freetext {
        margin-bottom: 0;
    }

    .question-freetext-label {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 0;
    }

    #question-modal-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #question-modal-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        questions: list[QuestionSpec],
        header: str = "",
    ) -> None:
        super().__init__()
        self._questions = questions
        self._header = header or "Questions"

    def compose(self) -> ComposeResult:
        with Vertical(id="question-modal-container"):
            yield Label(self._header, id="question-modal-header")
            with VerticalScroll(id="question-modal-scroll"):
                for i, q in enumerate(self._questions):
                    yield from self._compose_question(i, q)
            with Vertical(id="question-modal-buttons"):
                yield Button("Submit", variant="primary", id="question-modal-submit")
                yield Button("Skip", variant="default", id="question-modal-skip")

    def _compose_question(self, index: int, q: QuestionSpec) -> ComposeResult:
        with Vertical(classes="question-block"):
            yield Label(q.title, classes="question-title")
            if q.description:
                yield Label(q.description, classes="question-desc")
            if q.choices:
                yield RadioSet(
                    *[RadioButton(c) for c in q.choices],
                    id=f"question-choices-{index}",
                    classes="question-radioset",
                )
            yield Label("Or type your own answer:", classes="question-freetext-label")
            yield Input(id=f"question-freetext-{index}", classes="question-freetext")

    def on_mount(self) -> None:
        try:
            self.query_one("#question-freetext-0", Input).focus()
        except Exception:
            pass

    def _collect(self) -> list[QuestionAnswer | None]:
        answers: list[QuestionAnswer | None] = []
        for i, q in enumerate(self._questions):
            choice: str | None = None
            if q.choices:
                try:
                    radioset = self.query_one(f"#question-choices-{i}", RadioSet)
                    if radioset.pressed_button is not None:
                        choice = radioset.pressed_button.label.plain
                except Exception:
                    choice = None
            try:
                ft = self.query_one(f"#question-freetext-{i}", Input).value
            except Exception:
                ft = ""
            ft = (ft or "").strip()
            if choice is None and not ft:
                answers.append(None)
            else:
                answers.append(QuestionAnswer(choice=choice, free_text=ft or None))
        return answers

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "question-modal-submit":
            self.dismiss(self._collect())
        elif event.button.id == "question-modal-skip":
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)
