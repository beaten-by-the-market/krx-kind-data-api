# KIND(kind.krx.co.kr) 데이터를 사용하는 프로젝트 정리 — Selenium 방식

KRX 상장공시시스템(`kind.krx.co.kr`)을 **Selenium(`webdriver.Chrome`)으로 화면을 직접 조작**해 데이터를 긁는 코드입니다.
requests POST 방식은 별도 정리 → [../docs/KIND_데이터_프로젝트_정리.md](../docs/KIND_데이터_프로젝트_정리.md)

스캔 결과: **2개 프로젝트 폴더 · 4개 파일** (활성 3 / 주석처리·비활성 1)

> ⚠️ **옛날 방식.** 대부분 KIND 공시 **상세검색**(`disclosure/details.do?method=searchDetailsMain`) 화면을 다룹니다. 이 화면은 검색 조건을 JS 폼으로 제출해 결과 테이블을 다시 그리는 구조라, 과거에는 폼 POST 재현이 까다로워 브라우저를 띄워 조작했습니다. **추후 해당 `.do` 엔드포인트의 POST 파라미터를 분석하면 requests POST 방식으로 대체 가능**합니다.

---

## 호출 패턴

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

driver = webdriver.Chrome()
driver.get('https://kind.krx.co.kr/disclosure/details.do?method=searchDetailsMain')
# ... 검색 조건 입력 / 버튼 클릭 ...
soup = BeautifulSoup(driver.page_source, 'html.parser')   # 또는 pd.read_html(table_html)
```

---

## 프로젝트별 정리

### 1. [fairdisclosure/](../../fairdisclosure/)
공정공시 관련. KIND **상세검색 화면**(`disclosure/details.do?method=searchDetailsMain`)을 Selenium으로 조작해 테이블 수집.

- [fairdisc_kind.py](../../fairdisclosure/fairdisc_kind.py) — `webdriver.Chrome`로 상세검색 → 공정공시 목록을 `pd.read_html(table_html)`로 추출.
- [earningschangedisc.py](../../fairdisclosure/earningschangedisc.py) — 동일한 상세검색 화면. **손익구조 30%(대규모) 변동 공시** 수집.

### 2. [ad_hoc_issues/](../../ad_hoc_issues/)
DART 수시공시 처리 보조.

- [translation_disclosure_get.py](../../ad_hoc_issues/translation_disclosure_get.py) — **활성.** `webdriver.Chrome`로 `disclosure/todaydisclosure.do?...&marketType=1`(당일공시) 접속, `driver.page_source`를 BeautifulSoup 파싱. `common/disclsviewer.do`로 개별 공시 원문 링크 구성. 공시 영문번역 지원.
- [eng_discl_support.v2.py](../../ad_hoc_issues/eng_discl_support.v2.py) — ⚠️ **비활성(주석처리).** 과거 Selenium으로 `investwarn/adminissue.do`(관리종목), `investwarn/undisclosure.do`(불성실공시법인)를 긁던 코드가 전부 주석 처리됨. requests 방식 등으로 대체된 흔적.

---

## 요약

| 폴더 | 파일 수 | KIND 화면 | 상태 |
|------|--------|-----------|------|
| fairdisclosure | 2 | `details.do`(공정공시·손익변경 상세검색) | 활성 |
| ad_hoc_issues | 2 | `todaydisclosure.do`(당일공시), `investwarn/*`(관리·불성실) | 활성 1 / 주석 1 |

**대체 방향**: `fairdisclosure`의 상세검색 수집은 `details.do`의 POST 파라미터를 분석하면 [requests POST 방식](../docs/KIND_데이터_프로젝트_정리.md)으로 옮길 수 있습니다. `translation_disclosure_get.py`의 `todaydisclosure.do`는 이미 `englishkind/`에서 requests POST로 동일 화면을 처리하고 있어, 그 코드를 참고해 Selenium 의존을 제거할 수 있습니다.
