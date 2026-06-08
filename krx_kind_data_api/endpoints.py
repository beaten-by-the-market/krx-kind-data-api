"""KIND(kind.krx.co.kr) 화면(.do) → 친절한 이름 카탈로그.

각 엔드포인트는 dict로 정의한다:
    "path"          : `.do` 경로 (예: "listinvstg/mergeListingCompany.do")
    "http"          : "post" | "get"                        (기본 "post")
    "send_as"       : "params"(쿼리) | "data"(본문)          (기본 "params")
    "encoding"      : 응답 디코딩 인코딩                       (기본 "utf-8")
    "parser"        : parsers._PARSERS의 키                  (기본 "read_html")
    "parser_kwargs" : 파서에 넘길 추가 인자 (table_class 등)
    "defaults"      : 기본 파라미터 (호출자가 같은 키를 주면 덮어씀)
    "required"      : 반드시 채워야 하는 파라미터 이름 리스트
    "screen"        : 사람이 읽을 화면 설명

새 화면을 추가하려면 아래 dict에 한 줄 추가하면 된다. 자세한 절차:
docs/새_엔드포인트_추가하기.md
"""

ENDPOINTS = {
    # ── 종목 마스터 ────────────────────────────────────────────────
    "corp_list": {
        "path": "corpgeneral/corpList.do",
        "http": "get",
        "encoding": "euc-kr",
        "parser": "corp_list",
        "defaults": {"method": "download", "searchType": "13"},
        "screen": "상장법인목록(종목코드↔회사명 마스터). marketType=stockMkt/kosdaqMkt/konexMkt",
    },
    # ── 상장/증자 현황 ─────────────────────────────────────────────
    "stock_issue_list": {
        "path": "corpgeneral/stockissuelist.do",
        "http": "post",
        "send_as": "params",
        "parser": "read_html",
        "defaults": {
            "method": "searchStockIssueList",
            "forward": "searchStockIssueList",
            "pageIndex": "1",
            "currentPageSize": "5000",
            "orderMode": "1",
            "orderStat": "D",
            "fromDate": "2000-01-01",
        },
        "required": ["marketType", "toDate"],
        "screen": "증자(주식발행) 현황. marketType, listingType, fromDate~toDate",
    },
    "misc_list_type_stat": {
        "path": "listinvstg/miscListTypeStatDetail.do",
        "http": "post",
        "send_as": "data",
        "parser": "read_html",
        "defaults": {
            "method": "searchMiscListTypeStatDetailSub",
            "forward": "miscListTypeStatDetail_sub",
            "currentPageSize": "200",
            "pageIndex": "1",
            "marketType": "2",
        },
        "required": ["listMonth", "listClssCd"],
        "screen": "상장유형별 통계 상세(이전상장 11 / 특례상장 12 등). listMonth=연도",
    },
    "growth_report": {
        "path": "corpgeneral/growthReport.do",
        "http": "post",
        "send_as": "data",
        "encoding": "euc-kr",
        "parser": "read_html",
        "defaults": {
            "method": "listingForeignCompanyList",
            "forward": "growthReportList",
            "currentPageSize": "100",
            "pageIndex": "1",
            "kosdaqBbsTpCd": "23",
            "searchTextType": "1",
            "startDate": "1999-01-01",
        },
        "required": ["endDate"],
        "screen": "성장성특례 상장(성장성보고서) 목록. startDate~endDate",
    },
    # ── 상장유형별 기업 목록 (회사코드 추출) ───────────────────────
    "listing_company": {
        "path": "listinvstg/listingcompany.do",
        "http": "post",
        "send_as": "params",
        "parser": "kind_list_with_code",
        "parser_kwargs": {
            "table_class": "list type-00 tmt30",
            "columns": ["회사명", "상장일", "상장유형", "증권구분", "업종", "국적", "상장주선인"],
        },
        "defaults": {
            "method": "searchListingTypeSub",
            "forward": "listingtype_sub",
            "currentPageSize": "3000",
            "pageIndex": "1",
            "orderMode": "1",
            "orderStat": "D",
            "marketType": "2",
            "listTypeArrStr": "01|02|03|04|05|",
            "secuGrpArrStr": "0|ST|FS|MF|SC|RT|DR|",
            "fromDate": "2000-01-01",
        },
        "required": ["toDate"],
        "screen": "신규상장기업(상장유형 01~05). fromDate~toDate",
    },
    "merge_listing": {
        "path": "listinvstg/mergeListingCompany.do",
        "http": "post",
        "send_as": "params",
        "parser": "kind_list_with_code",
        "parser_kwargs": {
            "table_class": "list type-00 tmt30",
            "columns": ["회사명", "합병상장일", "상장유형", "증권구분", "업종", "국적", "상장주선인"],
        },
        "defaults": {
            "method": "searchMergeListingCompSub",
            "forward": "mergeListingCompany_sub",
            "currentPageSize": "2000",
            "pageIndex": "1",
            "orderMode": "1",
            "orderStat": "D",
            "marketType": "2",
            "listTypeArrStr": "06|07|",
            "secuGrpArrStr": "0|ST|FS|MF|SC|RT|DR|",
            "fromDate": "2000-01-01",
        },
        "required": ["toDate"],
        "screen": "합병·재상장 기업(상장유형 06·07, 스팩합병 '진짜 상장일'). fromDate~toDate",
    },
    # ── 공시 ──────────────────────────────────────────────────────
    "today_disclosure": {
        "path": "disclosure/todaydisclosure.do",
        "http": "post",
        "send_as": "params",
        "parser": "today_disclosure",
        "defaults": {
            "method": "searchTodayDisclosureSub",
            "forward": "todaydisclosure_sub",
            "currentPageSize": "100",
            "pageIndex": "1",
            "orderMode": "0",
            "orderStat": "D",
            "chose": "S",
            "todayFlag": "Y",
        },
        "required": ["marketType", "selDate"],
        "screen": "당일공시(marketType 1=코스피/2=코스닥, selDate=YYYY-MM-DD)",
    },
}


def get(name: str) -> dict:
    from .exceptions import UnknownEndpointError

    if name not in ENDPOINTS:
        raise UnknownEndpointError(
            f"Unknown endpoint: {name!r}. Available: {sorted(ENDPOINTS)}"
        )
    return ENDPOINTS[name]
