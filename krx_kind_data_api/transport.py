"""KIND(kind.krx.co.kr) 저수준 호출.

data.krx.co.kr와 달리 OTP/로그인이 없다. 화면별 `.do` 엔드포인트에 폼
파라미터를 POST(또는 GET)하면 HTML 조각이 돌아오고, 그걸 파싱한다.
이 모듈은 "디코딩된 HTML 문자열"까지만 책임지고, 파싱은 parsers.py가 한다.
"""
from __future__ import annotations

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
    """접수번호(acptno)로 KIND 공시 뷰어 원문 URL 생성."""
    return (
        f"{BASE}/common/disclsviewer.do?method=search"
        f"&acptno={acptno}&docno=&viewerhost=&viewerport="
    )
