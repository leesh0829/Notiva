from app.services.summarize import (
    _build_reduce_input,
    _clean_markdown,
    _coerce_text,
    _fallback_summary,
    _map_item_from_parsed,
    _normalize_action_items,
    _normalize_keywords,
    _normalize_timeline,
    _result_from_parsed,
)


class _FakeTranscript:
    def __init__(self, full_text: str, segments: list[dict]):
        self.full_text = full_text
        self.segments = segments


def test_coerce_text_handles_list_payload_without_truncation() -> None:
    raw_list = [
        "6월 17일 착수 감리 2차를 앞두고 문서 작업과 점검에 집중해야 한다.",
        "착수 감리는 작년 10월 과제 협약 이후 3개월간 설계 진행 상황을 검토하는 절차이다.",
    ]
    coerced = _coerce_text(raw_list)
    assert "착수 감리 2차" in coerced
    assert "10월 과제 협약" in coerced
    assert coerced.startswith("- ")


def test_coerce_text_extracts_text_from_dict() -> None:
    coerced = _coerce_text({"text": "결정 사항입니다."})
    assert coerced == "결정 사항입니다."


def test_normalize_action_items_filters_and_dedupes() -> None:
    rows = [
        {"task": "감리 문서 작성", "owner": "팀 전체", "due": "6월 17일"},
        {"task": "감리 문서 작성", "owner": "팀 전체", "due": "6월 17일"},
        {"task": "", "owner": "noop"},
        "단순 문자열 작업",
        "단순 문자열 작업",
    ]
    items = _normalize_action_items(rows)
    assert len(items) == 2
    assert items[0]["task"] == "감리 문서 작성"
    assert items[0]["owner"] == "팀 전체"
    assert items[0]["due"] == "6월 17일"
    assert items[1]["task"] == "단순 문자열 작업"
    assert items[1]["owner"] is None
    assert items[1]["due"] is None


def test_normalize_keywords_strips_hashes_and_limits() -> None:
    keywords = _normalize_keywords(["#AAS", "#AAS", "OPC UA", "  ", {"keyword": "ICC"}])
    assert keywords == ["AAS", "OPC UA", "ICC"]


def test_normalize_timeline_validates_time_ms() -> None:
    timeline = _normalize_timeline(
        [
            {"time_ms": 1500, "text": "도입"},
            {"time_ms": "bad", "text": "중반"},
            {"time_ms": -10, "text": "음수"},
            {"text": ""},
        ]
    )
    assert timeline == [
        {"time_ms": 1500, "text": "도입"},
        {"time_ms": 0, "text": "중반"},
        {"time_ms": 0, "text": "음수"},
    ]


def test_result_from_parsed_normalizes_all_fields() -> None:
    parsed = {
        "summary_md": "## 한 줄 요약\n- 회의 요약입니다.\n\n## 핵심 주제\n- 내용 A\n- 내용 B",
        "action_items": [{"task": "문서 작성", "owner": "팀", "due": "내일"}],
        "keywords": ["회의", "테스트"],
        "timeline": [{"time_ms": 1000, "text": "도입"}],
    }
    summary_md, action_items, keywords, timeline = _result_from_parsed(parsed)
    assert "## 한 줄 요약" in summary_md
    assert "## 핵심 주제" in summary_md
    assert action_items == [{"task": "문서 작성", "owner": "팀", "due": "내일"}]
    assert keywords == ["회의", "테스트"]
    assert timeline == [{"time_ms": 1000, "text": "도입"}]


def test_result_from_parsed_recovers_when_model_returns_list_for_markdown() -> None:
    parsed = {
        "summary_md": ["한 줄 요약 본문", "추가 핵심 흐름"],
        "action_items": [],
        "keywords": [],
        "timeline": [],
    }
    summary_md, _, _, _ = _result_from_parsed(parsed)
    assert "한 줄 요약 본문" in summary_md
    assert "추가 핵심 흐름" in summary_md
    assert "- 한 줄 요약 본문" in summary_md


def test_clean_markdown_collapses_blank_lines() -> None:
    assert _clean_markdown("## A\n\n\n\n- 내용") == "## A\n\n- 내용"


def test_map_item_from_parsed_caps_long_markdown() -> None:
    huge = "## 청크\n" + ("- 항목입니다. " * 5000)
    item = _map_item_from_parsed({"summary_md": huge, "action_items": [], "keywords": []})
    assert len(item["summary_md"]) <= 12_000


def test_build_reduce_input_emits_chunks_payload() -> None:
    mapped = [
        {"summary_md": "## 주제 A\n- 내용", "action_items": [], "keywords": ["A"]},
        {"summary_md": "## 주제 B\n- 내용", "action_items": [], "keywords": ["B"]},
        {"summary_md": "", "action_items": [], "keywords": []},
    ]
    payload = _build_reduce_input(mapped)
    assert payload.startswith("{")
    assert "chunks" in payload
    assert "주제 A" in payload
    assert "주제 B" in payload


def test_fallback_summary_returns_hierarchical_markdown() -> None:
    transcript = _FakeTranscript(
        full_text="안녕하세요. 6월 감리 대응 문서 작성을 시작합니다.",
        segments=[{"start_ms": 0, "end_ms": 5000, "text": "안녕하세요"}],
    )
    summary_md, action_items, keywords, timeline, model_name = _fallback_summary(transcript)
    assert "## 한 줄 요약" in summary_md
    assert "## 전사 발췌" in summary_md
    assert action_items == []
    assert keywords == []
    assert timeline == [{"time_ms": 0, "text": "안녕하세요"}]
    assert model_name == "fallback-summary-v4"
