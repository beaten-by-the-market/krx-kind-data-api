"""HTML 응답 → DataFrame 파서 레지스트리.

KIND 화면은 두 부류다.
  1) 평범한 HTML 테이블 → `pd.read_html`로 한 방에 (`read_html`)
  2) 회사코드가 행의 onclick(`fnDetailView('00126')` 등)에만 있는 목록 화면 →
     read_html로 보이는 컬럼을 뽑고, onclick에서 코드를 추출해 붙임
     (`kind_list_with_code`)

새 파서가 필요하면 함수를 만들어 `register_parser(name, func)`로 등록하면
엔드포인트 카탈로그에서 `"parser": name`으로 가리킬 수 있다.
"""
from __future__ import annotations

import re
from io import StringIO
from typing import Any, Callable, Optional

import pandas as pd
from bs4 import BeautifulSoup

from .exceptions import KINDParseError

# 목록 화면에서 회사코드가 박혀 있는 onclick 핸들러들
_CODE_RE = re.compile(
    r"(?:fnDetailView|companysummary_open|openCompanyInfoNew|fnViewDetail)"
    r"\('([A-Za-z0-9]+)'"
)


def read_html(
    html: str, *, table_index: int = 0, header: Optional[int] = 0, **_: Any
) -> pd.DataFrame:
    """가장 일반적인 경우: HTML 안의 table_index번째 표를 DataFrame으로."""
    try:
        tables = pd.read_html(StringIO(html), header=header)
    except ValueError as e:  # "No tables found"
        raise KINDParseError(f"No HTML table found ({e})") from e
    if table_index >= len(tables):
        raise KINDParseError(
            f"table_index={table_index} 이지만 표는 {len(tables)}개뿐"
        )
    return tables[table_index]


def kind_list_with_code(
    html: str,
    *,
    table_class: Optional[str] = None,
    table_index: int = 0,
    header: Optional[int] = None,
    columns: Optional[list] = None,
    code_column: str = "회사코드",
    **_: Any,
) -> pd.DataFrame:
    """목록 화면: 보이는 컬럼은 read_html로, 회사코드는 onclick에서 추출해 붙임.

    table_class를 주면 그 클래스의 표를, 없으면 table_index번째 표를 대상으로
    한다(read_html과 BeautifulSoup의 표 순서가 같다는 가정).

    이런 목록 화면은 보통 <thead>가 없어 header=None이 기본이다. columns를 주면
    보이는 컬럼명을 그 순서로 지정한다(회사코드는 그 뒤에 자동으로 붙음).
    """
    soup = BeautifulSoup(html, "html.parser")
    if table_class is not None:
        table = soup.find("table", class_=table_class)
    else:
        tables = soup.find_all("table")
        table = tables[table_index] if table_index < len(tables) else None
    if table is None:
        raise KINDParseError(
            f"대상 테이블을 못 찾음 (class={table_class!r}, index={table_index})"
        )

    df = read_html(str(table), table_index=0, header=header)
    if columns is not None:
        df.columns = list(columns)[: len(df.columns)]

    body = table.find("tbody") or table
    codes = []
    for tr in body.find_all("tr"):
        m = _CODE_RE.search(str(tr))
        codes.append(m.group(1) if m else None)
    # 헤더 행이 tbody 밖에 있으면 행 수가 맞는다. 어긋나면 코드 부착 생략.
    if len(codes) == len(df):
        df[code_column] = codes
    return df


def today_disclosure(html: str, **_: Any) -> pd.DataFrame:
    """당일공시(todaydisclosure.do) 전용 — 회사코드 + 공시 원문 URL까지 추출."""
    from .transport import disclosure_viewer_url

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="list type-00 mt10") or soup.find("table")
    if table is None or not table.find("tbody"):
        raise KINDParseError("당일공시 테이블을 찾지 못함")

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cols = tr.find_all("td")
        if len(cols) < 4:
            continue
        company_a = cols[1].find("a")
        code = ""
        if company_a and company_a.has_attr("onclick"):
            m = _CODE_RE.search(company_a["onclick"])
            code = m.group(1) if m else ""
        title_a = cols[2].find("a")
        title = (title_a.get("title", "").strip() if title_a else cols[2].text.strip())
        url = ""
        if title_a and title_a.has_attr("onclick"):
            m = re.search(r"openDisclsViewer\('(\d+)'", title_a["onclick"])
            if m:
                url = disclosure_viewer_url(m.group(1))
        rows.append(
            {
                "시간": cols[0].text.strip(),
                "회사코드": code,
                "회사명": cols[1].text.strip(),
                "공시제목": title,
                "제출인": cols[3].text.strip(),
                "상세URL": url,
            }
        )
    # 결과가 0건이어도 고정 컬럼 스키마를 유지한다(빈 df도 컬럼 보존).
    return pd.DataFrame(rows, columns=[
        "시간", "회사코드", "회사명", "공시제목", "제출인", "상세URL",
    ])


