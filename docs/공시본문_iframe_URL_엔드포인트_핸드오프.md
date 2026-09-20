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
  3. **`docno`(서식코드)** ← shell엔 없다. 두 가지로 얻는다:
     - 폼 종류가 고정이면 표로 결정(잠정실적 별도=`99620`, 연결=`99626`).
     - **모르면 `searchContents` 폼 전송을 requests로 재현**해 서버에게 물어본다(§5). 이게 범용 해법.
- **권장 구현**: `disclosure_content_url(acptno)` — docno/basis를 주면 조립, 안 주면 자동 해석.
  **Selenium은 더 이상 필요 없다**(§5).

> ⚠️ **2026-09 정정**: 이 문서는 원래 `searchContents`가 "봇을 차단해 정적 requests 불가"라고
> 적었고 그래서 Selenium 폴백을 권했다. **오판이었다.** 차단되는 건 없고, `searchContents`는
> XHR이 아니라 **iframe 타깃 폼 전송**이라 그대로 POST하면 된다(§5). 매매거래정지처럼 docno가
> 시장·조치종류마다 갈리는 폼을 매핑표 없이 수집하려다 확인했다.

---

## 1. 배경 — 왜 shell만으론 안 되나

`kind_url = disclosure_viewer_url(acptno)` = `disclsviewer.do?method=search&acptno=...` 은
`<iframe id="docViewFrm" src="">` 가 **빈 채로** 오고, 로드 후 JS가 `searchContents` AJAX를 호출해
`docLocPath`(진짜 본문 URL)를 채운다. 그 AJAX는 `docNo`가 틀리면 `blank.html`을 돌려준다.
~~봇을 리다이렉트한다(정적 requests 불가).~~ **← 틀렸다.** `docNo`에 접수번호를 넣어서 난 blank였다.
**content_id를 넣으면 requests로 정상 응답한다**(§5).

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

> 다른 공시유형은 docno가 다르다. 그리고 **폼 종류만으로 결정되지 않는 경우가 많다** — 매매거래정지는
> 시장 × 조치종류로 갈린다(코스닥 정지 `70797` / 해제 `70799` / 기간변경 `70798`,
> 코넥스 `32010`·`32012`·`32011`, 유가 `68060`·`68054`·`99808`). 제목 정규식으로 분기하는
> 매핑표는 새 서식이 생길 때마다 조용히 깨지므로, **docno 미상이면 §5를 쓴다.**

## 3. 설계 결정 — requests 우선 + Selenium 폴백

이 라이브러리는 requests 기반(pyproject에 selenium 없음)이다. 그 정신을 유지한다.

| 방식 | 필요 | 속도 | 커버리지 |
|---|---|---|---|
| **docno 지정** | shell 1회 GET + content_id 정규식 + docno(폼별) | 가장 빠름(요청 1회) | docno를 아는 폼(잠정실적 등) |
| **searchContents 해석** (권장·범용) | shell GET + `searchContents` POST | 빠름(요청 2회) | **임의 폼**(docno 몰라도 됨) |
| ~~Selenium 폴백~~ | 헤드리스 Chrome, `docLocPath` 읽기 | 느림(~5s) | 위 두 가지로 충분해 **불필요** |

→ 함수 시그니처: `disclosure_content_url(acptno, *, docno=None, basis=None, ...)`.
docno/basis를 주면 조립하고, **없으면 `resolve_content_url()`로 자동 해석**한다.
Selenium 모듈(`selenium_viewer.py`)은 하위호환으로 남겨두지만 쓸 일이 없다.

## 4. 붙여넣을 코드 — requests-only

### 4-1. `krx_kind_data_api/transport.py` 에 추가

기존 `disclosure_viewer_url` 바로 아래에 넣는다. `request()`를 재사용한다.

