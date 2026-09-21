"""회사 필터 — KIND 가 searchCorpName 을 무시하는 화면들.

2026-09 실측:
- disclosure_details : searchCorpName(회사명·종목코드) 무시. repIsuSrtCd='A'+종목코드만 거른다.
- stock_issue_list   : searchCorpName·repIsuSrtCd 무시. isurCd(KIND 회사코드)만 거른다.
- pubofr_prog_com    : searchCorpName 정상 동작(여기선 다루지 않음).

오프라인 테스트는 항상 돈다. 라이브 테스트는 KIND_SKIP_LIVE=1 이면 건너뛴다.
"""
from __future__ import annotations

import os
import warnings

import pytest

from krx_kind_data_api.endpoints import _disclosure_details_prepare, _stock_issue_prepare

live = pytest.mark.skipif(os.getenv("KIND_SKIP_LIVE") == "1", reason="KIND_SKIP_LIVE set")


# ── 오프라인: prepare 변환 ───────────────────────────────────────────

def test_rep_code_gets_a_prefix():
    p = _disclosure_details_prepare({"repIsuSrtCd": "005930", "searchCorpName": ""})
    assert p["repIsuSrtCd"] == "A005930"      # 'A' 없는 6자리는 서버에서 0건


def test_ticker_in_searchcorpname_moves_to_rep():
    p = _disclosure_details_prepare({"repIsuSrtCd": "", "searchCorpName": "005930"})
    assert p["repIsuSrtCd"] == "A005930"


def test_name_only_warns():
    with pytest.warns(UserWarning, match="무시"):
        _disclosure_details_prepare({"repIsuSrtCd": "", "searchCorpName": "삼성전자"})


def test_name_with_rep_does_not_warn():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        p = _disclosure_details_prepare({"repIsuSrtCd": "A005930", "searchCorpName": "삼성전자"})
    assert p["repIsuSrtCd"] == "A005930"


def test_stock_issue_name_warns_but_isurcd_does_not():
    with pytest.warns(UserWarning, match="isurCd"):
        _stock_issue_prepare({"searchCorpName": "케이뱅크", "isurCd": ""})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _stock_issue_prepare({"searchCorpName": "케이뱅크", "isurCd": "27957"})


# ── 라이브: 서버 동작 고정 ──────────────────────────────────────────

@live
def test_disclosure_details_rep_filters_to_one_company():
    from krx_kind_data_api import fetch

    df = fetch("disclosure_details", repIsuSrtCd="A005930",
               fromDate="2026-09-01", toDate="2026-09-18", lastReport="")
    assert len(df) > 0
    assert set(df["회사명"]) == {"삼성전자"}


@live
def test_disclosure_details_searchcorpname_is_ignored_by_server():
    """회사명만 주면 필터 없음과 같은 결과 — 이 테스트가 깨지면 KIND 가 바뀐 것."""
    from krx_kind_data_api import fetch

    kw = dict(fromDate="2026-09-01", toDate="2026-09-18", lastReport="")
    base = fetch("disclosure_details", **kw)
    with pytest.warns(UserWarning):
        named = fetch("disclosure_details", searchCorpName="삼성전자", **kw)
    assert list(named["접수번호"]) == list(base["접수번호"])


@live
def test_company_summary_works_for_delisted():
    from krx_kind_data_api import company_summary, rep_isu_srt_cd

    info = company_summary("41821")                 # 신한제10호스팩(2025 상장폐지)
    assert info["종목코드"] == "418210"
    assert "상장폐지" in info["시장구분"]
    assert rep_isu_srt_cd("41821") == "A418210"


@live
def test_stock_issue_list_isurcd_filters():
    from krx_kind_data_api import fetch

    df = fetch("stock_issue_list", isurCd="27957",
               fromDate="2026-01-01", toDate="2026-09-18")
    assert len(df) > 0
    assert set(df["회사명"]) == {"케이뱅크"}