def disclosure_details(html: str, **_: Any) -> pd.DataFrame:
    """공시 상세검색(details.do) 전용.

    todaydisclosure.do와 표 클래스는 같지만(list type-00 mt10) 맨 앞에 '번호' 열이
    하나 더 있어 컬럼 오프셋이 다르다. 회사코드는 회사 셀의
    companysummary_open('04270'), 공시 원문 접수번호는 공시제목 셀의
    openDisclsViewer('20260714000204','')에서 뽑는다. 시장(유가/코스닥)은 회사 셀의
    아이콘 alt에서 읽는다.
    """
    from .transport import disclosure_viewer_url

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="list type-00 mt10") or soup.find("table")
    if table is None or not table.find("tbody"):
        raise KINDParseError("공시 상세검색 테이블을 찾지 못함")

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cols = tr.find_all("td")
        if len(cols) < 5:  # 번호/시간/회사명/공시제목/제출인(+차트) 최소 5열
            continue
        # 회사 셀: 시장 아이콘 alt + companysummary_open('회사코드')
        corp_cell = cols[2]
        market_img = corp_cell.find("img", class_="legend")
        market = market_img["alt"].strip() if (market_img and market_img.has_attr("alt")) else ""
        corp_a = corp_cell.find("a")
        code = ""
        if corp_a is not None and corp_a.has_attr("onclick"):
            m = _CODE_RE.search(corp_a["onclick"])
            code = m.group(1) if m else ""
        corp_name = corp_a.text.strip() if corp_a is not None else corp_cell.text.strip()
        # 공시제목 셀: openDisclsViewer('접수번호','')
        title_a = cols[3].find("a")
        title = (title_a.get("title", "").strip() if title_a else cols[3].text.strip())
        acptno, url = "", ""
        if title_a is not None and title_a.has_attr("onclick"):
            m = re.search(r"openDisclsViewer\('(\d+)'", title_a["onclick"])
            if m:
                acptno = m.group(1)
                url = disclosure_viewer_url(acptno)
        rows.append(
            {
                "번호": cols[0].text.strip(),
                "시간": cols[1].text.strip(),
                "시장": market,
                "회사코드": code,
                "회사명": corp_name,
                "공시제목": title,
                "접수번호": acptno,
                "제출인": cols[4].text.strip(),
                "상세URL": url,
            }
        )
    # 결과가 0건이어도 고정 컬럼 스키마를 유지한다.
    return pd.DataFrame(rows, columns=[
        "번호", "시간", "시장", "회사코드", "회사명",
        "공시제목", "접수번호", "제출인", "상세URL",
    ])


