# 핸드오프: 공시 본문(iframe) URL 엔드포인트 추가

> 목표: 접수번호(`acptno`)로 KIND 공시 **본문 HTML의 실제 URL**(`/external/.../*.htm`)을 돌려주는 기능 추가.
> 지금 `transport.disclosure_viewer_url(acptno)`는 **껍데기(shell)** URL만 만든다. 그 안 iframe의 진짜 본문 URL을 얻는 게 이 작업.

이 문서만 보고 바로 구현할 수 있게 **메커니즘 → 설계 결정 → 붙여넣을 코드 → 엣지케이스 → (선택)엔드포인트·MCP 노출** 순으로 정리한다.

---

## 0. TL;DR

- shell(`disclsviewer.do?...`)은 JS로 채워지는 빈 껍데기. 본문은 iframe 안
  `https://kind.krx.co.kr/external/{YYYY}/{MM}/{DD}/{acptno[8:14]}/{content_id}/{docno}.htm` 에 있다.
- 필요한 3조각:
  1. **날짜 + `acptno[8:14]`** ← 접수번호에서 바로. (⚠️ 4번째 슬롯은 **종목코드가 아니라 접수번호 seq**다.)
  2. **`content_id`** ← shell HTML 안 `<option value='{14자리}|Y'>` 에 정적으로 들어있음. **requests로 추출 가능.**
  3. **`docno`(서식코드)** ← shell엔 없고 JS(`searchContents`, 봇 차단)로만 옴. **폼 종류로 결정**: 잠정실적 별도=`99620`, 연결=`99626`.
- **권장 구현**: requests-only 함수 `disclosure_content_url(acptno, docno=...)` (의존성 추가 없음).
  `docno`를 모르는 임의 폼은 **Selenium 폴백**(선택 의존성)으로 `docLocPath`를 직접 읽는다.

---

## 1. 배경 — 왜 shell만으론 안 되나

`kind_url = disclosure_viewer_url(acptno)` = `disclsviewer.do?method=search&acptno=...` 은
`<iframe id="docViewFrm" src="">` 가 **빈 채로** 오고, 로드 후 JS가 `searchContents` AJAX를 호출해
`docLocPath`(진짜 본문 URL)를 채운다. 그 AJAX는 봇을 `blank.html`로 리다이렉트한다(정적 requests 불가).

그러나 **`content_id`는 shell 정적 HTML에 이미 있다**:

```html
<select id="mainDoc" ...>
  <option value="">본문선택</option>
  <option value='20260629001475|Y' selected="selected">영업(잠정)실적(공정공시) (2026.06.29)</option>
</select>
```

`20260629001475` 가 본문 URL의 5번째 슬롯(**content_id**). **주의: 이 값은 접수번호와 다르다**
(위 예시 접수번호는 `20260629000856`, content_id는 `20260629001475`).

## 2. 본문 URL 조립 공식 (검증됨)

```
https://kind.krx.co.kr/external/{acptno[0:4]}/{acptno[4:6]}/{acptno[6:8]}/{acptno[8:14]}/{content_id}/{docno}.htm
```

실측 예 (지역난방공사 별도 잠정실적):
- acptno `20260629000856` → 날짜 `2026/06/29`, 슬롯4 `000856`
- content_id `20260629001475` (shell option에서 추출)
- docno `99620` (별도)
- → `https://kind.krx.co.kr/external/2026/06/29/000856/20260629001475/99620.htm` → **HTTP 200, 본문 HTML**

**docno = 폼 종류로 결정** (개정전/개정후 무관):
| 폼 | docno |
|---|---|
| 영업(잠정)실적(공정공시) — **별도** | `99620` |
| 연결재무제표기준 영업(잠정)실적 — **연결** | `99626` |

> 다른 공시유형은 docno가 다르다. 잠정실적 외로 확장하려면 §5의 Selenium 폴백을 쓰거나 폼→docno 표를 만든다.

## 3. 설계 결정 — requests 우선 + Selenium 폴백

이 라이브러리는 requests 기반(pyproject에 selenium 없음)이다. 그 정신을 유지한다.

| 방식 | 필요 | 속도 | 커버리지 |
|---|---|---|---|
| **requests-only** (권장) | shell 1회 GET + content_id 정규식 + docno(폼별) | 빠름(~0.3s) | docno를 아는 폼(잠정실적 등) |
| **Selenium 폴백** (선택) | 헤드리스 Chrome, `docLocPath` 읽기 | 느림(~5s) | **임의 폼**(docno 몰라도 됨) |

