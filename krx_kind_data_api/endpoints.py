"""KIND(kind.krx.co.kr) 화면(.do) → 친절한 이름 카탈로그.

각 엔드포인트는 dict로 정의한다:
    "path"          : `.do` 경로 (예: "listinvstg/mergeListingCompany.do")
    "http"          : "post" | "get"                        (기본 "post")
    "send_as"       : "params"(쿼리) | "data"(본문)          (기본 "params")
    "encoding"      : 응답 디코딩 인코딩                       (기본 "utf-8")
    "parser"        : parsers._PARSERS의 키                  (기본 "read_html")
    "parser_kwargs" : 파서에 넘길 추가 인자 (table_class 등)
    "defaults"      : 기본 파라미터 (호출자가 같은 키를 주면 덮어씀)
    "prepare"       : (선택) merged dict를 받아 변형해 돌려주는 콜러블.
                      친절한 파라미터(예: spacType)를 화면 raw 필드(listTypeArrStr)로
                      바꾸거나 파생값을 채울 때 쓴다. required 검증 직전에 실행된다.
    "required"      : 반드시 채워야 하는 파라미터 이름 리스트
    "screen"        : 사람이 읽을 화면 설명
    "params"        : (선택) 호출자/MCP가 넘길 수 있는 파라미터의 문서.
                      {param_name: {"desc", "example", "kind", "required", ...}} 꼴.
                      fetch()는 이 필드를 읽지 않는다(순수 메타데이터). MCP 서버가
                      이걸 그대로 JSON-Schema로 변환해 툴 인자를 노출하면 된다.
                      아래 "params" 항목의 하위 키 규약:
                        "desc"     : 사람이 읽을 설명
                        "example"  : 예시 값
                        "required" : True면 호출자가 반드시 채워야 함(= required 리스트와 일치)
                        "kind"     : "date" | "filter" | "paging" | "sort" 등 역할 구분.
                                     defaults의 나머지 키(method/forward 등)는 화면 내부
                                     고정값이라 여기 문서화하지 않으며 건드리면 안 된다.

새 화면을 추가하려면 아래 dict에 한 줄 추가하면 된다. 자세한 절차:
docs/새_엔드포인트_추가하기.md
"""

# SPAC 합병상장(존속/소멸) 스위치. 친절한 spacType → 화면 raw 필드 listTypeArrStr.
_SPAC_TYPE_TO_CODE = {"존속": "06|", "소멸": "07|", "전체": "06|07|"}


def _spac_merge_prepare(p: dict) -> dict:
    """spacType(존속/소멸/전체)을 listTypeArrStr 코드로 변환하고 spacType 키는 제거.

    - 서버 필터는 listTypeArrStr가 결정한다(listTypeArr는 무시됨을 실측 확인).
    - 매핑에 없는 값이면 그대로 listTypeArrStr로 넘긴다(고급 사용자가 '06|' 직접 지정 가능).
    - spacType은 KIND가 모르는 가상 파라미터이므로 전송 전에 pop 한다.
    """
    spac_type = p.pop("spacType", "전체")
    p["listTypeArrStr"] = _SPAC_TYPE_TO_CODE.get(spac_type, spac_type)
    return p


# ── 공시 상세검색(details.do) 공시유형 매핑 ────────────────────────────
# details.do는 공시유형을 "카테고리 탭(01~20) + 세부코드"로 필터한다.
# 필터를 켜려면 해당 카테고리 필드에 값을 넣어야 한다:
#     disclosureType{cat}     = "code|"   (파이프로 끝나는 코드 나열)
#     pDisclosureType{cat}    = "code|"   (동일)
#     disclosureTypeArr{cat}  = "code"    (배열 형태)
#     bfrDsclsType            = "on"
# cat(카테고리 탭 인덱스)은 세부코드에서 유추되지 않으므로 아래 매핑으로 관리한다.
#
# 카테고리 탭 인덱스(브라우저 폼 disclosureType{NN} 기준):
#   01 수시공시 / 02 시장조치 / 03 공정공시 / 04 신고사항 / 05 채권공시 /
#   06 채권시장조치 / 07 경기공시 / 08 특수공시 / 09 발행공시 / 10 지분공시 /
#   11 워런트공시 / 13 ETN공시 / 14 의결권공시 / 20 공정위공시
#
# 확장 방법: 브라우저에서 원하는 유형을 체크하고 details.do POST 폼을 캡처해
#   disclosureType{NN}=코드| 와 disclosureTypeArr{NN}=코드 를 확인한 뒤 아래 dict에
#   {"친절한키": {"cat": "NN", "code": "코드"}} 한 줄을 추가하면 된다.
DISCLOSURE_TYPE_CODES = {
    # 공정공시(03) > 매출액 영업손익 등 영업실적
    "공정공시_영업실적": {"cat": "03", "code": "0204"},
}

