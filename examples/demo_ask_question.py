#!/usr/bin/env python
"""Standalone demo: pushes QuestionModal in a minimal Textual app."""

from textual.app import App, ComposeResult

from stupidex.screens.question_modal import QuestionModal, QuestionSpec


class DemoApp(App):
    CSS_PATH = None

    def compose(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        specs = [
            QuestionSpec(
                title="Preferred Programming Languages",
                description="Which languages do you prefer to work with?",
                choices=["Python", "TypeScript", "Rust", "Go", "Other"],
            )
        ]
        self.push_screen(QuestionModal(specs, header="Quick survey"), self._on_result)

    def _on_result(self, result) -> None:
        self.exit(result)


def main():
    app = DemoApp()
    result = app.run()
    if result is None:
        print("\nYou skipped the question.")
    else:
        for i, ans in enumerate(result):
            if ans is None:
                print(f"\nQuestion {i+1}: skipped")
            else:
                parts = []
                if ans.choice:
                    parts.append(f"choice={ans.choice}")
                if ans.free_text:
                    parts.append(f"free_text={ans.free_text}")
                print(f"\nQuestion {i+1}: {', '.join(parts) or 'empty'}")


if __name__ == "__main__":
    main()
