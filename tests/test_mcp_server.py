"""MCP 서버의 순수 로직 테스트.

mcp 패키지 설치 없이도 스키마/디스패치 로직을 검증한다(build_server/main만 mcp 필요).
run_tool 실계열 호출은 KIND_SKIP_LIVE=1로 스킵 가능.
"""
from __future__ import annotations

import os

import pytest

from krx_kind_data_api import list_endpoints
from krx_kind_data_api.mcp_server import (
    catalog,
    endpoint_from_tool,
    input_schema,
    run_tool,
    tool_name,
)


def test_tool_name_roundtrip():
    for ep in list_endpoints():
        assert endpoint_from_tool(tool_name(ep)) == ep
    assert tool_name("pubofr_prog_com") == "kind_pubofr_prog_com"


def test_input_schema_matches_params():
    schema = input_schema("pubofr_prog_com")
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["toDate"]
    # enum/examples 반영 확인
    assert schema["properties"]["searchCorpName"]["type"] == "string"
    assert "examples" in schema["properties"]["searchCorpName"]


def test_input_schema_enum_carried():
    schema = input_schema("today_disclosure")
    assert schema["properties"]["marketType"]["enum"] == ["1", "2"]
    assert set(schema["required"]) == {"marketType", "selDate"}


def test_catalog_covers_all_endpoints():
    names = {t["name"] for t in catalog()}
    assert names == {tool_name(ep) for ep in list_endpoints()}
    for t in catalog():
        assert t["description"]
        assert t["inputSchema"]["type"] == "object"


@pytest.mark.skipif(os.getenv("KIND_SKIP_LIVE") == "1", reason="KIND_SKIP_LIVE set")
def test_run_tool_shape_and_json_safe():
    import json

    result = run_tool(
        "pubofr_prog_com",
        {"searchCorpName": "이루다", "searchCorpNameTmp": "이루다",
         "isurCd": "16406", "fromDate": "2019-01-01", "toDate": "2020-12-31"},
    )
    assert result["endpoint"] == "pubofr_prog_com"
    assert result["rows"] == 1
    assert "회사명" in result["columns"]
    assert result["records"][0]["회사명"] == "이루다"
    # JSON 직렬화 가능해야 함(numpy/NaT 잔재 없음)
    json.dumps(result, ensure_ascii=False)


@pytest.mark.skipif(os.getenv("KIND_SKIP_LIVE") == "1", reason="KIND_SKIP_LIVE set")
def test_run_tool_drops_empty_args_defaults_to_all():
    # 빈 문자열 필터는 제거되어 전체 조회가 된다
    result = run_tool("pubofr_prog_com", {"searchCorpName": "", "toDate": "2026-07-02"})
    assert result["rows"] > 1
