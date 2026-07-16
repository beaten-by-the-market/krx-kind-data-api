"""KIND(kind.krx.co.kr) 저수준 호출.

data.krx.co.kr와 달리 OTP/로그인이 없다. 화면별 `.do` 엔드포인트에 폼
파라미터를 POST(또는 GET)하면 HTML 조각이 돌아오고, 그걸 파싱한다.
이 모듈은 "디코딩된 HTML 문자열"까지만 책임지고, 파싱은 parsers.py가 한다.
"""
from __future__ import annotations

import re
from typing import Optional

import requests

from .exceptions import KINDFetchError

BASE = "https://kind.krx.co.kr"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# corpList 다운로드 등에서 쓰는 시장 코드
MARKETS = {
    "kospi": "stockMkt",
    "kosdaq": "kosdaqMkt",
    "konex": "konexMkt",
}


def _url(path: str) -> str:
    """'listinvstg/mergeListingCompany.do' → 절대 URL. 이미 절대 URL이면 그대로."""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{BASE}/{path.lstrip('/')}"


def request(
    path: str,
    params: Optional[dict] = None,
    *,
    http: str = "post",
    send_as: str = "params",
    encoding: str = "utf-8",
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> str:
    """KIND `.do` 엔드포인트를 호출하고 디코딩된 HTML 문자열을 반환.

    Parameters
    ----------
    path : `.do` 경로(예: "listinvstg/mergeListingCompany.do") 또는 절대 URL
    params : 폼 파라미터
    http : "post" | "get"
    send_as : "params"(쿼리스트링) | "data"(요청 본문) — POST일 때만 의미 있음
    encoding : 응답 디코딩 인코딩 ("utf-8" | "euc-kr" 등)
    session : 재사용할 requests.Session (없으면 매 호출 새로 생성)
    """
    s = session or requests.Session()
    url = _url(path)
    headers = {"User-Agent": USER_AGENT, "Referer": f"{BASE}/"}
    params = params or {}

    try:
        if http.lower() == "get":
            resp = s.get(url, params=params, headers=headers, timeout=timeout)
        elif send_as == "data":
            resp = s.post(url, data=params, headers=headers, timeout=timeout)
        else:
            resp = s.post(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise KINDFetchError(f"KIND request failed: {url} ({e})") from e

    if not resp.ok or not resp.content:
        raise KINDFetchError(
            f"KIND fetch failed: {url} status={resp.status_code} "
            f"bytes={len(resp.content)}"
        )

    resp.encoding = encoding
    return resp.text


def disclosure_viewer_url(acptno: str) -> str:
    """접수번호(acptno)로 KIND 공시 뷰어 **shell** URL 생성.

    이건 JS로 채워지는 빈 껍데기다. 안 iframe의 진짜 본문 URL은
    disclosure_content_url()로 얻는다.
    """
    return (
        f"{BASE}/common/disclsviewer.do?method=search"
        f"&acptno={acptno}&docno=&viewerhost=&viewerport="
    )


# ── 공시 본문(iframe) 실제 URL ─────────────────────────────────────────
# shell(disclsviewer.do)은 빈 껍데기이고, 본문은 iframe 안
#   {BASE}/external/{YYYY}/{MM}/{DD}/{acptno[8:14]}/{content_id}/{docno}.htm
# 에 있다. 3조각이 필요하다:
#   1) 날짜 + acptno[8:14](접수번호 seq, 종목코드 아님) ← 접수번호에서 바로
#   2) content_id(14자리) ← shell HTML의 <option value='...|Y'>에서 정적 추출
#   3) docno(서식코드) ← 폼 종류로 결정. 잠정실적 별도=99620 / 연결=99626.
# docno를 모르는 임의 폼은 selenium_viewer.disclosure_content_url_selenium 폴백을 쓴다.

# 잠정실적 서식코드(docno). 다른 공시유형은 값이 다르다.
DOCNO_JAMJEONG = {"separate": "99620", "consolidated": "99626"}
_CONTENT_ID_RE = re.compile(r"option\s+value=['\"](\d{14})\|")


def disclosure_content_id(
    acptno: str,
    *,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> str:
    """shell HTML에서 본문 content_id(14자리) 추출. 접수번호와 다를 수 있다.

    관련공시·첨부가 있으면 <option>이 여러 개일 수 있는데 첫 번째가 주 문서다.
    """
    html = request(
        "common/disclsviewer.do",
        {"method": "search", "acptno": acptno, "docno": "",
         "viewerhost": "", "viewerport": ""},
        http="get", encoding="euc-kr", session=session, timeout=timeout,
    )
    m = _CONTENT_ID_RE.search(html)      # 첫 <option value='...|Y'> = 주 문서
    if not m:
        raise KINDFetchError(
            f"content_id를 찾지 못함(acptno={acptno}). shell 구조 변경 또는 문서 없음."
        )
    return m.group(1)


def disclosure_content_url(
    acptno: str,
    *,
    docno: Optional[str] = None,
    basis: Optional[str] = None,   # "separate" | "consolidated" — docno 없을 때 잠정실적용
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> str:
    """접수번호 → 공시 본문(iframe) 실제 URL.

    docno 결정 우선순위: 명시 docno > basis(잠정실적 별도/연결) 매핑.
    둘 다 없으면 ValueError(→ 임의 폼은 selenium_viewer 폴백 사용).
    """
    if docno is None:
        if basis in DOCNO_JAMJEONG:
            docno = DOCNO_JAMJEONG[basis]
        else:
            raise ValueError(
                "docno 또는 basis('separate'/'consolidated')가 필요합니다. "
                "임의 공시유형은 selenium_viewer.disclosure_content_url_selenium을 쓰세요."
            )
    cid = disclosure_content_id(acptno, session=session, timeout=timeout)
    y, m, d = acptno[0:4], acptno[4:6], acptno[6:8]
    return f"{BASE}/external/{y}/{m}/{d}/{acptno[8:14]}/{cid}/{docno}.htm"


def disclosure_content_html(
    acptno: str,
    *,
    encoding: str = "utf-8",
    session: Optional[requests.Session] = None,
    timeout: int = 30,
    **kw,
) -> str:
    """본문 URL을 열어 디코딩된 HTML 반환. (kw는 disclosure_content_url로 전달)

    shell은 EUC-KR이지만 본문 .htm은 <meta charset=UTF-8>이라 기본 encoding='utf-8'.
    """
    url = disclosure_content_url(acptno, session=session, timeout=timeout, **kw)
    return request(url, {}, http="get", encoding=encoding,
                   session=session, timeout=timeout)
