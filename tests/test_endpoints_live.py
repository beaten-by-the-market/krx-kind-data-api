"""실제 KIND 호출을 수행하는 라이브 테스트.

실행: pytest tests/test_endpoints_live.py
스킵: KIND_SKIP_LIVE=1 환경변수 설정 시 전체 스킵.
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import pytest

from krx_kind_data_api import endpoint_info, fetch, list_endpoints
from krx_kind_data_api.endpoints import ENDPOINTS

pytestmark = pytest.mark.skipif(
    os.getenv("KIND_SKIP_LIVE") == "1", reason="KIND_SKIP_LIVE set"
)

TODAY = datetime.today().strftime("%Y-%m-%d")


def build_input_schema(name: str) -> dict:
    """endpoint_info(name)["params"] → MCP inputSchema. docs 예제와 동일 로직."""
    params = endpoint_info(name).get("params", {})
    return {
        "type": "object",
        "properties": {
            k: {"type": "string", "description": v["desc"]}
            for k, v in params.items()
        },
        "required": [k for k, v in params.items() if v.get("required")],
    }


def test_catalog_has_core_endpoints():
    names = list_endpoints()
    for required in (
        "corp_list",
        "stock_issue_list",
        "misc_list_type_stat",
        "growth_report",
        "listing_company",
        "merge_listing",
        "pubofr_prog_com",
        "today_disclosure",
        "disclosure_details",
        "admin_issue",
    ):
        assert required in names


def test_required_params_enforced():
    # merge_listing은 toDate가 필수 → 누락 시 에러
    with pytest.raises(Exception):
        fetch("merge_listing")


def test_corp_list_returns_master():
    df = fetch("corp_list", marketType="kosdaqMkt")
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 100
    assert "종목코드" in df.columns
    # 6자리 문자열로 정규화됐는지
    assert df["종목코드"].str.len().eq(6).all()


def test_merge_listing_has_code_column():
    df = fetch("merge_listing", toDate=TODAY)
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert "회사코드" in df.columns


def test_stock_issue_list_shape_and_codes():
    # 변경상장(3) — 회사코드(5자리 이하)와 접수번호(14자리)를 각각 뽑는지
    df = fetch("stock_issue_list", marketType="all", listingType="3",
               fromDate="2026-04-21", toDate="2026-07-21", currentPageSize="15")
    assert isinstance(df, pd.DataFrame) and len(df) > 0
    for col in ("회사명", "상장(예정)일", "상장방식", "발행주식수", "액면가",
                "발행사유", "회사코드", "접수번호", "상세URL"):
        assert col in df.columns
    assert set(df["상장방식"]) == {"변경상장"}          # listingType=3 필터 확인
    assert df["회사코드"].str.len().max() <= 6           # companysummary_open 코드
    assert (df["접수번호"].str.len() == 14).all()        # fnDetailView acptno


def test_stock_issue_list_type_partition():
    # 전체 = 추가+변경+신규 (재상장은 해당 기간 0건일 수 있음)
    def n(lt):
        return len(fetch("stock_issue_list", marketType="all", listingType=lt,
                         fromDate="2026-04-21", toDate="2026-07-21",
                         currentPageSize="3000"))
    assert n("") == n("2") + n("3") + n("4") + n("5")


def test_admin_issue_shape_and_market_partition():
    df = fetch("admin_issue")
    assert isinstance(df, pd.DataFrame) and len(df) > 0
    assert list(df.columns) == ["종목명", "지정일", "지정사유"]
    # 전체 = 코스피(1) + 코스닥(2)
    kospi = fetch("admin_issue", marketType="1")
    kosdaq = fetch("admin_issue", marketType="2")
    assert len(kospi) + len(kosdaq) == len(df)


def test_today_disclosure_shape():
    df = fetch("today_disclosure", marketType=1, selDate=TODAY)
    assert isinstance(df, pd.DataFrame)
    for col in ("시간", "회사코드", "회사명", "공시제목", "상세URL"):
        assert col in df.columns


def test_pubofr_prog_com_sample():
    df = fetch(
        "pubofr_prog_com",
        searchCorpName="이루다",
        searchCorpNameTmp="이루다",
        isurCd="16406",
        fromDate="2019-01-01",
        toDate="2020-12-31",
    )
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    for col in ("회사명", "신고서제출일", "상장예정일", "업무처리번호"):
        assert col in df.columns
    assert df.loc[0, "회사명"] == "이루다"
    assert str(df.loc[0, "업무처리번호"]) == "20191128000155"


# ── 빈 결과에도 고정 컬럼 유지 (네트워크 불필요) ────────────────────

def test_parsers_keep_columns_when_empty():
    from krx_kind_data_api import parsers

    cases = {
        "today_disclosure": (
            '<table class="list type-00 mt10"><tbody></tbody></table>',
            ["시간", "회사코드", "회사명", "공시제목", "제출인", "상세URL"],
        ),
        "disclosure_details": (
            '<table class="list type-00 mt10"><tbody></tbody></table>',
            ["번호", "시간", "시장", "회사코드", "회사명",
             "공시제목", "접수번호", "제출인", "상세URL"],
        ),
        "stock_issue_list": (
            '<table class="list type-00"><tbody></tbody></table>',
            ["회사명", "상장(예정)일", "상장방식", "발행주식수", "액면가",
             "발행사유", "회사코드", "접수번호", "상세URL"],
        ),
    }
    for parser_name, (html, expected) in cases.items():
        df = getattr(parsers, parser_name)(html)
        assert len(df) == 0
        assert list(df.columns) == expected, parser_name

    # labeled_table은 columns 인자를 그대로 스키마로 유지
    df = parsers.labeled_table(
        '<table class="x"><tbody></tbody></table>',
        columns=["종목명", "지정일", "지정사유"], table_class="x",
    )
    assert len(df) == 0 and list(df.columns) == ["종목명", "지정일", "지정사유"]


# ── params 메타데이터 정합성 (네트워크 불필요) ──────────────────────

def test_all_endpoints_have_params_metadata():
    for name, spec in ENDPOINTS.items():
        assert "params" in spec, f"{name}에 params 문서가 없습니다"
        assert isinstance(spec["params"], dict) and spec["params"]


def test_params_required_flags_match_required_list():
    # params에서 required=True인 키 == spec['required'] 집합
    for name, spec in ENDPOINTS.items():
        params = spec["params"]
        flagged = {k for k, v in params.items() if v.get("required")}
        assert flagged == set(spec.get("required", [])), (
            f"{name}: params required={flagged} vs spec required={spec.get('required')}"
        )


def test_params_have_desc_and_kind():
    for name, spec in ENDPOINTS.items():
        for key, meta in spec["params"].items():
            assert meta.get("desc"), f"{name}.{key}에 desc 없음"
            assert meta.get("kind"), f"{name}.{key}에 kind 없음"


def test_build_input_schema_shape():
    schema = build_input_schema("pubofr_prog_com")
    assert schema["type"] == "object"
    assert schema["required"] == ["toDate"]
    assert "searchCorpName" in schema["properties"]
    assert schema["properties"]["searchCorpName"]["type"] == "string"


# ── 예시값이 실제로 동작하는지 (라이브) ─────────────────────────────

def test_pubofr_prog_com_filter_is_subset_of_all():
    # 필터 요청 1건이 전체 결과에 그대로 포함되는지(같은 데이터셋 확인)
    cap = fetch("pubofr_prog_com", searchCorpName="이루다",
                searchCorpNameTmp="이루다", isurCd="16406",
                fromDate="2019-01-01", toDate="2020-12-31")
    assert len(cap) == 1
    code = str(cap.loc[0, "업무처리번호"])
    allrows = fetch("pubofr_prog_com", fromDate="2019-01-01", toDate="2020-12-31")
    assert code in set(allrows["업무처리번호"].astype(str))


def test_listing_company_example_params():
    df = fetch("listing_company", toDate=TODAY)
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert "회사코드" in df.columns


# ── SPAC 합병상장 (spac_merge_listing) ──────────────────────────────

def test_spac_merge_prepare_maps_spactype():
    # prepare 훅: spacType → listTypeArrStr, spacType는 제거 (네트워크 불필요)
    from krx_kind_data_api.endpoints import _spac_merge_prepare

    assert _spac_merge_prepare({"spacType": "존속"})["listTypeArrStr"] == "06|"
    assert _spac_merge_prepare({"spacType": "소멸"})["listTypeArrStr"] == "07|"
    assert _spac_merge_prepare({"spacType": "전체"})["listTypeArrStr"] == "06|07|"
    # 미지정 → 전체
    assert _spac_merge_prepare({})["listTypeArrStr"] == "06|07|"
    # spacType 키는 전송 대상에서 빠진다
    assert "spacType" not in _spac_merge_prepare({"spacType": "존속"})
    # 매핑에 없는 값은 그대로 통과(고급 사용자)
    assert _spac_merge_prepare({"spacType": "06|"})["listTypeArrStr"] == "06|"


def test_spac_merge_listing_type_switch():
    survive = fetch("spac_merge_listing", spacType="존속", toDate=TODAY)
    dissolve = fetch("spac_merge_listing", spacType="소멸", toDate=TODAY)
    both = fetch("spac_merge_listing", spacType="전체", toDate=TODAY)

    assert len(survive) > 0 and len(dissolve) > 0
    assert set(survive["상장유형"]) == {"SPAC 존속합병"}
    assert set(dissolve["상장유형"]) == {"SPAC 소멸합병"}
    # 전체 = 존속 + 소멸 (서로소)
    assert len(both) == len(survive) + len(dissolve)
    assert set(both["상장유형"]) == {"SPAC 존속합병", "SPAC 소멸합병"}


def test_spac_merge_listing_columns():
    df = fetch("spac_merge_listing", spacType="존속", toDate=TODAY)
    for col in ("회사명", "합병상장일", "상장유형", "액면가", "공모가",
                "공모금액", "주요제품", "최초상장주식수", "회사코드"):
        assert col in df.columns


# ── 공시 본문(iframe) 실제 URL (disclosure_content_url) ──────────────

def test_content_url_jamjeong_separate():
    from krx_kind_data_api import disclosure_content_url

    url = disclosure_content_url("20260629000856", basis="separate")
    assert url.endswith("/99620.htm")
    assert "/external/2026/06/29/000856/" in url   # 슬롯4=접수번호 seq(종목코드 아님)


def test_content_id_differs_from_acptno():
    from krx_kind_data_api import disclosure_content_id

    acpt = "20260629000856"
    cid = disclosure_content_id(acpt)
    assert cid.isdigit() and len(cid) == 14
    assert cid != acpt          # content_id ≠ 접수번호


def test_content_url_requires_docno_or_basis():
    from krx_kind_data_api import disclosure_content_url

    with pytest.raises(ValueError):
        disclosure_content_url("20260629000856")


def test_content_html_fetch():
    import requests
    from krx_kind_data_api import disclosure_content_url

    url = disclosure_content_url("20260629000856", basis="separate")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    assert r.status_code == 200
    assert "실적" in r.content.decode("utf-8", "replace")


def test_endpoint_info_roundtrip():
    info = endpoint_info("merge_listing")
    assert info["path"] == "listinvstg/mergeListingCompany.do"
    assert info["parser"] == "kind_list_with_code"

    info = endpoint_info("pubofr_prog_com")
    assert info["path"] == "listinvstg/pubofrprogcom.do"
    assert info["send_as"] == "data"