# details.do 폼에 존재하는 공시유형 카테고리 탭 인덱스(12·15~19는 폼에 없음).
_DETAIL_DISC_CATS = ["01", "02", "03", "04", "05", "06", "07", "08",
                     "09", "10", "11", "13", "14", "20"]


def _disclosure_details_defaults() -> dict:
    """details.do가 기대하는 전체 폼 필드를 빈값으로 채운 defaults 생성."""
    d = {
        # ── 화면 내부 고정값 ──
        "method": "searchDetailsSub",
        "forward": "details_sub",
        # ── 페이지네이션 / 정렬 ──
        # 화면 드롭다운은 15/30/50/100만 제공. 100 초과는 서버가 무시할 수 있으니
        # 전량이 필요하면 pageIndex로 페이지를 넘긴다(전체 건수는 결과 페이징에 표시).
        "currentPageSize": "100",
        "pageIndex": "1",
        "orderMode": "1",
        "orderStat": "D",
        # ── 검색 조건(빈값 = 전체) ──
        "searchCodeType": "",
        "repIsuSrtCd": "",
        "allRepIsuSrtCd": "",
        "oldSearchCorpName": "",
        "disclosureType": "",       # raw 빈 필드(친절한 disclosureType 파라미터와 별개)
        "disTypevalue": "",
        "reportNm": "",
        "reportCd": "",
        "searchCorpName": "",       # 회사명(부분일치) 또는 종목코드
        "business": "",
        "marketType": "",           # 빈값=전체 / 1=유가(코스피) / 2=코스닥
        "kosdaqSegment": "",
        "settlementMonth": "",
        "securities": "",
        "submitOblgNm": "",
        "enterprise": "",
        "reportNmTemp": "",
        "reportNmPop": "",
        "bfrDsclsType": "on",
        "fromDate": "2000-01-01",
    }
    for cat in _DETAIL_DISC_CATS:
        d[f"disclosureType{cat}"] = ""
        d[f"pDisclosureType{cat}"] = ""
    return d


def _disclosure_details_prepare(p: dict) -> dict:
    """친절한 disclosureType(키 또는 'cat:code') → 카테고리별 raw 필드로 전개.

    - disclosureType 이 DISCLOSURE_TYPE_CODES 의 키면 그 cat/code 사용.
    - 'cat:code'(예: '03:0204') 형태면 그대로 파싱해 사용(매핑에 없는 유형 즉석 지정).
    - 값이 없으면 공시유형 필터 없이 전체 조회.
    """
    from .exceptions import KINDFetchError

    key = (p.pop("disclosureType", "") or "").strip()
    cat = (p.pop("disclosureTypeCat", "") or "").strip()
    code = (p.pop("disclosureTypeCode", "") or "").strip()
    if key:
        spec = DISCLOSURE_TYPE_CODES.get(key)
        if spec is not None:
            cat, code = spec["cat"], spec["code"]
        elif ":" in key:
            cat, code = (x.strip() for x in key.split(":", 1))
        else:
            raise KINDFetchError(
                f"Unknown disclosureType {key!r}. "
                f"Available keys: {sorted(DISCLOSURE_TYPE_CODES)} "
                f"or use 'cat:code' form (예: '03:0204')."
            )
    if cat and code:
        p[f"disclosureType{cat}"] = f"{code}|"
        p[f"pDisclosureType{cat}"] = f"{code}|"
        p[f"disclosureTypeArr{cat}"] = code
    # 친절한 파라미터를 소비했으니 raw 빈 필드를 복원(폼이 기대).
    p["disclosureType"] = ""
    return p


