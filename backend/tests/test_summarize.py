from app.services.summarize import _build_summary_markdown, _payload_from_mapped_items, _summary_result_from_parsed


def test_build_summary_markdown_includes_multiple_sections() -> None:
    markdown = _build_summary_markdown(
        {
            "one_liner": "짧은 요약",
            "overview": "전체 개요",
            "detailed_summary": "상세 내용",
            "key_points": ["핵심 1", "핵심 2"],
            "topic_summaries": [{"topic": "주제 A", "summary": "설명"}],
            "decisions": ["결정 1"],
            "open_questions": ["질문 1"],
            "notable_details": ["세부 1"],
        }
    )

    assert "## 한 줄 요약" in markdown
    assert "## 총 요약" in markdown
    assert "## 상세 요약" in markdown
    assert "## 주제별 요약" in markdown
    assert "## 결정 사항" in markdown


def test_summary_result_from_parsed_preserves_action_items_keywords_and_timeline() -> None:
    summary_md, action_items, keywords, timeline = _summary_result_from_parsed(
        {
            "one_liner": "짧은 요약",
            "overview": "개요",
            "action_items": [{"task": "작업", "owner": "팀", "due": "내일"}],
            "keywords": ["회의", "테스트"],
            "timeline": [{"time_ms": 1000, "text": "도입"}],
        }
    )

    assert "## 한 줄 요약" in summary_md
    assert action_items == [{"task": "작업", "owner": "팀", "due": "내일"}]
    assert keywords == ["회의", "테스트"]
    assert timeline == [{"time_ms": 1000, "text": "도입"}]


def test_payload_from_mapped_items_builds_non_empty_fallback() -> None:
    payload = _payload_from_mapped_items(
        [
            {
                "summary": "첫 번째 주제 설명",
                "detailed_summary": "첫 번째 주제 설명과 세부 맥락",
                "key_points": ["핵심 A"],
                "topic_summaries": [{"topic": "주제 A", "summary": "설명 A"}],
                "decisions": [],
                "open_questions": [],
                "notable_details": ["세부 A"],
                "action_items": [],
                "keywords": [],
                "timeline": [{"time_ms": 0, "text": "도입"}],
            }
        ]
    )

    assert payload["one_liner"]
    assert payload["overview"]
    assert payload["topic_summaries"]
