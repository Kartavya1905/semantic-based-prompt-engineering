"""
FILE:         tests/unit/test_run_showcase.py
WHAT IT DOES: Checks the parts of run_showcase.py that need no model: the prompt step, the
              stats step's guidance when results are missing, and the step selection.
WHERE IT FITS: The guided tour (run_showcase.py). Its model steps reuse code tested elsewhere.
"""

import pytest

import run_showcase


def test_prompt_step_shows_every_section_and_the_fingerprint(capsys):
    assert run_showcase.main(["--steps", "prompt"]) == 0
    printed = capsys.readouterr().out
    for section in ("<role>", "<policies>", "<output_contract>", "<output_schema>", "<examples>"):
        assert section in printed
    assert "fingerprint" in printed and "<ticket>" in printed


def test_stats_step_explains_how_to_create_missing_results(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(run_showcase, "COMPARISON_RESULTS", tmp_path / "missing.jsonl")
    assert run_showcase.main(["--steps", "stats"]) == 0
    assert "configs/experiments/dev_v2_comparison.yaml" in capsys.readouterr().out


def test_unknown_step_is_an_error():
    with pytest.raises(SystemExit):
        run_showcase.main(["--steps", "prompt,dance"])


def test_showcase_tickets_fit_the_production_template():
    from prompt_engine.composer import PromptComposer
    from prompt_engine.registry import PromptRegistry

    registry = PromptRegistry()
    manifest = registry.load_manifest("ticket_triage", run_showcase.PRODUCTION_VARIANT)
    for showcase in run_showcase.SHOWCASE_TICKETS:
        PromptComposer(registry).compose(manifest, showcase["ticket"])  # raises if a key is off
