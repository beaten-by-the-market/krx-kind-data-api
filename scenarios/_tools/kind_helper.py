# ── KIND·KRX 헬퍼 (모든 시나리오 노트북 공통) ─────────────────────────────
# KIND(kind.krx.co.kr, 공시)는 로그인 없이 됩니다.
# KRX 정보데이터시스템(data.krx.co.kr, 시세·지수)은 2026-09부터 로그인이 필요합니다.
#   Colab: 왼쪽 🔑(Secrets)에 KRX_ID, KRX_PW 를 넣고 "노트북 액세스"를 켜세요.
#   로컬: 환경변수 KRX_ID/KRX_PW 또는 .env (krx-data-api 가 작업 폴더와 자기 레포의 .env 를 읽음).
# 아이디·비밀번호 값은 출력하지 않습니다.
import io, os, re, sys, time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests

IN_COLAB = "google.colab" in sys.modules
if IN_COLAB:
    from google.colab import userdata
    for _k in ("KRX_ID", "KRX_PW"):
        try:
            _v = userdata.get(_k)
        except Exception:
            _v = None
        if _v:
            os.environ[_k] = _v
    if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
        print("⚠️ Colab Secrets 에 KRX_ID / KRX_PW 가 없습니다. 시세·지수 호출이 LOGOUT 오류로 실패합니다.")

import krx_kind_data_api as kind
from krx_data_api import fetch as krx_fetch

pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 60)

# ── KIND 호출 (분당 50요청 안쪽으로) ──────────────────────────────────────
_KIND_GAP = 1.2          # 초. KIND는 과한 호출에 민감하다(README: 분당 50요청 이하)
_kind_last = [0.0]
_KIND_SESSION = requests.Session()


def _kind_wait():
    gap = time.time() - _kind_last[0]
    if gap < _KIND_GAP:
        time.sleep(_KIND_GAP - gap)
    _kind_last[0] = time.time()


def kind_fetch(name, **params):
    """krx_kind_data_api.fetch + 호출 간격 조절."""
    _kind_wait()
    return kind.fetch(name, session=_KIND_SESSION, **params)


def disclosures(date_from, date_to, **params):
    """KIND 공시 상세검색(disclosure_details)을 월 단위로 끊어 모두 받는다.
    긴 기간을 한 번에 주면 KIND가 오류 없이 0건을 돌려주므로 월별로 나누고, 100건이 넘으면 페이지를 넘긴다.
    params 예: reportNm="무상증자결정", disclosureType="배당", lastReport=""(원본·정정 모두).
    결과의 `시간`은 공시 시각(Timestamp), `정정`/`이후정정`은 정정 표시."""
    parts = []
    for m in pd.period_range(pd.Timestamp(date_from), pd.Timestamp(date_to), freq="M"):
        s = max(m.start_time, pd.Timestamp(date_from)).strftime("%Y-%m-%d")
        e = min(m.end_time, pd.Timestamp(date_to)).strftime("%Y-%m-%d")
        page = 1
        while True:
            df = kind_fetch("disclosure_details", fromDate=s, toDate=e, pageIndex=str(page),
                            currentPageSize="100", **params)
            parts.append(df)
            if len(df) < 100:
                break
            page += 1
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if out.empty:
        return out
    out["시간"] = pd.to_datetime(out["시간"], errors="coerce")
    return (out.drop(columns=["번호"]).drop_duplicates("접수번호")
               .sort_values("시간").reset_index(drop=True))


def disclosure_tables(acptno):
    """접수번호 → 공시 본문의 표 목록(pd.read_html). 정정된 공시는 최종(정정) 본문이 온다.
    resolve_content_url 은 목차(_toc.htm)를 주는 경우가 있어 본문(.htm)으로 바꿔 읽는다. 요청 3회."""
    _kind_wait()
    url = kind.resolve_content_url(acptno, session=_KIND_SESSION).replace("_toc.htm", ".htm")
    _kind_wait()
    r = _KIND_SESSION.get(url, timeout=30)
    r.raise_for_status()
    html = r.content.decode("utf-8", "replace")
    try:
        return pd.read_html(io.StringIO(html))
    except ValueError:
        return []