ENDPOINTS = {
    # ── 종목 마스터 ────────────────────────────────────────────────
    "corp_list": {
        "path": "corpgeneral/corpList.do",
        "http": "get",
        "encoding": "euc-kr",
        "parser": "corp_list",
        "defaults": {"method": "download", "searchType": "13"},
        "screen": "상장법인목록(종목코드↔회사명 마스터). marketType=stockMkt/kosdaqMkt/konexMkt",
        "params": {
            "marketType": {
                "kind": "filter", "required": False, "example": "kosdaqMkt",
                "enum": ["stockMkt", "kosdaqMkt", "konexMkt"],
                "desc": "시장 구분. stockMkt=코스피 / kosdaqMkt=코스닥 / konexMkt=코넥스. "
                        "생략 시 전체 시장.",
            },
        },
    },
    # ── 상장/증자 현황 ─────────────────────────────────────────────
    "stock_issue_list": {
        "path": "corpgeneral/stockissuelist.do",
        "http": "post",
        "send_as": "data",
        "parser": "stock_issue_list",   # 회사코드+접수번호 둘 다 추출(전용 파서)
        "defaults": {
            # ── 화면 내부 고정값 ──
            "method": "searchStockIssueList",
            "forward": "searchStockIssueList",
            "searchMode": "",
            "searchCodeType": "",
            # ── 페이지네이션 / 정렬 ──
            "pageIndex": "1",
            "currentPageSize": "5000",   # ≈전량. 화면 기본은 15
            "orderMode": "1",
            "orderStat": "D",
            # ── 필터(빈값 = 전체) ──
            "marketType": "all",         # all=전체 / 1=코스피 / 2=코스닥 계열
            "listingType": "",           # 빈값=전체 (2 추가/3 변경/4 신규/5 재상장)
            "searchCorpName": "",        # 회사명(부분일치) 또는 종목코드
            "comAbbrv": "",
            "repIsuSrtCd": "",
            "repIsuCd": "",
            "isurCd": "",
            "bzProcsNo": "",
            "paxreq": "",
            "outsvcno": "",
            "fromDate": "2000-01-01",
        },
        "required": ["toDate"],
        "screen": "증자·상장방식별 주식발행 현황(추가/변경/신규/재상장). "
                  "marketType(all/1/2), listingType로 유형 필터, fromDate~toDate. "
                  "반환: 회사명·상장(예정)일·상장방식·발행주식수·액면가·발행사유·회사코드·접수번호·상세URL",
        "params": {
            "toDate": {
                "kind": "date", "required": True, "format": "YYYY-MM-DD",
                "example": "2026-07-21", "desc": "조회 종료일(상장예정일 기준 상한). 필수.",
            },
            "fromDate": {
                "kind": "date", "required": False, "format": "YYYY-MM-DD",
                "example": "2026-04-21", "desc": "조회 시작일. 생략 시 2000-01-01.",
            },
            "listingType": {
                "kind": "filter", "required": False, "example": "4",
                "enum": ["", "2", "3", "4", "5"],
                "desc": "상장방식(발행유형) 필터. 빈값=전체 / 2=추가상장 / 3=변경상장(감자·병합·소각 등) / "
                        "4=신규상장 / 5=재상장.",
            },
            "marketType": {
                "kind": "filter", "required": False, "example": "all",
                "enum": ["all", "1", "2"],
                "desc": "시장 구분. all=전체(기본) / 1=코스피 / 2=코스닥 계열.",
            },
            "searchCorpName": {
                "kind": "filter", "required": False, "example": "삼성전자",
                "desc": "회사명(부분일치) 또는 종목코드로 필터. 빈값이면 전체.",
            },
            "currentPageSize": {
                "kind": "paging", "required": False, "example": "5000",
                "desc": "최대 반환 행 수. 기본 5000≈전량.",
            },
            "pageIndex": {
                "kind": "paging", "required": False, "example": "1",
                "desc": "페이지 번호(1부터).",
            },
            "orderStat": {
                "kind": "sort", "required": False, "example": "D",
                "desc": "정렬 방향. D=상장(예정)일 내림차순(최신순) / A=오름차순.",
            },
        },
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
        "params": {
            "listMonth": {
                "kind": "filter", "required": True, "example": "2024",
                "desc": "조회 연도(YYYY). 필수.",
            },
            "listClssCd": {
                "kind": "filter", "required": True, "example": "12",
                "desc": "상장유형 코드. 11=이전상장 / 12=특례상장 등. 필수.",
            },
            "marketType": {
                "kind": "filter", "required": False, "example": "2",
                "desc": "시장 구분 코드(기본 2=코스닥).",
            },
            "currentPageSize": {
                "kind": "paging", "required": False, "example": "200",
                "desc": "최대 반환 행 수. 기본 200.",
            },
            "pageIndex": {
                "kind": "paging", "required": False, "example": "1",
                "desc": "페이지 번호(1부터).",
            },
        },
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
        "params": {
            "endDate": {
                "kind": "date", "required": True, "format": "YYYY-MM-DD",
                "example": "2026-07-02", "desc": "조회 종료일. 필수.",
            },
            "startDate": {
                "kind": "date", "required": False, "format": "YYYY-MM-DD",
                "example": "1999-01-01", "desc": "조회 시작일. 생략 시 1999-01-01.",
            },
            "currentPageSize": {
                "kind": "paging", "required": False, "example": "100",
                "desc": "최대 반환 행 수. 기본 100.",
            },
            "pageIndex": {
                "kind": "paging", "required": False, "example": "1",
                "desc": "페이지 번호(1부터).",
            },
        },
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
        "params": {
            "toDate": {
                "kind": "date", "required": True, "format": "YYYY-MM-DD",
                "example": "2026-07-02", "desc": "조회 종료일(상장일 상한). 필수.",
            },
            "fromDate": {
                "kind": "date", "required": False, "format": "YYYY-MM-DD",
                "example": "2000-01-01", "desc": "조회 시작일. 생략 시 2000-01-01.",
            },
            "marketType": {
                "kind": "filter", "required": False, "example": "2",
                "desc": "시장 구분 코드(기본 2=코스닥). 1=코스피 계열.",
            },
            "listTypeArrStr": {
                "kind": "filter", "required": False, "example": "01|02|03|04|05|",
                "desc": "상장유형 코드 파이프(|) 나열. 기본 '01|02|03|04|05|'(신규상장 전체). "
                        "특정 유형만 원하면 예 '01|'처럼 좁힌다.",
            },
            "currentPageSize": {
                "kind": "paging", "required": False, "example": "3000",
                "desc": "최대 반환 행 수. 기본 3000≈전량.",
            },
            "pageIndex": {
                "kind": "paging", "required": False, "example": "1",
                "desc": "페이지 번호(1부터).",
            },
            "orderStat": {
                "kind": "sort", "required": False, "example": "D",
                "desc": "정렬 방향. D=상장일 내림차순(최신순) / A=오름차순.",
            },
        },
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
        "params": {
            "toDate": {
                "kind": "date", "required": True, "format": "YYYY-MM-DD",
                "example": "2026-07-02", "desc": "조회 종료일(합병상장일 상한). 필수.",
            },
            "fromDate": {
                "kind": "date", "required": False, "format": "YYYY-MM-DD",
                "example": "2000-01-01", "desc": "조회 시작일. 생략 시 2000-01-01.",
            },
            "marketType": {
                "kind": "filter", "required": False, "example": "2",
                "desc": "시장 구분 코드(기본 2=코스닥). 1=코스피 계열.",
            },
            "listTypeArrStr": {
                "kind": "filter", "required": False, "example": "06|07|",
                "desc": "상장유형 코드 파이프(|) 나열. 기본 '06|07|'(합병상장·재상장).",
            },
            "currentPageSize": {
                "kind": "paging", "required": False, "example": "2000",
                "desc": "최대 반환 행 수. 기본 2000≈전량.",
            },
            "pageIndex": {
                "kind": "paging", "required": False, "example": "1",
                "desc": "페이지 번호(1부터).",
            },
            "orderStat": {
                "kind": "sort", "required": False, "example": "D",
                "desc": "정렬 방향. D=합병상장일 내림차순(최신순) / A=오름차순.",
            },
        },
    },
    "spac_merge_listing": {
        "path": "listinvstg/mergeListingCompany.do",
        "http": "post",
        "send_as": "data",
        "parser": "kind_list_with_code",
        "parser_kwargs": {
            "table_class": "list type-00 tmt30",
            # 기본 7열 + choicType(01~05) 선택 5열. choicTypeArrStr로 5열을 모두 켜둔다.
            "columns": [
                "회사명",
                "합병상장일",
                "상장유형",       # 'SPAC 존속합병' / 'SPAC 소멸합병'
                "증권구분",
                "업종",
                "국적",
                "상장주선인",
                "액면가",          # choicType 01
                "공모가",          # choicType 02
                "공모금액",        # choicType 03
                "주요제품",        # choicType 04 (SPAC은 보통 '기업 인수합병')
                "최초상장주식수",  # choicType 05
            ],
            # onclick="fnDetailView('44684','...')" 의 첫 인자 = 회사코드
            "code_column": "회사코드",
        },
        "prepare": _spac_merge_prepare,   # spacType(존속/소멸/전체) → listTypeArrStr
        "defaults": {
            # ── 화면 내부 고정값 ──
            "method": "searchMergeListingCompSub",
            "forward": "mergeListingCompany_sub",
            "searchCodeType": "",
            # 추가 5개 컬럼(액면가·공모가·공모금액·주요제품·최초상장주식수)을 모두 표시.
            # choicTypeArrStr가 컬럼 표시를 결정한다(choicTypeArr 리스트는 무시됨).
            "choicTypeArrStr": "01|02|03|04|05|",
            # 증권종류 전체(필터 안 함). secuGrpArrStr가 결정(secuGrpArr 리스트는 무시됨).
            "secuGrpArrStr": "0|ST|FS|MF|SC|RT|DR|",
            # ── 페이지네이션 / 정렬 ──
            "currentPageSize": "2000",
            "pageIndex": "1",
            "orderMode": "1",
            "orderStat": "D",
            # ── 필터(빈값 = 전체) ──
            "marketType": "",           # 빈값=전체 시장(1=코스피/2=코스닥)
            "searchCorpName": "",       # 회사명(부분일치) 또는 종목코드
            "searchCorpNameTmp": "",
            "isurCd": "",
            "repIsuSrtCd": "",
            "country": "",              # 국적 필터
            "industry": "",             # 업종 필터
            "repMajAgntDesignAdvserComp": "",
            "repMajAgntComp": "",       # 대표주선인(증권사)명 필터
            "designAdvserComp": "",
            # 존속(06)+소멸(07) 전체가 기본. prepare가 spacType으로 이 값을 덮어씀.
            "listTypeArrStr": "06|07|",
            "fromDate": "2000-01-01",
        },
        "required": ["toDate"],
        "screen": "SPAC(기업인수목적회사) 합병상장. spacType로 존속/소멸/전체 선택. "
                  "fromDate~toDate. 기존 merge_listing과 달리 전체 시장·SPAC 전용 컬럼 포함",
        "params": {
            "spacType": {
                "kind": "filter", "required": False, "example": "존속",
                "enum": ["존속", "소멸", "전체"],
                "desc": "SPAC 합병 유형. 존속=SPAC 존속합병(코드06) / 소멸=SPAC 소멸합병(코드07) / "
                        "전체=둘 다(기본). 내부적으로 listTypeArrStr로 변환된다.",
            },
            "toDate": {
                "kind": "date", "required": True, "format": "YYYY-MM-DD",
                "example": "2026-07-02", "desc": "조회 종료일(합병상장일 상한). 필수.",
            },
            "fromDate": {
                "kind": "date", "required": False, "format": "YYYY-MM-DD",
                "example": "2000-01-01", "desc": "조회 시작일. 생략 시 2000-01-01.",
            },
            "marketType": {
                "kind": "filter", "required": False, "example": "2",
                "desc": "시장 구분. 빈값=전체(사실상 코스닥) / 1=코스피 / 2=코스닥. "
                        "SPAC 합병상장은 대부분 코스닥.",
            },
            # 주의: 이 Sub 화면은 searchCorpName/isurCd/repMajAgntComp 등 회사·주선인
            # 필터를 서버단에서 무시한다(전체가 그대로 나옴). 회사명 검색은 결과를
            # 받은 뒤 DataFrame에서 거르는 방식으로 한다. → 여기 params에 노출하지 않음.
            "currentPageSize": {
                "kind": "paging", "required": False, "example": "2000",
                "desc": "최대 반환 행 수. 기본 2000≈전량.",
            },
            "pageIndex": {
                "kind": "paging", "required": False, "example": "1",
                "desc": "페이지 번호(1부터).",
            },
            "orderStat": {
                "kind": "sort", "required": False, "example": "D",
                "desc": "정렬 방향. D=합병상장일 내림차순(최신순) / A=오름차순.",
            },
        },
    },
    "pubofr_prog_com": {
        "path": "listinvstg/pubofrprogcom.do",
        "http": "post",
        "send_as": "data",
        "parser": "kind_list_with_code",
        "parser_kwargs": {
            "table_class": "list type-00 tmt30",
            "columns": [
                "회사명",
                "신고서제출일",
                "수요예측일정",
                "청약일정",
                "납입일",
                "확정공모가",
                "공모금액(백만원)",
                "상장예정일",
                "상장주선인/지정자문인",
            ],
            "code_column": "업무처리번호",
        },
        "defaults": {
            # ── 화면 내부 고정값(건드리지 말 것) ──
            # Main이 아니라 데이터를 주는 Sub 호출. forward/searchMode/searchCodeType
            # 도 화면이 요구하는 상수라 그대로 둔다.
            "method": "searchPubofrProgComSub",
            "forward": "pubofrprogcom_sub",
            "searchMode": "1",
            "searchCodeType": "",
            # ── 페이지네이션(원하면 override) ──
            # currentPageSize는 "한 번에 받을 최대 행 수"일 뿐 데이터 내용은 안 바꾼다.
            # 2000이면 사실상 전량. 더 받으려면 pageIndex로 다음 페이지.
            "currentPageSize": "2000",
            "pageIndex": "1",
            # ── 정렬 ──  orderStat: D=내림차순 / A=오름차순
            "orderMode": "1",
            "orderStat": "D",
            # ── 필터(빈값 = 전체 조회). 아래 params 참고 ──
            # 회사/발행사/주선인 등으로 좁힐 때만 값을 넣는다. 캡처된 브라우저
            # 요청은 searchCorpName/searchCorpNameTmp/isurCd에만 값이 있었다.
            "searchCorpName": "",       # 회사명(부분일치) 또는 종목코드
            "searchCorpNameTmp": "",    # ↑와 같은 값을 넣어야 함(화면이 둘 다 검사)
            "isurCd": "",               # 발행사 코드(종목코드 6자리 중 앞 5자리)
            "repIsuSrtCd": "",
            "bzProcsNo": "",            # 업무처리번호(특정 건 1개만 콕 집어 조회)
            "detailMarket": "",
            "marketType": "",
            "repMajAgntDesignAdvserComp": "",
            "repMajAgntComp": "",       # 대표주선인(증권사)명 필터
            "designAdvserComp": "",     # 지정자문인명 필터
            # ── 조회 기간(신고서제출일 기준) ──
            "fromDate": "2000-01-01",
        },
        "required": ["toDate"],
        "screen": "공모기업 진행현황. fromDate~toDate, searchCorpName/isurCd로 회사 필터 가능",
        # 호출자/MCP가 넘길 수 있는 파라미터 문서. defaults의 나머지 고정 키는 제외.
        # MCP 툴 스키마 예:  properties = {k: {"type": "string", "description": v["desc"]}
        #                                   for k, v in params.items()}
        #                    required   = [k for k, v in params.items() if v.get("required")]
        "params": {
            "toDate": {
                "kind": "date", "required": True, "format": "YYYY-MM-DD",
                "example": "2026-07-02",
                "desc": "조회 종료일(신고서제출일 기준 상한). 유일한 필수값.",
            },
            "fromDate": {
                "kind": "date", "required": False, "format": "YYYY-MM-DD",
                "example": "2000-01-01",
                "desc": "조회 시작일(신고서제출일 기준 하한). 생략 시 2000-01-01.",
            },
            "searchCorpName": {
                "kind": "filter", "required": False, "example": "363260",
                "desc": "회사명(부분일치) 또는 종목코드로 필터. 빈값이면 전체 공모기업.",
            },
            "searchCorpNameTmp": {
                "kind": "filter", "required": False, "example": "363260",
                "desc": "searchCorpName과 반드시 같은 값을 넣는다(화면이 두 필드를 함께 검사).",
            },
            "isurCd": {
                "kind": "filter", "required": False, "example": "36326",
                "desc": "발행사(법인) 코드 = 종목코드 6자리 중 앞 5자리. "
                        "예: 종목코드 363260 → isurCd 36326. 정확 매칭.",
            },
            "bzProcsNo": {
                "kind": "filter", "required": False, "example": "20200907000341",
                "desc": "업무처리번호. 특정 공모 건 1개만 콕 집어 조회할 때 사용(결과의 '업무처리번호' 컬럼값).",
            },
            "repMajAgntComp": {
                "kind": "filter", "required": False, "example": "KB증권",
                "desc": "대표주선인(증권사)명으로 필터.",
            },
            "designAdvserComp": {
                "kind": "filter", "required": False, "example": "",
                "desc": "지정자문인(코넥스)명으로 필터.",
            },
            "currentPageSize": {
                "kind": "paging", "required": False, "example": "2000",
                "desc": "한 번에 받을 최대 행 수(데이터 내용이 아니라 페이지 크기만 결정). "
                        "기본 2000이면 사실상 전량.",
            },
            "pageIndex": {
                "kind": "paging", "required": False, "example": "1",
                "desc": "페이지 번호(1부터). currentPageSize와 함께 페이지네이션.",
            },
            "orderStat": {
                "kind": "sort", "required": False, "example": "D",
                "desc": "정렬 방향. D=신고서제출일 내림차순(최신순) / A=오름차순.",
            },
        },
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
        "params": {
            "marketType": {
                "kind": "filter", "required": True, "example": "1",
                "enum": ["1", "2"],
                "desc": "시장 구분. 1=코스피 / 2=코스닥. 필수.",
            },
            "selDate": {
                "kind": "date", "required": True, "format": "YYYY-MM-DD",
                "example": "2026-07-02", "desc": "조회 대상일. 필수.",
            },
            "currentPageSize": {
                "kind": "paging", "required": False, "example": "100",
                "desc": "최대 반환 행 수. 기본 100.",
            },
            "pageIndex": {
                "kind": "paging", "required": False, "example": "1",
                "desc": "페이지 번호(1부터).",
            },
        },
    },
    "disclosure_details": {
        "path": "disclosure/details.do",
        "http": "post",
        "send_as": "data",
        "parser": "disclosure_details",
        "prepare": _disclosure_details_prepare,   # disclosureType → 카테고리 raw 필드
        "defaults": _disclosure_details_defaults(),
        "required": ["toDate"],
        "screen": "공시 상세검색. disclosureType로 공시유형 필터(예 '공정공시_영업실적'), "
                  "marketType로 시장(1=유가/2=코스닥), fromDate~toDate 기간 조회. "
                  "총 건수는 많을 수 있으니 currentPageSize(≤100)+pageIndex로 페이지네이션.",
        "params": {
            "disclosureType": {
                "kind": "filter", "required": False, "example": "공정공시_영업실적",
                "enum": ["공정공시_영업실적"],
                "desc": "공시유형 필터. 등록된 키('공정공시_영업실적'=공정공시>매출액 영업손익 등 "
                        "영업실적) 또는 'cat:code' 형태(예 '03:0204')로 직접 지정. "
                        "생략 시 전체 유형. 새 유형은 endpoints.DISCLOSURE_TYPE_CODES에 추가.",
            },
            "toDate": {
                "kind": "date", "required": True, "format": "YYYY-MM-DD",
                "example": "2026-07-15", "desc": "조회 종료일(공시일 상한). 필수.",
            },
            "fromDate": {
                "kind": "date", "required": False, "format": "YYYY-MM-DD",
                "example": "2025-07-15",
                "desc": "조회 시작일(공시일 하한). 생략 시 2000-01-01. "
                        "브라우저 기본은 종료일 기준 1년 전.",
            },
            "marketType": {
                "kind": "filter", "required": False, "example": "1",
                "enum": ["1", "2"],
                "desc": "시장 구분. 1=유가증권(코스피) / 2=코스닥. 생략 시 전체 시장.",
            },
            "searchCorpName": {
                "kind": "filter", "required": False, "example": "삼성전자",
                "desc": "회사명(부분일치) 또는 종목코드로 필터. 빈값이면 전체.",
            },
            "currentPageSize": {
                "kind": "paging", "required": False, "example": "100",
                "desc": "한 페이지 행 수. 화면 최대는 100(초과는 서버가 무시할 수 있음). "
                        "전량은 pageIndex로 페이지를 넘겨 수집.",
            },
            "pageIndex": {
                "kind": "paging", "required": False, "example": "1",
                "desc": "페이지 번호(1부터).",
            },
            "orderStat": {
                "kind": "sort", "required": False, "example": "D",
                "desc": "정렬 방향. D=공시일 내림차순(최신순) / A=오름차순.",
            },
        },
    },
    # ── 투자유의(관리종목 등) ──────────────────────────────────────
    "admin_issue": {
        "path": "investwarn/adminissue.do",
        "http": "post",
        "send_as": "data",
        "parser": "labeled_table",
        "parser_kwargs": {
            # <thead>가 비어 있고 컬럼명은 summary="종목명, 지정일, 지정사유"에만 있다.
            "table_class": "list type-00 tmt30",
            "columns": ["종목명", "지정일", "지정사유"],
        },
        "defaults": {
            # ── 화면 내부 고정값 ──
            "method": "searchAdminIssueSub",
            "forward": "adminissue_sub",
            "searchMode": "1",
            "searchCodeType": "",
            # ── 페이지네이션 / 정렬 ──
            # 서버가 큰 currentPageSize를 허용(5000이면 사실상 전량).
            "currentPageSize": "5000",
            "pageIndex": "1",
            "orderMode": "1",
            "orderStat": "D",
            # ── 필터(빈값 = 전체) ──
            "marketType": "",          # 빈값=전체 / 1=코스피 / 2=코스닥
            "searchCorpName": "",
            "repIsuSrtCd": "",
            "paxreq": "",
            "outsvcno": "",
        },
        "required": [],   # 날짜 없음 — 현시점 지정 목록 스냅샷
        "screen": "현재 관리종목 지정 목록(스냅샷). marketType로 시장 필터. "
                  "반환: 종목명·지정일·지정사유. 코드가 필요하면 corp_list와 종목명으로 조인.",
        "params": {
            "marketType": {
                "kind": "filter", "required": False, "example": "1",
                "enum": ["", "1", "2"],
                "desc": "시장 구분. 빈값=전체 / 1=코스피 / 2=코스닥.",
            },
            "currentPageSize": {
                "kind": "paging", "required": False, "example": "5000",
                "desc": "최대 반환 행 수. 기본 5000≈전량(서버가 큰 값 허용).",
            },
            "pageIndex": {
                "kind": "paging", "required": False, "example": "1",
                "desc": "페이지 번호(1부터).",
            },
            "orderStat": {
                "kind": "sort", "required": False, "example": "D",
                "desc": "정렬 방향. D=지정일 내림차순(최신순) / A=오름차순.",
            },
        },
    },
}


def get(name: str) -> dict:
    from .exceptions import UnknownEndpointError

    if name not in ENDPOINTS:
        raise UnknownEndpointError(
            f"Unknown endpoint: {name!r}. Available: {sorted(ENDPOINTS)}"
        )
    return ENDPOINTS[name]
