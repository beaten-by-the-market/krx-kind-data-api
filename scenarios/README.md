# 시나리오 노트북

KIND 공시(`krx_kind_data_api`)와 KRX 시세(`krx_data_api`)를 엮은 분석 예제입니다. 노트북마다 실행 결과가 저장돼 있어
GitHub에서 바로 읽을 수 있고, 배지를 누르면 Colab에서 다시 돌릴 수 있습니다.

| 번호 | 시나리오 | 질문 예시 | 쓰는 데이터 |
|---|---|---|---|
| 1-01 | [무상증자 이벤트 스터디](1_disclosure_events/01_bonus_issue_event_study.md) ([노트북](1_disclosure_events/01_bonus_issue_event_study.ipynb)) | "무상증자 발표하면 주가 오르나?", "비율 큰 무상증자일수록 더 오르나?" | KIND `disclosure_details`·공시 본문, KRX `individual_price_trend`(수정주가)·`equity_index`·`all_stock_price` |

## Colab에서 실행

1. 노트북 맨 위 **Colab에서 열기** 배지를 누릅니다.
2. 왼쪽 🔑(Secrets)에 `KRX_ID`, `KRX_PW`(data.krx.co.kr 계정)를 넣고 노트북 액세스를 켭니다.
   KRX 정보데이터시스템은 2026-09부터 로그인이 필요합니다. KIND는 로그인이 필요 없습니다.
3. 위에서부터 실행합니다. 첫 셀이 이 레포와 [krx-data-api](https://github.com/beaten-by-the-market/krx-data-api)를 GitHub에서 설치합니다.

## 폴더 구조

```
scenarios/
├── _src/<유형>/<NN_이름>.py   노트북 원본(`# %%` 셀 구분). 여기를 고친다
├── _tools/
│   ├── build.py               원본 → 실행된 .ipynb (배지·준비 셀 삽입)
│   ├── kind_helper.py         모든 노트북의 공통 준비 셀(KIND 호출 간격, 공시 월별 수집, KRX 시세·지수)
│   └── show.py                실행된 노트북의 출력 확인
└── <유형>/<NN_이름>.ipynb      실행 결과 포함 노트북 + 같은 이름의 .md 설명
```

## 다시 만들기 (로컬)

```bash
pip install -e .                               # 이 레포
pip install -e ../krx-data-api                 # 또는 git+https://github.com/beaten-by-the-market/krx-data-api.git
pip install nbformat nbclient ipykernel
python scenarios/_tools/build.py 1_disclosure_events/01   # 원본을 노트북으로 만들고 실행
python scenarios/_tools/show.py scenarios/1_disclosure_events/01_bonus_issue_event_study.ipynb
```

- `.ipynb`는 손으로 고치지 말고 `_src`의 원본을 고친 뒤 다시 빌드합니다.
- `kind_helper.py`를 바꾸면 모든 노트북을 다시 빌드합니다(`python scenarios/_tools/build.py`).
- 로컬 실행의 KRX 로그인은 환경변수 `KRX_ID`/`KRX_PW` 또는 `.env`에서 읽습니다. krx-data-api를 편집 가능
  설치(`pip install -e`)했다면 그 레포의 `.env`도 읽습니다.
- KIND는 과한 호출에 민감해서 헬퍼가 요청 사이에 1.2초씩 쉽니다(분당 50요청 안쪽).