→ 함수 시그니처: `disclosure_content_url(acptno, *, docno=None, ...)`.
`docno`가 주어지면 requests-only, 없고 `use_selenium=True`면 폴백.

## 4. 붙여넣을 코드 — requests-only

### 4-1. `krx_kind_data_api/transport.py` 에 추가

기존 `disclosure_viewer_url` 바로 아래에 넣는다. `request()`를 재사용한다.

```python
import re

# 잠정실적 서식코드(docno). 다른 공시유형은 값이 다르다(§5 Selenium 폴백 참고).
DOCNO_JAMJEONG = {"separate": "99620", "consolidated": "99626"}
_CONTENT_ID_RE = re.compile(r"option\s+value=['\"](\d{14})\|")


def disclosure_content_id(acptno: str, *, session=None, timeout: int = 30) -> str:
    """shell HTML에서 본문 content_id(14자리) 추출. 접수번호와 다를 수 있다."""
    html = request(
        f"common/disclsviewer.do",
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
    docno: str | None = None,
    basis: str | None = None,     # "separate" | "consolidated" — docno 없을 때 잠정실적용
    session=None,
    timeout: int = 30,
) -> str:
    """접수번호 → 공시 본문(iframe) 실제 URL.

    docno 결정 우선순위: 명시 docno > basis(잠정실적 별도/연결) 매핑.
    둘 다 없으면 ValueError(→ 임의 폼은 disclosure_content_url_selenium 사용).
    """
    if docno is None:
        if basis in DOCNO_JAMJEONG:
            docno = DOCNO_JAMJEONG[basis]
        else:
            raise ValueError(
                "docno 또는 basis('separate'/'consolidated')가 필요합니다. "
                "임의 공시유형은 Selenium 폴백을 쓰세요."
            )
    cid = disclosure_content_id(acptno, session=session, timeout=timeout)
    y, m, d = acptno[0:4], acptno[4:6], acptno[6:8]
    return f"{BASE}/external/{y}/{m}/{d}/{acptno[8:14]}/{cid}/{docno}.htm"


def disclosure_content_html(acptno: str, *, encoding: str = "utf-8", **kw) -> str:
    """본문 URL을 열어 디코딩된 HTML 반환. (kw는 disclosure_content_url로 전달)"""
    url = disclosure_content_url(acptno, **kw)
    return request(url, {}, http="get", encoding=encoding, session=kw.get("session"))
```

> `request()`는 `path`가 절대 URL이면 그대로 GET 한다(`_url()`가 처리) — 본문 URL 그대로 넘기면 됨.
> 본문 `.htm`은 `<meta charset=UTF-8>`이라 `encoding="utf-8"`. shell은 EUC-KR.

### 4-2. `krx_kind_data_api/__init__.py` 에 export 추가

```python
from .transport import (
    disclosure_viewer_url,
    disclosure_content_url,     # 추가
    disclosure_content_id,      # 추가
    disclosure_content_html,    # 추가
    MARKETS, BASE,
)
# __all__ 에도 세 이름 추가
```

### 4-3. 사용

```python
from krx_kind_data_api import disclosure_content_url, disclosure_content_html

# 잠정실적: basis만 주면 docno 자동
disclosure_content_url("20260629000856", basis="separate")
# → https://kind.krx.co.kr/external/2026/06/29/000856/20260629001475/99620.htm

# 임의 폼: docno 직접 지정
disclosure_content_url("20260616000198", docno="99626")

html = disclosure_content_html("20260629000856", basis="separate")   # 본문 HTML
```

## 5. Selenium 폴백 (선택) — 임의 폼·docno 미상

docno를 모르거나 shell 구조가 바뀌어 requests가 실패할 때. 완성 URL을 JS가 직접 준다.
selenium 4는 Selenium Manager가 chromedriver를 자동 관리(별도 설치 불필요), Chrome만 있으면 됨.

### 5-1. `pyproject.toml` 선택 의존성

```toml
[project.optional-dependencies]
selenium = ["selenium>=4"]
```

### 5-2. `krx_kind_data_api/selenium_viewer.py` (신규)

