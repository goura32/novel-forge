from __future__ import annotations

from pathlib import Path

from novel_forge.ab_review import (
    ReviewCase,
    actionability_summary,
    extract_case_from_request,
    render_review_prompt,
    replay_ollama_options,
)


def _request_payload() -> dict[str, object]:
    return {
        "messages": [
            {"role": "system", "content": "system"},
            {
                "role": "user",
                "content": (
                    "# シーン本文レビュー\n\n"
                    "## レビュー対象\n"
                    "### writer context\n"
                    '{"pov":{"display_name":"エリナ"}}\n\n'
                    "### 本文\n"
                    '{"title":"夜明け","content":"エリナは扉を開けた。"}\n\n'
                    "## 出力仕様\n"
                    "{}"
                ),
            },
        ]
    }


def test_extract_case_from_saved_write_review_request() -> None:
    case = extract_case_from_request(
        case_id="scene_01",
        request_payload=_request_payload(),
        source_attempt_id="att_source",
    )

    assert case == ReviewCase(
        case_id="scene_01",
        writer_context={"pov": {"display_name": "エリナ"}},
        draft={"title": "夜明け", "content": "エリナは扉を開けた。"},
        source_attempt_id="att_source",
    )


def test_render_review_prompt_has_no_unresolved_placeholders(tmp_path: Path) -> None:
    template = tmp_path / "candidate.md"
    template.write_text(
        "### writer context\n{writer_context}\n\n"
        "### 本文\n{draft}\n\n"
        "### schema\n{schema}\n",
        encoding="utf-8",
    )

    rendered = render_review_prompt(
        template,
        writer_context={"pov": {"display_name": "エリナ"}},
        draft={"title": "夜明け", "content": "エリナは扉を開けた。"},
    )

    assert "{writer_context}" not in rendered
    assert "{draft}" not in rendered
    assert "{schema}" not in rendered


def test_replay_options_leave_temperature_and_top_p_unspecified() -> None:
    options = replay_ollama_options(
        {"think": False, "temperature": 0.7, "top_p": 0.9, "num_ctx": 262144},
        seed=101,
    )

    assert options == {"think": False, "num_ctx": 262144, "seed": 101}


def test_actionability_summary_counts_schema_violations_not_freeform_notes() -> None:
    summary = actionability_summary(
        {
            "issues": [
                {
                    "severity": "重要",
                    "field": "content",
                    "description": "根拠あり",
                    "suggestion": "修正する",
                    "before": "エリナは扉を開けた。",
                    "after": "エリナは扉を押し開けた。",
                },
                {
                    "severity": "軽微",
                    "field": "content",
                    "description": "根拠なし",
                    "suggestion": "修正する",
                    "before": "本文にない語",
                    "after": "",
                },
                {
                    "field": "content",
                    "description": "必須欠落",
                    "suggestion": "修正する",
                },
            ]
        },
    )

    assert summary == {
        "issue_count": 3,
        "schema_violation_count": 1,
    }
