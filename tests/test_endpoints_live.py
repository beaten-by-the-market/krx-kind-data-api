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

pytestmark = pytest.mark.skipif(
    os.getenv("KIND_SKIP_LIVE") == "1", reason="KIND_SKIP_LIVE set"
)

TODAY = datetime.today().strftime("%Y-%m-%d")


def test_catalog_has_core_endpoints():
    names = list_endpoints()
    for required in (
        "corp_list",
        "stock_issue_list",
        "misc_list_type_stat",
        "growth_report",
        "listing_company",
        "merge_listing",
        "today_disclosure",
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


def test_today_disclosure_shape():
    df = fetch("today_disclosure", marketType=1, selDate=TODAY)
    assert isinstance(df, pd.DataFrame)
    for col in ("시간", "회사코드", "회사명", "공시제목", "상세URL"):
        assert col in df.columns


def test_endpoint_info_roundtrip():
    info = endpoint_info("merge_listing")
    assert info["path"] == "listinvstg/mergeListingCompany.do"
    assert info["parser"] == "kind_list_with_code"
