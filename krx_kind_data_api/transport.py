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
_CONTENT_ID_RE = re.compile(r"option\s+value=['\"](\d{14})\|([YN])")
# searchContents 응답에서 완성 본문 URL(docno 포함)을 뽑는다.
_DOCPATH_RE = re.compile(r"(https?://[^\s'\"]+?\.htm)")


def _shell_url(acptno: str) -> str:
    return (
        f"{BASE}/common/disclsviewer.do?method=search"
        f"&acptno={acptno}&docno=&viewerhost=&viewerport="
    )


def _shell_html(
    acptno: str,
    *,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> str:
    """공시 뷰어 shell(EUC-KR) HTML."""
    return request(
        "common/disclsviewer.do",
        {"method": "search", "acptno": acptno, "docno": "",
         "viewerhost": "", "viewerport": ""},
        http="get", encoding="euc-kr", session=session, timeout=timeout,
    )


def company_summary(
    isur_cd: str,
    *,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> dict:
    """KIND 회사코드(isurCd, 5자리) → 회사 기본정보 dict.

    공시 목록의 `회사코드` 컬럼이 이 값이다. **상장폐지된 회사도 조회된다** —
    `corp_list`(상장법인목록)는 현재 상장사만 담아 폐지 종목의 종목코드를 못 준다.

    반환 키(화면의 항목명 그대로): 한글명, 영문명, 표준코드, 종목코드, 설립일,
    시장구분('코스닥 상장폐지' 처럼 상태 포함), 상장일, 대표이사, 업종 … .
    """
    from bs4 import BeautifulSoup

    html = request(
        "common/companysummary.do",
        {"method": "searchCompanySummaryOvrvwDetail", "strIsurCd": str(isur_cd),
         "lstCd": "undefined"},
        http="get", encoding="utf-8", session=session, timeout=timeout,
    )
    out: dict = {}
    for tr in BeautifulSoup(html, "html.parser").find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip()
                 for c in tr.find_all(["th", "td"])]
        for k, v in zip(cells[0::2], cells[1::2]):   # th/td 가 번갈아 온다
            if k and k not in out:
                out[k] = v
    if not out.get("종목코드"):
        raise KINDFetchError(f"회사 정보를 찾지 못함(isurCd={isur_cd}).")
    return out


def rep_isu_srt_cd(
    code: str,
    *,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> str:
    """`disclosure_details` 의 회사 필터 값(`repIsuSrtCd`)을 만든다.

    - 6자리 종목코드('005930') → 'A005930'
    - 5자리 KIND 회사코드('41821') → company_summary 로 종목코드를 찾아 'A418210'
      (상장폐지 종목도 된다)
    """
    code = str(code).strip()
    if code.upper().startswith("A") and len(code) == 7:
        return code.upper()
    if len(code) == 6:
        return "A" + code
    return "A" + company_summary(code, session=session, timeout=timeout)["종목코드"]


def resolve_content_url(
    acptno: str,
    *,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> str:
    """접수번호 → 본문 실제 URL. **docno를 몰라도 된다.**

    shell 의 `docpathfrm` 폼(=`method=searchContents`)을 그대로 재현하면 서버가
    docno 가 박힌 완성 URL을 돌려준다. XHR 이 아니라 iframe 타깃 폼 전송이라
    requests 로 재현된다(예전엔 봇 차단으로 requests 불가라고 봤으나 오판이었다).

    ⚠️ 폼 필드 `docNo` 에는 **content_id** 를 넣어야 한다. 접수번호를 넣으면
    blank.html 이 온다. 정정공시는 content_id 후보가 여럿이라 순차 시도한다.

    docno 가 공시유형·시장·조치종류마다 다른 폼(예: 매매거래정지는 코스닥 정지
    70797 / 해제 70799, 유가 68060·68054·99808)에서 매핑표 없이 쓸 수 있다.
    docno 가 고정인 폼은 `disclosure_content_url(acptno, docno=...)` 가 요청 1회
    더 적으므로 그쪽이 낫다.
    """
    s = session or requests.Session()
    shell = _shell_html(acptno, session=s, timeout=timeout)
    opts = _CONTENT_ID_RE.findall(shell)
    if not opts:
        raise KINDFetchError(
            f"content_id를 찾지 못함(acptno={acptno}). shell 구조 변경 또는 문서 없음."
        )
    cands = ([cid for cid, flag in opts if flag == "Y"]
             + [cid for cid, flag in reversed(opts) if flag != "Y"])
    for cid in cands:
        html = request(
            "common/disclsviewer.do",
            {"method": "searchContents", "docNo": cid},
            http="post", send_as="data", encoding="euc-kr",
            session=s, timeout=timeout,
        )
        m = _DOCPATH_RE.search(html)
        if m:
            return m.group(1)
    raise KINDFetchError(
        f"본문 URL 미확보(acptno={acptno}). content_id 후보 {len(cands)}개가 모두 "
        f"blank.html 이었다."
    )


def disclosure_content_ids(
    acptno: str,
    *,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> list:
    """shell HTML의 content_id 후보를 **우선순위 순**으로 반환.

    <option value='{14자리}|{Y|N}'> 의 Y/N 플래그가 현재 유효한 문서를 가리킨다.
    - 원공시: option 1개.
    - 정정공시: 2개(`|N` 원공시, `|Y` 정정본). 정정의 정정이면 3개 이상.

    정정공시에서 `|N`(원공시)의 content_id 를 정정 접수번호와 조합하면 404 가 난다.
    그래서 `|Y` 를 앞에 두고, 그 다음 나머지를 역순(최신 우선)으로 반환한다.
    같은 날 정정이 2건이면 shell 만으로는 확정할 수 없어 호출 측에서 순차 시도해야 한다.
    """
    opts = _CONTENT_ID_RE.findall(
        _shell_html(acptno, session=session, timeout=timeout)
    )
    if not opts:
        raise KINDFetchError(
            f"content_id를 찾지 못함(acptno={acptno}). shell 구조 변경 또는 문서 없음."
        )
    return ([cid for cid, flag in opts if flag == "Y"]
            + [cid for cid, flag in reversed(opts) if flag != "Y"])


def disclosure_content_id(
    acptno: str,
    *,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> str:
    """shell HTML에서 본문 content_id(14자리) 추출. 접수번호와 다를 수 있다.

    option 이 여러 개면 `|Y`(현재 유효 문서)를 고른다. 원공시는 option 이 하나뿐이라
    기존 동작과 같고, 정정공시에서만 결과가 달라진다(예전에는 원공시 것을 반환해 404).
    후보를 모두 보려면 disclosure_content_ids 를 쓴다.
    """
    return disclosure_content_ids(acptno, session=session, timeout=timeout)[0]


def disclosure_content_url(
    acptno: str,
    *,
    docno: Optional[str] = None,
    basis: Optional[str] = None,   # "separate" | "consolidated" — docno 없을 때 잠정실적용
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> str:
    """접수번호 → 공시 본문(iframe) 실제 URL.

    docno 결정 우선순위: 명시 docno > basis(잠정실적 별도/연결) 매핑 >
    **searchContents 조회**(docno 자동 해석, `resolve_content_url`).

    셋 다 요청 1~2회로 끝나며 Selenium 은 더 이상 필요 없다. docno 를 아는 폼은
    요청이 1회 적으니 docno/basis 를 주는 쪽이 여전히 빠르다.
    """
    if docno is None:
        if basis in DOCNO_JAMJEONG:
            docno = DOCNO_JAMJEONG[basis]
        else:
            # docno 미상(임의 폼) — 서버에 직접 물어본다.
            return resolve_content_url(acptno, session=session, timeout=timeout)
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
