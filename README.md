# krx-kind-data-api

KRX 상장공시시스템(**KIND**, `kind.krx.co.kr`) 호출 클라이언트 + 인벤토리.
[krx-data-api](../krx-data-api/)(`data.krx.co.kr`)의 KIND 버전입니다. KIND는
로그인/OTP가 없고, 화면별 `.do` 엔드포인트에 폼 파라미터를 POST/GET 해서 HTML을
파싱하는 구조라, 그걸 `fetch("이름")` 한 줄로 추상화했습니다.

## 설치 & 빠른 시작

```bash
pip install -e .          # 또는: pip install git+<repo-url>
```

```python
from krx_kind_data_api import fetch, list_endpoints

fetch("corp_list", marketType="kosdaqMkt")              # 코스닥 종목코드 마스터
fetch("merge_listing", toDate="2026-06-08")             # 합병·재상장 기업
fetch("spac_merge_listing", spacType="존속", toDate="2026-06-08")  # SPAC 존속합병상장
fetch("spac_merge_listing", spacType="소멸", toDate="2026-06-08")  # SPAC 소멸합병상장
fetch("listing_company", toDate="2026-06-08")           # 신규상장 기업
fetch("pubofr_prog_com", toDate="2026-06-08")           # 공모기업 진행현황
fetch("today_disclosure", marketType=1, selDate="2026-06-08")  # 당일공시
list_endpoints()                                        # 등록된 화면 목록
```

`fetch()`는 `defaults`에 호출 파라미터를 머지하고, 화면에 맞는 파서로 HTML을
DataFrame으로 만들어 돌려줍니다. `**params`로 무엇이든 덮어쓸 수 있습니다.

### 등록된 엔드포인트 (v0.1)

| 이름 | 화면 | 비고 |
|------|------|------|
| `corp_list` | 상장법인목록(종목코드↔회사명 마스터) | `marketType=stockMkt/kosdaqMkt/konexMkt` |
| `stock_issue_list` | 증자(주식발행) 현황 | `marketType`, `toDate` 필수 |
| `misc_list_type_stat` | 상장유형별 통계 상세(이전/특례상장) | `listMonth`(연도), `listClssCd` 필수 |
| `growth_report` | 성장성특례 상장(성장성보고서) | euc-kr, `endDate` 필수 |
| `listing_company` | 신규상장 기업(상장유형 01~05) | 회사코드 추출, `toDate` 필수 |
| `merge_listing` | 합병·재상장 기업(06·07, 스팩합병) | 회사코드 추출, `toDate` 필수 |
| `spac_merge_listing` | **SPAC 합병상장(존속/소멸)** | `spacType`(존속/소멸/전체)로 스위치, SPAC 전용 컬럼(액면가·공모가·공모금액 등), `toDate` 필수 |
| `pubofr_prog_com` | 공모기업 진행현황 | 업무처리번호 추출, `toDate` 필수, `searchCorpName`/`isurCd` 필터 가능 |
| `today_disclosure` | 당일공시 | `marketType`, `selDate` 필수, 공시 원문 URL 포함 |

### MCP 서버 (Claude 등 AI 에이전트에서 호출)

카탈로그의 8개 화면을 **MCP 툴로 그대로 노출**합니다. 각 엔드포인트의 `"params"`
메타데이터가 자동으로 툴 인자 스키마(JSON-Schema)가 되므로, 엔드포인트를 추가하면
툴도 자동으로 늘어납니다.

```bash
pip install -e ".[mcp]"                 # mcp SDK 포함 설치
python -m krx_kind_data_api.mcp_server  # stdio 트랜스포트로 구동 (= krx-kind-mcp)
```

Claude Desktop / Claude Code 등록(`claude_desktop_config.json` 또는 mcp 설정):

```json
{
  "mcpServers": {
    "krx-kind": {
      "command": "python",
      "args": ["-m", "krx_kind_data_api.mcp_server"]
    }
  }
}
```

- 툴 이름은 `kind_<엔드포인트>` (예: `kind_pubofr_prog_com`).
- 인자는 `endpoints.py`의 `"params"`에서 생성 — `desc`/`enum`/`example`/`required` 반영.
- 결과는 `{endpoint, rows, columns, truncated, records}` JSON(기본 최대 500행).
- 구현/설계: [krx_kind_data_api/mcp_server.py](krx_kind_data_api/mcp_server.py).
  순수 로직(스키마·디스패치)과 서버 구동이 분리돼 있어 mcp 미설치로도 테스트됩니다.

### 새 화면을 API로 추가

`krx_kind_data_api/endpoints.py`의 `ENDPOINTS`에 dict 한 줄을 추가하면 끝입니다.
절차와 함정은 **[docs/새_엔드포인트_추가하기.md](docs/새_엔드포인트_추가하기.md)** 참고.
(예: *"`mergeListingCompany.do` 화면도 api로 만들어줘"* → 이 문서대로 추가)

