from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from stupidex.tools.ask_question import _escape

from stupidex.screens.question_modal import QuestionAnswer, QuestionModal, QuestionSpec
from stupidex.tools.ask_question import (
    _format_answers_xml,
    _question_specs_from_args,
    execute_ask_question,
)


def _spec(
    title: str = "Q",
    description: str = "",
    choices: list[str] | None = None,
) -> QuestionSpec:
    return QuestionSpec(title=title, description=description, choices=choices)


class QuestionSpecFromArgsTests(unittest.TestCase):
    def test_basic_parse(self):
        specs = _question_specs_from_args(
            [{"title": "T", "description": "D", "choices": ["a", "b"]}]
        )
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].title, "T")
        self.assertEqual(specs[0].description, "D")
        self.assertEqual(specs[0].choices, ["a", "b"])

    def test_empty_choices_becomes_none(self):
        specs = _question_specs_from_args([{"title": "T", "choices": []}])
        self.assertIsNone(specs[0].choices)

    def test_missing_fields_default(self):
        specs = _question_specs_from_args([{}])
        self.assertEqual(specs[0].title, "")
        self.assertEqual(specs[0].description, "")
        self.assertIsNone(specs[0].choices)

    def test_multiple_questions(self):
        specs = _question_specs_from_args(
            [
                {"title": "One", "choices": ["x", "y"]},
                {"title": "Two"},
                {"title": "Three", "choices": ["a"]},
            ]
        )
        self.assertEqual(len(specs), 3)
        self.assertEqual(specs[2].choices, ["a"])


class FormatAnswersXmlTests(unittest.TestCase):
    def test_choice_only(self):
        xml = _format_answers_xml([QuestionAnswer(choice="A")])
        self.assertIn('index="0"', xml)
        self.assertIn('choice="A"', xml)
        self.assertIn("answered=\"true\"", xml)
        self.assertNotIn("<free_text>", xml)

    def test_free_text_only(self):
        xml = _format_answers_xml([QuestionAnswer(free_text="hello")])
        self.assertIn("<free_text>hello</free_text>", xml)
        self.assertNotIn("choice=", xml)

    def test_both(self):
        xml = _format_answers_xml([QuestionAnswer(choice="B", free_text="note")])
        self.assertIn('choice="B"', xml)
        self.assertIn("<free_text>note</free_text>", xml)

    def test_skipped_question(self):
        xml = _format_answers_xml([None])
        self.assertIn('answered="false"', xml)

    def test_escaping(self):
        xml = _format_answers_xml([QuestionAnswer(free_text="<evil>")])
        self.assertIn("&lt;evil&gt;", xml)
        self.assertNotIn("<evil>", xml)


