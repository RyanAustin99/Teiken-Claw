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


def test_boot_linter_canned_assistant_intro():
    problems = lint_boot_message("Hello, I am your agent. How can I help you today?", settings)
    assert any("canned assistant" in item for item in problems)


def test_boot_linter_operational_identity_phrase():
    problems = lint_boot_message("My operational identity is Alex.", settings)
    assert any("forbidden phrase" in item and "operational identity" in item for item in problems)


def test_boot_linter_session_scenario_meta_phrases():
    problems = lint_boot_message("For this session in this scenario, let's begin.", settings)
    lowered = " ".join(problems).lower()
    assert "session" in lowered
    assert "scenario" in lowered