### 패키지 구조

```
krx_kind_data_api/
├── transport.py   .do 엔드포인트 POST/GET → HTML 문자열 (BASE, MARKETS, viewer URL)
├── endpoints.py   화면 카탈로그 (여기에 한 줄 추가하면 새 API)
├── parsers.py     HTML→DataFrame 파서 레지스트리 (read_html / kind_list_with_code / today_disclosure / corp_list)
├── client.py      fetch() — defaults 머지 + required 검증 + 파서 적용
├── mcp_server.py  MCP 서버 — params 메타 → 툴 스키마 자동 생성 (optional: pip install .[mcp])
└── exceptions.py
tests/test_endpoints_live.py   라이브 테스트 (KIND_SKIP_LIVE=1로 스킵)
tests/test_mcp_server.py       MCP 순수 로직 테스트 (mcp 미설치에서도 동작)
```

---

## 인벤토리 — 어디서 KIND를 호출했나

원래 이 폴더는 KIND 호출 코드가 어느 프로젝트에 흩어져 있는지 정리한 인벤토리에서
출발했습니다. 스캔 결과: **8개 프로젝트 폴더 · 15개 파일** (활성 12 / 비활성·주석처리 3)

### 수집 방식이 두 가지입니다

KIND는 `data.krx.co.kr`(정보데이터시스템)과 달리 OTP 2단계 다운로드가 아니라, 화면별 `.do` 엔드포인트에 폼 파라미터를 던지는 구조입니다. 접근 방식은 둘로 나뉩니다.

| 방식 | 폴더 | 특징 |
|------|------|------|
| **requests POST/GET** | [docs/](docs/) | 화면의 내부 `.do` 엔드포인트에 `requests.post(url, data/params)` → `pd.read_html`/`BeautifulSoup`. 가볍고 빠름. **권장 방식** |
| **Selenium** | [selenium/](selenium/) | `webdriver.Chrome`로 상세검색 화면을 직접 조작해 `driver.page_source`를 파싱. **옛날 방식** — 상세검색(`details.do`) 화면이 폼 POST로 잘 안 떨어지던 시절의 흔적. 추후 requests POST로 대체 가능 |

- requests POST 방식 정리 → **[docs/KIND_데이터_프로젝트_정리.md](docs/KIND_데이터_프로젝트_정리.md)**
- Selenium 방식 정리 → **[selenium/KIND_Selenium_프로젝트_정리.md](selenium/KIND_Selenium_프로젝트_정리.md)**
- 상장종목현황(주권 보통주·외국주권 현재 목록) → **[docs/상장종목현황_listed_issue_status.md](docs/상장종목현황_listed_issue_status.md)**

## 자주 쓰이는 KIND 엔드포인트

| 엔드포인트 (`kind.krx.co.kr/...`) | 화면 | 주 용도 |
|-----|------|---------|
| `corpgeneral/corpList.do?method=download` | 상장법인목록 다운로드 | 종목코드 마스터(종목코드↔회사명) — 가장 흔함 |
| `corpgeneral/listedIssueStatus.do` | 상장종목현황 집계 | 시장 전체 증권구분별 회사수/종목수 요약 (`listed_issue_summary`) |
| `corpgeneral/listedissuestatusdetail.do` | 상장종목현황 상세(엑셀) | 시장·증권구분별 종목 목록 (`listed_issue_status`) |
| `corpgeneral/stockissuelist.do` | 증자(주식발행) 현황 | 자사주/증자 분석 |
| `corpgeneral/growthReport.do` | 외국기업·성장성보고 | 외국기업/특수상장 |
| `disclosure/todaydisclosure.do` | 당일공시 | 영문공시/번역 대상 수집 |
| `disclosure/details.do?method=searchDetailsMain` | 공시 상세검색 | 공정공시·손익변경 (requests POST, `disclosure_details`) |
| `common/disclsviewer.do` | 공시 뷰어(shell) | 개별 공시 뷰어 링크(`disclosure_viewer_url`) |
| `external/.../{docno}.htm` | 공시 본문(iframe) | 접수번호→본문 HTML 실제 URL(`disclosure_content_url` / `disclosure_content_html`) |
| `listinvstg/miscListTypeStatDetail.do` | 상장유형별 통계 상세 | 실적예측/스톡옵션 |
| `listinvstg/pubofrprogcom.do` | 공모기업 진행현황 | IPO 수요예측·청약·상장예정일 수집 |
| `investwarn/adminissue.do` / `undisclosure.do` / `delcompany.do` | 관리종목 / 불성실공시 / 상장폐지 | 투자유의 |