class ExecuteAskQuestionTests(unittest.TestCase):
    def test_empty_questions_returns_error(self):
        result = asyncio.run(execute_ask_question(questions=[]))
        self.assertIn("requires at least one question", result.content)

    def test_no_title_returns_error(self):
        result = asyncio.run(
            execute_ask_question(questions=[{"description": "no title"}])
        )
        self.assertIn("must have a non-empty title", result.content)

    def test_no_active_app_returns_unavailable(self):
        with patch("textual._context.active_app") as mock_ctx:
            mock_ctx.get.side_effect = LookupError("no active app")
            result = asyncio.run(
                execute_ask_question(questions=[{"title": "T"}])
            )
        self.assertIn('answered="false"', result.content)
        self.assertIn("not available", result.content)

    def test_app_pushes_modal_and_returns_answers(self):
        mock_app = MagicMock()
        pushed = {}

        def fake_push(screen, callback):
            pushed["screen"] = screen
            pushed["callback"] = callback

        mock_app.push_screen.side_effect = fake_push

        answers = [QuestionAnswer(choice="A"), QuestionAnswer(free_text="note")]
        with patch("textual._context.active_app") as mock_ctx:
            mock_ctx.get.return_value = mock_app
            async def run():
                fut = asyncio.ensure_future(
                    execute_ask_question(questions=[{"title": "Q1", "choices": ["A"]}, {"title": "Q2"}])
                )
                await asyncio.sleep(0.01)
                callback = pushed["callback"]
                callback(answers)
                return await fut

            result = asyncio.run(run())

        mock_app.push_screen.assert_called_once()
        self.assertIn('choice="A"', result.content)
        self.assertIn("<free_text>note</free_text>", result.content)
        self.assertIn("answered 2/2", result.display)

    def test_user_skip_returns_skipped(self):
        mock_app = MagicMock()
        pushed = {}

        def fake_push(screen, callback):
            pushed["callback"] = callback

        mock_app.push_screen.side_effect = fake_push

        with patch("textual._context.active_app") as mock_ctx:
            mock_ctx.get.return_value = mock_app
            async def run():
                fut = asyncio.ensure_future(
                    execute_ask_question(questions=[{"title": "Q"}])
                )
                await asyncio.sleep(0.01)
                pushed["callback"](None)
                return await fut

            result = asyncio.run(run())

        self.assertIn('answered="false"', result.content)
        self.assertIn("skipped", result.content.lower())

    def test_context_passed_as_modal_header(self):
        mock_app = MagicMock()
        pushed = {}

        def fake_push(screen, callback):
            pushed["screen"] = screen
            pushed["callback"] = callback

        mock_app.push_screen.side_effect = fake_push

        with patch("textual._context.active_app") as mock_ctx:
            mock_ctx.get.return_value = mock_app
            async def run():
                fut = asyncio.ensure_future(
                    execute_ask_question(
                        questions=[{"title": "Q", "choices": ["A"]}],
                        context="Pick wisely",
                    )
                )
                await asyncio.sleep(0.01)
                pushed["callback"]([QuestionAnswer(choice="A")])
                return await fut

            asyncio.run(run())

        modal = pushed["screen"]
        self.assertEqual(pushed["screen"]._header, "Pick wisely")

    def test_default_header_when_no_context(self):
        mock_app = MagicMock()
        pushed = {}

        def fake_push(screen, callback):
            pushed["screen"] = screen
            pushed["callback"] = callback

        mock_app.push_screen.side_effect = fake_push

        with patch("textual._context.active_app") as mock_ctx:
            mock_ctx.get.return_value = mock_app
            async def run():
                fut = asyncio.ensure_future(
                    execute_ask_question(questions=[{"title": "Q"}])
                )
                await asyncio.sleep(0.01)
                pushed["callback"]([QuestionAnswer(free_text="hi")])
                return await fut

            asyncio.run(run())

        self.assertEqual(pushed["screen"]._header, "Questions")

    def test_partial_answers_count(self):
        mock_app = MagicMock()
        pushed = {}

        def fake_push(screen, callback):
            pushed["callback"] = callback

        mock_app.push_screen.side_effect = fake_push

        with patch("textual._context.active_app") as mock_ctx:
            mock_ctx.get.return_value = mock_app
            async def run():
                fut = asyncio.ensure_future(
                    execute_ask_question(
                        questions=[
                            {"title": "Q1", "choices": ["A", "B"]},
                            {"title": "Q2"},
                            {"title": "Q3", "choices": ["X"]},
                        ],
                    )
                )
                await asyncio.sleep(0.01)
                pushed["callback"]([
                    QuestionAnswer(choice="A"),
                    None,
                    QuestionAnswer(free_text="note"),
                ])
                return await fut

            result = asyncio.run(run())

        self.assertIn("answered 2/3", result.display)
        self.assertIn('choice="A"', result.content)
        self.assertIn("<free_text>note</free_text>", result.content)
        self.assertIn('answered="false"', result.content)

    def test_preferred_languages_question(self):
        mock_app = MagicMock()
        pushed = {}

        def fake_push(screen, callback):
            pushed["screen"] = screen
            pushed["callback"] = callback

        mock_app.push_screen.side_effect = fake_push

        with patch("textual._context.active_app") as mock_ctx:
            mock_ctx.get.return_value = mock_app

            async def run():
                fut = asyncio.ensure_future(
                    execute_ask_question(
                        questions=[
                            {
                                "title": "Preferred Programming Languages",
                                "description": "Which languages do you prefer to work with?",
                                "choices": ["Python", "TypeScript", "Rust", "Go", "Other"],
                            }
                        ],
                        context="Quick survey",
                    )
                )
                await asyncio.sleep(0.01)
                pushed["callback"]([QuestionAnswer(choice="Python")])
                return await fut

            result = asyncio.run(run())

        self.assertIn('choice="Python"', result.content)
        self.assertIn("answered 1/1", result.display)
        self.assertEqual(pushed["screen"]._header, "Quick survey")

    def test_escape_none_returns_empty(self):
        self.assertEqual(_escape(None), "")

    def test_escape_plain_string(self):
        self.assertEqual(_escape("hello"), "hello")

    def test_escape_special_chars(self):
        self.assertEqual(_escape("a < b > c & d"), "a &lt; b &gt; c &amp; d")