def stock_issue_list(html: str, **_: Any) -> pd.DataFrame:
    """증자·상장방식별 주식발행 현황(stockissuelist.do) 전용.

    이 화면은 코드가 두 군데에 있다:
      - 회사코드: 회사 셀의 companysummary_open('01100')  (5자리)
      - 접수번호: 행(<tr>) onclick fnDetailView('20260715000647')  (14자리, 공시 링크)
    범용 kind_list_with_code는 행 onclick(fnDetailView)을 먼저 잡아 회사코드 대신
    접수번호를 넣어버리므로 전용 파서로 둘 다 뽑는다. 결과 없음 플레이스홀더
    행(colspan 1개 td)은 컬럼 수로 걸러진다.
    """
    from .transport import disclosure_viewer_url

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="list type-00") or soup.find("table")
    if table is None or not table.find("tbody"):
        raise KINDParseError("증자현황 테이블을 찾지 못함")

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cols = tr.find_all("td")
        if len(cols) < 6:   # 데이터 행은 6열. '조회된 결과값이 없습니다' 등은 스킵
            continue
        # 회사코드: 회사 셀의 companysummary_open('01100')
        code = ""
        corp_a = cols[0].find("a")
        if corp_a is not None and corp_a.has_attr("onclick"):
            m = re.search(r"companysummary_open\('([A-Za-z0-9]+)'", corp_a["onclick"])
            code = m.group(1) if m else ""
        # 접수번호: 행 onclick fnDetailView('20260715000647')
        acptno = ""
        if tr.has_attr("onclick"):
            m = re.search(r"fnDetailView\('(\d+)'", tr["onclick"])
            acptno = m.group(1) if m else ""
        rows.append(
            {
                "회사명": cols[0].get_text(strip=True),
                "상장(예정)일": cols[1].get_text(strip=True),
                "상장방식": cols[2].get_text(strip=True),
                "발행주식수": cols[3].get_text(strip=True),
                "액면가": cols[4].get_text(strip=True),
                "발행사유": cols[5].get_text(strip=True),
                "회사코드": code,
                "접수번호": acptno,
                "상세URL": disclosure_viewer_url(acptno) if acptno else "",
            }
        )
    # 결과가 0건이어도 고정 컬럼 스키마를 유지한다.
    return pd.DataFrame(rows, columns=[
        "회사명", "상장(예정)일", "상장방식", "발행주식수", "액면가",
        "발행사유", "회사코드", "접수번호", "상세URL",
    ])


def labeled_table(
    html: str,
    *,
    columns: list,
    table_class: Optional[str] = None,
    table_index: int = 0,
    **_: Any,
) -> pd.DataFrame:
    """헤더가 비어(컬럼명은 summary 속성에만) 코드 링크도 없는 단순 목록 표.

    보이는 <td>를 columns 순서로 그대로 매핑한다. 관리종목/불성실공시/상장폐지처럼
    코드 onclick 없이 텍스트만 있는 화면용. 열 수가 columns보다 적은 행
    ('조회된 결과값이 없습니다' 등 플레이스홀더)은 스킵한다.
    """
    soup = BeautifulSoup(html, "html.parser")
    if table_class is not None:
        table = soup.find("table", class_=table_class)
    else:
        tables = soup.find_all("table")
        table = tables[table_index] if table_index < len(tables) else None
    if table is None or not table.find("tbody"):
        raise KINDParseError(
            f"대상 테이블을 못 찾음 (class={table_class!r}, index={table_index})"
        )
    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < len(columns):
            continue
        rows.append({c: cells[i].get_text(strip=True) for i, c in enumerate(columns)})
    # 결과가 0건이어도 지정한 columns 스키마를 유지한다.
    return pd.DataFrame(rows, columns=list(columns))


def _pad6(code: Any) -> str:
    """종목코드 6자리 정규화. 우선주 등 문자 섞인 코드('0117P0')는 그대로 둔다.

    결측이 섞인 숫자 컬럼은 pandas가 float로 읽어 '30660.0'처럼 들어오므로
    끝의 '.0'을 떼고, NaN/빈값은 ''로 정규화한다.
    """
    s = str(code).strip()
    if s.endswith(".0"):        # float 표기(NaN 섞인 숫자 컬럼)
        s = s[:-2]
    if not s or s.lower() == "nan":
        return ""
    return f"{int(s):06d}" if s.isdigit() else s


def corp_list(html: str, **_: Any) -> pd.DataFrame:
    """상장법인목록(corpList.do?method=download) — 종목코드를 6자리 문자열로 정규화."""
    df = read_html(html, table_index=0, header=0)
    if "종목코드" in df.columns:
        df["종목코드"] = df["종목코드"].map(_pad6)
    return df


_PARSERS: dict[str, Callable[..., pd.DataFrame]] = {
    "read_html": read_html,
    "kind_list_with_code": kind_list_with_code,
    "today_disclosure": today_disclosure,
    "disclosure_details": disclosure_details,
    "stock_issue_list": stock_issue_list,
    "labeled_table": labeled_table,
    "corp_list": corp_list,
}


def register_parser(name: str, func: Callable[..., pd.DataFrame]) -> None:
    """외부에서 커스텀 파서를 추가."""
    _PARSERS[name] = func


def get_parser(name: str) -> Callable[..., pd.DataFrame]:
    if name not in _PARSERS:
        raise KINDParseError(
            f"Unknown parser: {name!r}. Available: {sorted(_PARSERS)}"
        )
    return _PARSERS[name]