# ── KRX 시세·지수 (krx-data-api, 로그인 필요) ────────────────────────────
INDEX_CODES = {"KOSPI": ("1", "001"), "KOSDAQ": ("2", "001")}


def _num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce")


def index_close(name, date_from, date_to):
    """KRX 지수 일별 종가(Series, index=날짜). name: KOSPI / KOSDAQ."""
    a, b = INDEX_CODES[name]
    df = krx_fetch("equity_index", indIdx=a, indIdx2=b,
                   strtDd=pd.Timestamp(date_from).strftime("%Y%m%d"),
                   endDd=pd.Timestamp(date_to).strftime("%Y%m%d"))
    s = pd.Series(_num(df["종가"]).values, index=pd.to_datetime(df["일자"]), name=name)
    return s.sort_index()


def stock_snapshot(day):
    """하루치 전 종목 시세(all_stock_price, JSON 영문 코드). 휴장일이면 직전 거래일 값이 온다.
    ISU_SRT_CD(단축코드)·ISU_CD(표준코드 KR7…)·ISU_ABBRV·MKT_NM·TDD_CLSPRC(원주가)·LIST_SHRS 등."""
    df = krx_fetch("all_stock_price", trdDd=pd.Timestamp(day).strftime("%Y%m%d"))
    for c in ("TDD_CLSPRC", "FLUC_RT", "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP", "LIST_SHRS"):
        if c in df:
            df[c] = _num(df[c])
    return df


def price_trend(isu_cd, date_from, date_to, adjusted=True):
    """개별종목 일별 시세(individual_price_trend, CSV 한글 컬럼). isu_cd 는 표준코드(KR7…).
    adjusted=True 면 수정주가(오늘 기준), False 면 원주가. index=날짜."""
    df = krx_fetch("individual_price_trend", isuCd=isu_cd,
                   strtDd=pd.Timestamp(date_from).strftime("%Y%m%d"),
                   endDd=pd.Timestamp(date_to).strftime("%Y%m%d"),
                   adjusted_price=adjusted)
    if df.empty:
        return df
    df.index = pd.to_datetime(df.pop("일자"))
    return df.sort_index()


def reaction_day(ts, days, cutoff="15:30"):
    """공시 시각 → 반응 첫 거래일(D0)의 위치(days 안의 정수 인덱스).
    장 마감(cutoff) 이후 공시는 다음 거래일, 휴장일 공시는 다음 거래일이 D0."""
    hh, mm = map(int, cutoff.split(":"))
    day = ts.normalize()
    if ts.hour * 60 + ts.minute >= hh * 60 + mm:
        day += pd.Timedelta(days=1)
    pos = days.searchsorted(day)
    return int(pos) if pos < len(days) else None


def pct(x, digits=1):
    return "-" if x is None or pd.isna(x) else f"{x * 100:+.{digits}f}%"


PRICE_NOTICE = ("※ 주가는 KRX 수정주가(individual_price_trend, 오늘 기준)입니다. 무상증자·분할의 권리락으로 생기는 "
                "기계적 하락은 소급 반영돼 수익률에 섞이지 않습니다. 배당은 반영하지 않습니다.")

# 한글 차트 폰트
import matplotlib.pyplot as plt
try:
    import koreanize_matplotlib  # noqa: F401  (Colab: 위 셀에서 설치)
except ImportError:
    if sys.platform.startswith("win"):
        plt.rcParams["font.family"] = "Malgun Gothic"
    elif sys.platform == "darwin":
        plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False

print("KIND·KRX 준비 완료", "(Colab)" if IN_COLAB else "(로컬)",
      "| KRX 로그인 정보:", "있음" if os.environ.get("KRX_ID") and os.environ.get("KRX_PW") else "없음")