class QuestionModalCollectTests(unittest.TestCase):
    def _make_modal(self, specs: list[QuestionSpec]) -> QuestionModal:
        modal = QuestionModal(specs, header="H")
        modal.query_one = MagicMock(side_effect=self._query_one_side_effect(specs))
        return modal

    def _query_one_side_effect(self, specs: list[QuestionSpec]):
        inputs = {}
        radiosets = {}

        def _q(selector, type_=None):
            sel = selector.lstrip("#")
            if sel.startswith("question-choices-"):
                idx = int(sel.rsplit("-", 1)[1])
                return radiosets.setdefault(idx, MagicMock(pressed_button=None))
            if sel.startswith("question-freetext-"):
                idx = int(sel.rsplit("-", 1)[1])
                return inputs.setdefault(idx, MagicMock(value=""))
            raise KeyError(selector)

        return _q

    def test_all_empty_returns_none_answers(self):
        modal = self._make_modal([_spec("Q1"), _spec("Q2")])
        answers = modal._collect()
        self.assertEqual(answers, [None, None])

    def test_free_text_answer(self):
        modal = self._make_modal([_spec("Q1", choices=["a", "b"])])
        # mock the freetext input to return a value
        def _q(selector, type_=None):
            if selector == "#question-freetext-0":
                return MagicMock(value="typed")
            if selector == "#question-choices-0":
                return MagicMock(pressed_button=None)
            raise KeyError
        modal.query_one = MagicMock(side_effect=_q)
        answers = modal._collect()
        self.assertEqual(answers[0].free_text, "typed")
        self.assertIsNone(answers[0].choice)

    def test_choice_answer(self):
        modal = self._make_modal([_spec("Q1", choices=["a", "b"])])
        choice_button = MagicMock()
        choice_button.label.plain = "b"
        def _q(selector, type_=None):
            if selector == "#question-choices-0":
                return MagicMock(pressed_button=choice_button)
            if selector == "#question-freetext-0":
                return MagicMock(value="")
            raise KeyError
        modal.query_one = MagicMock(side_effect=_q)
        answers = modal._collect()
        self.assertEqual(answers[0].choice, "b")
        self.assertIsNone(answers[0].free_text)

    def test_whitespace_only_freetext_treated_as_empty(self):
        modal = self._make_modal([_spec("Q1", choices=[])])
        def _q(selector, type_=None):
            if selector == "#question-freetext-0":
                return MagicMock(value="   ")
            raise KeyError
        modal.query_one = MagicMock(side_effect=_q)
        answers = modal._collect()
        self.assertIsNone(answers[0])


if __name__ == "__main__":
    unittest.main()
