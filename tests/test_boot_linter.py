from app.agent.boot_linter import lint_boot_message
from app.config.settings import settings


def test_boot_linter_forbidden_phrase():
    problems = lint_boot_message("This agent is ready.", settings)
    assert any("forbidden phrase" in item for item in problems)


def test_boot_linter_list_formatting():
    problems = lint_boot_message("1) First step\n2) Second step", settings)
    assert "contains list formatting" in problems


def test_boot_linter_question_count():
    problems = lint_boot_message("What should I call you? What should you call me? Anything else?", settings)
    assert any("too many questions" in item for item in problems)


def test_boot_linter_word_count():
    text = "word " * 200
    problems = lint_boot_message(text, settings)
    assert any("too many words" in item for item in problems)

