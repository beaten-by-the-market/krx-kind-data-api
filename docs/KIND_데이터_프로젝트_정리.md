# KIND(kind.krx.co.kr) 데이터를 사용하는 프로젝트 정리 — requests POST 방식

KRX 상장공시시스템(`kind.krx.co.kr`)에서 **`requests`로 직접** 데이터를 불러오는 코드가 포함된 프로젝트입니다.
Selenium 방식은 별도 정리 → [../selenium/KIND_Selenium_프로젝트_정리.md](../selenium/KIND_Selenium_프로젝트_정리.md)

스캔 결과: **6개 프로젝트 폴더 · 11개 파일** (활성 9 / 주석처리·비활성 2)

---

## 호출 패턴

KIND 화면의 내부 `.do` 엔드포인트에 폼 파라미터를 보내 HTML 테이블을 받아오는 구조입니다.

### 1) POST → `pd.read_html` (테이블 화면)

```python
url = 'https://kind.krx.co.kr/corpgeneral/stockissuelist.do'
params = { ... }                       # 화면별 검색 조건
req = requests.post(url, params=params)
df = pd.read_html(req.content)[0]      # 또는 BeautifulSoup 파싱
```

### 2) corpList 다운로드 URL → `pd.read_html` (종목 마스터)

```python
DOWNLOAD_URL = 'kind.krx.co.kr/corpgeneral/corpList.do'
params = {'method': 'download', 'marketType': 'stockMkt', 'searchType': 13}
request_url = urllib.parse.urlunsplit(['http', DOWNLOAD_URL, '', urlencode(params), ''])
df_listed = pd.read_html(request_url, header=0)[0]   # 종목코드↔회사명 마스터
```

### 3) POST → `BeautifulSoup` (당일공시 목록)

```python
url = 'https://kind.krx.co.kr/disclosure/todaydisclosure.do'
response = requests.post(url, params=params)
soup = BeautifulSoup(response.text, 'html.parser')
```

---

## 프로젝트별 정리

### 1. [dart_disclosure/](../../dart_disclosure/)
DART 공시 + KRX/KIND 결합 노트북. KIND 호출이 가장 많은 폴더.

- [자사주_소각KIND.ipynb](../../dart_disclosure/자사주_소각KIND.ipynb) — `corpgeneral/stockissuelist.do`(증자현황), `corpgeneral/listedissuestatusdetail.do`(상장종목현황 상세). `requests.post` → `pd.read_html`. 자사주 소각에 상장주식수 결합.
- [listing_special.ipynb](../../dart_disclosure/listing_special.ipynb) — KIND 엔드포인트 다수: `listinvstg/miscListTypeStatDetail.do`, `corpgeneral/growthReport.do`, `corpgeneral/corpList.do`, `common/corpList.do`, `investwarn/delcompany.do`(상장폐지), `listinvstg/listingcompany.do`(신규상장), `listinvstg/mergeListingCompany.do`(합병상장), `listinvstg/pubofrprogcom.do`(공모기업 진행현황), `corpgeneral/listedissuestatusdetail.do`. 신규/특수상장 종합. **KIND 호출 최다.**

### 2. [englishkind/](../../englishkind/)
영문공시 지원. 당일공시 목록을 긁어 영문 대상 공시를 추린다. (전용 폴더)

- [kospi_engdiscl.py](../../englishkind/kospi_engdiscl.py) — `disclosure/todaydisclosure.do`(코스피 당일공시) `requests.post` + `BeautifulSoup`, `common/disclsviewer.do`(공시 원문 뷰어 링크).
- [kosdaq_engdiscl.py](../../englishkind/kosdaq_engdiscl.py) — 동일 구조, 코스닥.

### 3. [forecast_real/](../../forecast_real/)
실적예측·스톡옵션. 상장유형 통계와 외국기업 정보를 KIND에서 수집.

- [forecast_real.py](../../forecast_real/forecast_real.py) — `listinvstg/miscListTypeStatDetail.do`(상장유형별 통계 상세), `corpgeneral/growthReport.do`(외국기업/성장성). `requests.post` → `pd.read_html`.
- [stock_option.py](../../forecast_real/stock_option.py) — 동일 엔드포인트. 스톡옵션 분석.

### 4. [seibro/](../../seibro/)
SEIBRO 분석의 종목코드 마스터를 KIND `corpList`에서 받아온다.

- [seibro_anlysis.py](../../seibro/seibro_anlysis.py) — `corpgeneral/corpList.do?method=download`(상장법인목록 다운로드, 종목코드 마스터). `pd.read_html(request_url)` — 활성.
- [seibro_data_get_azure.py](../../seibro/seibro_data_get_azure.py) — 동일(`corpList.do` 종목 마스터).

### 5. [test/](../../test/)
테스트용 사본.

- [kosdaq_engdiscl.py](../../test/kosdaq_engdiscl.py) — `englishkind/kosdaq_engdiscl.py`의 복사본. `disclosure/todaydisclosure.do`.

### 6. [xbrl_validation/](../../xbrl_validation/) — ⚠️ 비활성(주석처리)
과거 `corpList.do`로 종목목록을 받던 코드가 **전부 주석 처리**되어 현재 미사용. (이력 참고용)

- [get_xbrl_full_opendartreader.py](../../xbrl_validation/get_xbrl_full_opendartreader.py) — `corpgeneral/corpList.do` 다운로드 코드 주석처리.
- [get_xbrl_full_opendartreader_for_real.py](../../xbrl_validation/get_xbrl_full_opendartreader_for_real.py) — 동일, 주석처리.

---

## 요약

| 폴더 | 파일 수 | 주된 KIND 용도 | 상태 |
|------|--------|----------------|------|
| dart_disclosure | 2 | 증자/상장현황/신규·특수상장 종합 (호출 최다) | 활성 |
| englishkind | 2 | 당일공시 → 영문공시 대상 추출 | 활성 |
| forecast_real | 2 | 상장유형 통계·외국기업 | 활성 |
| seibro | 2 | corpList 종목코드 마스터 | 활성 |
| test | 1 | englishkind 사본 | 활성 |
| xbrl_validation | 2 | corpList 종목목록 | 비활성(주석) |

**공통 패턴**: KIND는 대부분 ① **종목코드 마스터**(`corpList.do`) 또는 ② **공시/상장 상태 테이블**(`todaydisclosure.do`, `listedissuestatusdetail.do`, `stockissuelist.do` 등)을 받아 DART/SEIBRO 데이터와 결합하는 보조 소스로 쓰입니다.