```python
import re

# 잠정실적 서식코드(docno). 다른 공시유형은 값이 다르다(§5 Selenium 폴백 참고).
DOCNO_JAMJEONG = {"separate": "99620", "consolidated": "99626"}
_CONTENT_ID_RE = re.compile(r"option\s+value=['\"](\d{14})\|([YN])")


def disclosure_content_ids(acptno: str, *, session=None, timeout: int = 30) -> list:
    """content_id 후보를 우선순위 순으로. `|Y`(현재 유효 문서)가 먼저.

    정정공시는 option 이 2개(`|N` 원공시, `|Y` 정정본)라 첫 번째를 쓰면 404 가 난다.
    정정의 정정(3개 이상)은 shell 만으로 확정할 수 없어 호출 측에서 순차 시도한다.
    """
    html = request(
        "common/disclsviewer.do",
        {"method": "search", "acptno": acptno, "docno": "",
         "viewerhost": "", "viewerport": ""},
        http="get", encoding="euc-kr", session=session, timeout=timeout,
    )
    opts = _CONTENT_ID_RE.findall(html)   # [(content_id, 'Y'|'N'), ...]
    if not opts:
        raise KINDFetchError(
            f"content_id를 찾지 못함(acptno={acptno}). shell 구조 변경 또는 문서 없음."
        )
    return ([cid for cid, flag in opts if flag == "Y"]
            + [cid for cid, flag in reversed(opts) if flag != "Y"])


def disclosure_content_id(acptno: str, *, session=None, timeout: int = 30) -> str:
    """shell HTML에서 본문 content_id(14자리) 추출. 접수번호와 다를 수 있다."""
    return disclosure_content_ids(acptno, session=session, timeout=timeout)[0]


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

## 5. searchContents 해석 (권장) — 임의 폼·docno 미상

shell의 `docpathfrm` 폼을 그대로 POST하면 **docno가 박힌 완성 URL**이 돌아온다.

```html
<form name="docpathfrm" id="docpathfrm" target="docpathframe" action="/common/disclsviewer.do">
  <input type="hidden" name="method" id="method" value="searchContents" />
  <input type="hidden" name="docNo"  id="docNo"  value="" />
</form>
```

`target="docpathframe"` — **XHR이 아니라 iframe 타깃 폼 전송**이다. 그래서 requests로 그대로 된다.

```python
POST https://kind.krx.co.kr/common/disclsviewer.do
data = {"method": "searchContents", "docNo": <content_id>}
# → 응답 본문에 https://kind.krx.co.kr/external/.../70797.htm
```

⚠️ **`docNo`에 넣는 값은 content_id다.** 접수번호를 넣으면 `blank.html`이 온다.
(원 문서가 "봇 차단"이라고 본 건 이것 때문이었다.) 정정공시는 content_id 후보가
여럿이라 `|Y` 우선으로 순차 시도한다.

구현: `transport.resolve_content_url(acptno)`. `disclosure_content_url(acptno)`에
docno/basis를 안 주면 내부적으로 이걸 부른다.

```python
from krx_kind_data_api import resolve_content_url, disclosure_content_url

resolve_content_url("20260918000659")          # 코스닥 매매거래정지
# → .../external/2026/09/18/000659/20260918001407/70797.htm
disclosure_content_url("20260917000531")       # 유가 99808 — docno 몰라도 됨
disclosure_content_url("20260629000856", basis="separate")   # docno 아는 폼(요청 1회 적음)
```

### 호출 속도

KIND는 과한 호출에 민감하다. 대량 수집은 **분당 50요청**(공시 1건당 3요청 = 분당 약
16건) 수준으로 제한하는 것을 권한다. 참고 구현:
`case-projects-private/afterhrs_actions/collect_trading_halt_bodies.py`
(전역 토큰버킷 + 이어받기 + 실패 로그).

### (구) Selenium 폴백

`selenium_viewer.disclosure_content_url_selenium(acptno)`는 남아 있지만 §5로 대체됐다.
건당 ~5초라 대량 수집에는 쓰지 말 것.

## 6. 엣지케이스 & 함정

- **슬롯4 = 접수번호[8:14](seq)**, 종목코드 아님. (예시 URL의 `000490`이 우연히 종목코드처럼 보였을 뿐.)
- **content_id ≠ 접수번호.** 반드시 shell option에서 추출. 접수번호를 그대로 넣으면 404.
- **다중 option**: `<option value='{14자리}|{Y|N}'>`이 여러 개일 수 있다.
  **Y/N 플래그가 현재 유효한 문서를 가리킨다 — 첫 번째가 아니다.**
  - 원공시: option 1개.
  - **정정공시: 2개(`|N` 원공시, `|Y` 정정본).** 첫 번째(=원공시)의 content_id를 정정 접수번호와
    조합하면 **404**. (배당공시 자회사명 수집에서 1,309건 중 41건이 이 이유로 실패했다.)
  - 정정의 정정: 3개 이상. shell만으로는 확정할 수 없으므로(같은 날 정정이 2건이면 날짜로도
    못 가른다) `disclosure_content_ids()`가 주는 후보를 **순차 시도**해 200이 나오는 것을 쓴다.
  - 자회사 대신공시(제목 `(자회사의 주요경영사항)`)는 option 개수와 무관.
- **docno는 공시유형별**: 잠정실적 별도 99620 / 연결 99626,
  현금ㆍ현물 배당 결정 61500(유가)/71500(코스닥), 배당 주주명부폐쇄(기준일) 결정 91444(유가).
  docno가 고정인 공시유형은 **Selenium 폴백 없이** `disclosure_content_url(acptno, docno=...)`로 끝난다.
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