from app.services.summarize import _build_summary_markdown, _payload_from_mapped_items, _summary_result_from_parsed


def test_build_summary_markdown_includes_multiple_sections() -> None:
    markdown = _build_summary_markdown(
        {
            "one_liner": "짧은 요약",
            "overview": "첫 번째 핵심 내용이다. 두 번째 핵심 내용이다.",
            "detailed_summary": "첫 번째 세부 설명이다. 두 번째 세부 설명이다. 세 번째 세부 설명이다. 네 번째 세부 설명이다.",
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
    assert "- 첫 번째 핵심 내용이다." in markdown
    assert "### 내용 정리" in markdown
    assert "### 주제별 세부 내용" in markdown


def test_build_summary_markdown_preserves_existing_markdown_in_overview_and_detail() -> None:
    markdown = _build_summary_markdown(
        {
            "one_liner": "짧은 요약",
            "overview": "- 핵심 A\n- 핵심 B",
            "detailed_summary": "### 내용 정리\n- 세부 A\n- 세부 B",
            "key_points": [],
            "topic_summaries": [],
            "decisions": [],
            "open_questions": [],
            "notable_details": [],
        }
    )

    assert "## 총 요약\n- 핵심 A\n- 핵심 B" in markdown
    assert "## 상세 요약\n### 내용 정리\n- 세부 A\n- 세부 B" in markdown


def test_build_summary_markdown_does_not_put_decisions_or_actions_in_overview() -> None:
    markdown = _build_summary_markdown(
        {
            "one_liner": "짧은 요약",
            "overview": "핵심 A. 핵심 B.",
            "detailed_summary": "세부 A. 세부 B.",
            "key_points": [],
            "topic_summaries": [],
            "decisions": ["결정 1"],
            "open_questions": [],
            "notable_details": [],
            "action_items": [{"task": "후속 작업", "owner": "팀", "due": "내일"}],
        }
    )

    overview_block = markdown.split("## 상세 요약")[0]
    assert "### 결정/합의" not in overview_block
    assert "### 후속 조치" not in overview_block
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


def test_payload_from_mapped_items_trims_detailed_summary_at_sentence_boundary() -> None:
    repeated = "학생들이 회사에서 사용하는 기술과 다르다고 불평하는 경우가 있으나, 학교는 기초를 가르친다. "
    payload = _payload_from_mapped_items(
        [
            {
                "summary": repeated * 12,
                "detailed_summary": repeated * 80,
                "key_points": [],
                "topic_summaries": [],
                "decisions": [],
                "open_questions": [],
                "notable_details": [],
                "action_items": [],
                "keywords": [],
                "timeline": [],
            }
        ]
    )

    assert payload["detailed_summary"]
    assert len(payload["detailed_summary"]) > 4000
    assert payload["detailed_summary"].endswith(".")
    assert not payload["detailed_summary"].endswith("학")