```python
"""Selenium 폴백: 임의 공시의 본문 URL을 JS 실행 후 docLocPath에서 직접 읽는다."""
from __future__ import annotations
import time
from .transport import disclosure_viewer_url
from .exceptions import KINDFetchError


def disclosure_content_url_selenium(acptno: str, *, headless: bool = True,
                                    wait: float = 12.0) -> str:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opt = Options()
    if headless:
        opt.add_argument("--headless=new")
    for a in ("--no-sandbox", "--disable-gpu", "--window-size=1200,900"):
        opt.add_argument(a)
    d = webdriver.Chrome(options=opt)
    try:
        d.get(disclosure_viewer_url(acptno))
        deadline = time.time() + wait
        while time.time() < deadline:
            time.sleep(0.5)
            loc = d.execute_script(
                "var e=document.getElementById('docLocPath');return e?e.value:'';")
            if loc:
                return loc     # 완성 URL(docno 포함) 그대로 반환
        raise KINDFetchError(f"docLocPath 미확보(acptno={acptno})")
    finally:
        d.quit()
```

> 대량 수집 시 브라우저를 재사용하도록 클래스로 감싸는 게 좋다(매 호출 `webdriver.Chrome()`은 느림).

## 6. 엣지케이스 & 함정

- **슬롯4 = 접수번호[8:14](seq)**, 종목코드 아님. (예시 URL의 `000490`이 우연히 종목코드처럼 보였을 뿐.)
- **content_id ≠ 접수번호.** 반드시 shell option에서 추출. 접수번호를 그대로 넣으면 404.
- **다중 option**: 관련공시·첨부가 있으면 `<option value='...|'>`이 여러 개일 수 있다. 첫 번째 = 주 문서.
  자회사 대신공시(제목 `(자회사의 주요경영사항)`)도 주 문서는 첫 option. 필요하면 option **텍스트**로 필터.
- **docno는 공시유형별**: 잠정실적 별도 99620 / 연결 99626. 다른 공시로 확장하면 그 폼의 docno 확인 필요(Selenium 폴백이 안전).
- **인코딩**: shell=EUC-KR, 본문 `.htm`=UTF-8.
- **월별·값없음**: 월별 잠정공시(예: 지역난방공사)는 본문 표의 재무값이 `-`. URL·구조는 정상.
- **본문 구조**(참고): iXBRL 아님. 평문 xforms 테이블 2개 — `XFormD1_Form0_Table0`(실적기간),
  `XFormD1_Form0_RepeatTable0/1`(실적내용). datapoint↔셀 매핑은
  `taxonomy/mapping/`(build_mapping.py, out/*.csv, README) 참고.

## 7. (선택) 엔드포인트·MCP로 노출

본문 URL은 DataFrame이 아니라 `fetch()`/`ENDPOINTS` 패턴에 안 맞는다(그건 표→DataFrame 전용).
두 가지 선택:

- **A. 그냥 함수로** (권장) — `disclosure_content_url`을 public 함수로 노출(§4-2). 단순·명확.
- **B. 1행 DataFrame 엔드포인트로** — MCP 툴로도 쓰고 싶으면, 접수번호→`{acptno, content_url, docno}`
  1행 df를 돌려주는 얇은 래퍼를 만들고 `endpoints.ENDPOINTS`가 아닌 별도 함수로 두거나,
  커스텀 파서 대신 전용 함수로 처리. (표준 request/parser 흐름을 타지 않으므로 endpoints dict엔 부적합.)

## 8. 테스트 (tests/test_endpoints_live.py 스타일)

```python
def test_content_url_jamjeong_separate():
    from krx_kind_data_api import disclosure_content_url
    url = disclosure_content_url("20260629000856", basis="separate")
    assert url.endswith("/99620.htm")
    assert "/external/2026/06/29/000856/" in url   # 슬롯4=접수번호 seq

def test_content_html_fetch():
    import requests
    from krx_kind_data_api import disclosure_content_url
    url = disclosure_content_url("20260629000856", basis="separate")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    assert r.status_code == 200 and "실적" in r.content.decode("utf-8", "replace")
```

> 라이브 테스트라 접수번호가 KIND에서 만료되면 최신 잠정실적 acptno로 교체.

---

## 부록: 참고 소스

- 이 메커니즘의 원 탐구·검증: `C:\Users\Peter\Desktop\taxonomy\mapping\` (README.md, build_mapping.py, samples/, out/).
- 옛 Selenium 방식(검색화면 조작): `selenium/KIND_Selenium_프로젝트_정리.md`.
- 기존 엔드포인트 추가 절차: `docs/새_엔드포인트_추가하기.md`.