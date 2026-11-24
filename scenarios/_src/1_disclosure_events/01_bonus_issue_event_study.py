# %% [markdown]
# # 1-01 무상증자 이벤트 스터디 — 결정 공시 전후 주가 반응
#
# **질문 예시:** "무상증자 발표하면 주가 오르나?", "1주당 1주씩 주는 큰 무상증자일수록 더 오르나?", "올해랑 작년이랑 반응이 달라?"
#
# 예전 Streamlit 앱(`krxnewsscrap/bonus_issue.py`)은 DART 무상증자결정과 일별 시세를 DB에 쌓아 두고
# 이사회결의일 기준 당일·전후 1일 수익률을 발행비율·연도별로 봤습니다. 그 DB는 이제 없어서
# **KIND 공시 + KRX 시세**로 다시 만들었습니다.
#
# | 항목 | 어디서 |
# |---|---|
# | 무상증자결정 공시와 **공시 시각** | KIND 공시 상세검색 `disclosure_details`(공시제목 `무상증자결정`), 원본·정정 모두 받아 정정 표시로 구분 |
# | 발행비율(1주당 신주배정 주식수)·신주배정기준일 | 공시 **본문** 표 (`resolve_content_url` → 본문 HTML) |
# | 주가 | KRX `individual_price_trend` **수정주가** (krx-data-api, 로그인 필요) |
# | 시장 수익률 | KRX `equity_index` 코스피·코스닥 지수 → 시장 대비 **초과수익** |
# | 종목코드 ↔ 표준코드 | KRX `all_stock_price` 하루치(전 종목 한 번 호출) |

# %%
START, END = "2025-01-01", "2026-11-14"   # 공시 기간. D+5 시세가 있도록 끝은 기준일 1주 전
ASOF = "2026-11-24"                        # 시세 기준일
print(PRICE_NOTICE)

# %% [markdown]
# ## 1. 무상증자결정 공시 모으기
# - KIND 상세검색은 기간이 길면 오류 없이 0건을 주므로 **월 단위**로 끊어 받습니다(헬퍼 `disclosures`).
# - `lastReport=""`로 원본과 정정을 모두 받은 뒤, 제목 앞 `[정정]` 표시가 있는 **정정공시는 뺍니다.**
#   시장이 처음 반응하는 건 원본 공시이기 때문입니다. 바뀐 조건(비율·기준일)은 2절에서 최종 본문으로 반영합니다.
# - `무상증자결정(자회사의 주요경영사항)`처럼 **자회사·종속회사** 공시도 뺍니다(공시 회사 자신의 증자가 아님).
# - 같은 검색어로 `유무상증자결정`은 잡히지 않습니다(유상증자가 섞인 다른 사건이라 의도대로입니다).

# %%
raw = disclosures(START, END, reportNm="무상증자결정", lastReport="")
is_sub = raw["공시제목"].str.contains("주요경영사항")
print(f"받은 공시 {len(raw)}건 = 원본 {(~raw['정정']).sum()} + 정정 {raw['정정'].sum()}")
print(f"  그중 자회사·종속회사 공시 {is_sub.sum()}건, 코넥스 {(raw['시장'] == '코넥스').sum()}건")
ev = raw[~raw["정정"] & ~is_sub & raw["시장"].isin(["유가증권", "코스닥"])].reset_index(drop=True)
print(f"→ 분석 대상 원본 공시 {len(ev)}건 (나중에 정정된 원본 {ev['이후정정'].sum()}건 포함)")
ev[["시간", "시장", "회사명", "공시제목", "접수번호", "이후정정"]].tail(8)

# %% [markdown]
# ## 2. 공시 본문에서 발행비율·기준일 읽기
# KIND 목록에는 비율이 없어서 공시 본문 표를 읽습니다. 공시 1건당 요청 3회(뷰어 → 본문 주소 → 본문)라
# KIND 권장 속도(분당 50요청)에 맞추면 100건에 6분쯤 걸립니다.
# 원본 접수번호로 열어도 KIND는 **최종 정정본**을 보여 주므로, 비율·기준일은 정정이 반영된 값입니다.
#
# - **발행비율** = `5. 1주당 신주배정 주식수`(보통주). 1이면 1주당 1주(주식 수 2배).
# - **신주배정기준일**로 권리락일(기준일 직전 거래일)을 계산해 4절에서 따로 봅니다.

# %%
def _rows(tables):
    for t in tables or []:
        if t.shape[1] < 2:
            continue
        for vals in t.astype(str).values.tolist():
            yield vals[0].replace(" ", ""), vals[1].replace(" ", ""), vals[-1]

def body_field(tables, label, common_only=False):
    for c0, c1, v in _rows(tables):
        if label in c0 and (not common_only or "보통" in c1):
            return v
    return None

def to_num(v):
    m = re.search(r"-?[\d,]*\.?\d+", str(v or "").replace(",", ""))
    return float(m.group()) if m else np.nan

def to_date(v):
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", str(v or ""))
    return pd.Timestamp(int(m[1]), int(m[2]), int(m[3])) if m else pd.NaT

t0 = time.time()
info = []
for a in ev["접수번호"]:
    try:
        tb = disclosure_tables(a)
    except Exception as e:          # 본문을 못 읽으면 비율 없이 남긴다
        print("본문 실패", a, type(e).__name__)
        tb = []
    info.append({
        "접수번호": a,
        "발행비율": to_num(body_field(tb, "1주당신주배정주식수", common_only=True)),
        "신주수": to_num(body_field(tb, "신주의종류와수", common_only=True)),
        "증자전주식수": to_num(body_field(tb, "증자전발행주식총수", common_only=True)),
        "신주배정기준일": to_date(body_field(tb, "신주배정기준일")),
        "상장예정일": to_date(body_field(tb, "신주의상장예정일")),
    })
ev = ev.merge(pd.DataFrame(info), on="접수번호", how="left")
print(f"본문 {len(ev)}건 읽음 ({time.time() - t0:.0f}초). 발행비율을 못 읽은 공시 {ev['발행비율'].isna().sum()}건")
ev["발행비율"].describe().round(2)

# %% [markdown]
# ## 3. 시세 붙이고 반응일(D0) 정하기
# - **D0** = 공시 후 첫 거래일. 장 마감(15:30) 이후 공시는 다음 거래일이 D0입니다(시간외 거래는 무시).
# - 주가는 **수정주가**입니다. 원주가로 재면 권리락일에 주가가 1/(1+비율)로 떨어져(1주당 1주면 반토막)
#   공시 후 며칠 창에 권리락이 끼면 수익률이 엉망이 됩니다. 아래 표가 그 예입니다.
# - 일별 시세는 기간 조회가 종목별 화면(`individual_price_trend`)뿐이라 **사건마다 1번** 부릅니다.
#   전 종목 시세(`all_stock_price`)는 하루치라 사건 창을 다 덮으려면 거래일 수백 번을 불러야 해서 더 느립니다.

# %%
kospi = index_close("KOSPI", "2024-11-01", ASOF)
kosdaq = index_close("KOSDAQ", "2024-11-01", ASOF)
days = kospi.index
mkt_index = {"유가증권": kospi, "코스닥": kosdaq}

snap = stock_snapshot(ASOF)                     # 종목코드 → 표준코드(KR7…)
isin = snap.set_index("ISU_SRT_CD")["ISU_CD"]
ev["종목코드"] = ev["회사코드"].str.strip() + "0"
ev["표준코드"] = ev["종목코드"].map(isin)
ev["D0_pos"] = [reaction_day(t, days) for t in ev["시간"]]
ev["반응일"] = [days[int(p)] if pd.notna(p) else pd.NaT for p in ev["D0_pos"]]


def ex_pos_of(rd):
    """신주배정기준일 → 권리락일 위치. 기준일(휴장이면 직전 거래일)의 바로 전 거래일(T+2 결제).
    기준일이 아직 오지 않았으면 None."""
    if pd.isna(rd) or not (days[0] <= rd <= days[-1]):
        return None
    return int(days.searchsorted(rd, side="right")) - 2


ev["권리락_pos"] = [ex_pos_of(rd) for rd in ev["신주배정기준일"]]
ev["권리락일자"] = [days[int(p)] if pd.notna(p) else pd.NaT for p in ev["권리락_pos"]]
miss = ev[ev["표준코드"].isna()]
print(f"표준코드를 못 찾은 사건 {len(miss)}건(상장폐지·코드변경 추정):", ", ".join(miss["회사명"]) or "-")

# 원주가 vs 수정주가: 권리락일에 무슨 일이 생기나 (거래정지 없이 정상 거래된 1주당 1주 사례)
DEMO = "비츠로셀"
cand = ev.dropna(subset=["표준코드", "권리락일자"])
ex_demo = (cand[cand["회사명"] == DEMO] if (cand["회사명"] == DEMO).any() else cand.sort_values("발행비율")).iloc[-1]
q = int(ex_demo["권리락_pos"])
a_ = price_trend(ex_demo["표준코드"], days[q - 3], days[q + 2], adjusted=False)["종가"]
b_ = price_trend(ex_demo["표준코드"], days[q - 3], days[q + 2], adjusted=True)["종가"]
print(f"\n{ex_demo['회사명']} — 1주당 {ex_demo['발행비율']:g}주, 신주배정기준일 {ex_demo['신주배정기준일'].date()}, "
      f"권리락일 {ex_demo['권리락일자'].date()}")
pd.DataFrame({"원주가 종가": a_, "원주가 수익률": a_.pct_change().map(pct),
              "수정주가 종가": b_, "수정주가 수익률": b_.pct_change().map(pct)})

# %%
WIN_PRE, WIN_POST = 20, 10      # 경로 그림용 창(거래일)
rows, paths = [], {}
t0 = time.time()
for _, e in ev.dropna(subset=["표준코드", "반응일"]).iterrows():
    p = int(e["D0_pos"])
    if p - WIN_PRE - 1 < 0:
        continue
    ex_pos = None if pd.isna(e["권리락_pos"]) else int(e["권리락_pos"])
    last = min(len(days) - 1, max(p + WIN_POST, (ex_pos or 0) + 1))
    px = price_trend(e["표준코드"], days[p - WIN_PRE - 1], days[last])
    if px.empty:
        continue
    c = px["종가"].astype(float).reindex(days[p - WIN_PRE - 1:last + 1]).ffill()
    m = mkt_index[e["시장"]].reindex(c.index).ffill()
    o = p - WIN_PRE - 1                                   # c 안에서의 위치 = 전체 위치 - o

    def r(s, a, b):
        a, b = a - o, b - o
        return s.iloc[b] / s.iloc[a] - 1 if 0 <= a < len(s) and 0 <= b < len(s) else np.nan

    rec = {"접수번호": e["접수번호"]}
    for col, (a, b) in {"발표 전 20일": (p - 21, p - 1), "D0": (p - 1, p),
                        "D-1~D+1": (p - 2, p + 1), "D0~D+5": (p - 1, p + 5)}.items():
        rec[col] = r(c, a, b)
        rec[col + " 초과"] = rec[col] - r(m, a, b)
    if ex_pos is not None and ex_pos > p + 1:
        rec["권리락일"] = r(c, ex_pos - 1, ex_pos)
        rec["권리락일 초과"] = rec["권리락일"] - r(m, ex_pos - 1, ex_pos)
        rec["D0→권리락 거래일"] = ex_pos - p
    rows.append(rec)
    ar = (c.pct_change() - m.pct_change()).iloc[1:]          # 일별 초과수익, D-20 … D+10
    seg = ar.iloc[:WIN_PRE + WIN_POST + 1]
    if len(seg) == WIN_PRE + WIN_POST + 1:
        paths[e["접수번호"]] = seg.values
res = ev.merge(pd.DataFrame(rows), on="접수번호", how="inner")
res["연도"] = res["반응일"].dt.year
print(f"시세를 붙인 사건 {len(res)}건 ({time.time() - t0:.0f}초)")

# %% [markdown]
# ## 4. 결과
# ### 4-1. 전체 분포
# - **D0**: D−1 종가 → D0 종가 (발표 당일 반응)
# - **D-1~D+1**: D−2 종가 → D+1 종가 (예전 앱의 "전후1일 수익률"과 같은 3일 창)
# - **D0~D+5**: D−1 종가 → D+5 종가 (발표 후 한 주)
# - **초과** = 같은 구간 종목 수익률 − 소속 시장 지수(코스피/코스닥) 수익률

# %%
COLS = ["발표 전 20일", "D0", "D-1~D+1", "D0~D+5", "권리락일"]

def summary(df, cols):
    out = {}
    for c in cols:
        x = df[c].dropna()
        out[c] = {"n": len(x), "평균": pct(x.mean()), "중앙값": pct(x.median()),
                  "상승 비율": f"{(x > 0).mean() * 100:.0f}%" if len(x) else "-",
                  "하위 25%": pct(x.quantile(.25)), "상위 25%": pct(x.quantile(.75))}
    return pd.DataFrame(out).T

print("시장 대비 초과수익")
summary(res, [c + " 초과" for c in COLS])

# %%
print("원 수익률 (시장 미조정)")
summary(res, COLS)

# %%
fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
box_cols = ["D0 초과", "D-1~D+1 초과", "D0~D+5 초과"]
axes[0].boxplot([res[c].dropna() * 100 for c in box_cols], showfliers=False)
axes[0].set_xticks(range(1, len(box_cols) + 1), [c.replace(" 초과", "") for c in box_cols])
axes[0].axhline(0, color="gray", lw=.8)
axes[0].set_title(f"구간별 시장 대비 초과수익 분포 (%, n={len(res)}, 이상치 생략)")
axes[0].grid(alpha=.3)

car = pd.DataFrame(paths).T
car.columns = range(-WIN_PRE, WIN_POST + 1)
cum = (car.cumsum(axis=1).sub(car.loc[:, :-1].sum(axis=1), axis=0)) * 100   # D-1 종가 기준 0
axes[1].plot(cum.columns, cum.mean(), marker="o", ms=3, label="평균")
axes[1].plot(cum.columns, cum.median(), marker="o", ms=3, label="중앙값")
axes[1].axvline(0, color="gray", ls="--"); axes[1].axhline(0, color="gray", lw=.8)
axes[1].set_title(f"D0 전후 누적 초과수익 (D-1 종가=0, %, n={len(cum)})")
axes[1].set_xlabel("거래일 (D0 = 반응 첫날)"); axes[1].legend(); axes[1].grid(alpha=.3)
plt.tight_layout()

# %% [markdown]
# ### 4-2. 연도별
# 평균은 소수의 급등 종목에 끌려가기 쉬워 **중앙값과 상승 비율**을 함께 봅니다.

# %%
def by_group(df, key, cols=("D0 초과", "D-1~D+1 초과", "D0~D+5 초과")):
    g = df.groupby(key, observed=True)
    out = pd.DataFrame({"사건 수": g.size()})
    for c in cols:
        out[c + " 평균"] = g[c].mean().map(pct)
        out[c + " 중앙값"] = g[c].median().map(pct)
    out["D0 초과 상승 비율"] = g["D0 초과"].apply(lambda x: f"{(x > 0).mean() * 100:.0f}%")
    return out

by_group(res, "연도")

# %% [markdown]
# ### 4-3. 발행비율 구간별
# 1주당 신주배정 주식수로 나눕니다. 먼저 구간별 표, 다음 그림은 예전 앱처럼 비율과 D0 초과수익의 산점도(연도별 색)입니다.

# %%
res["비율 구간"] = pd.cut(res["발행비율"], [0, 0.3, 0.99, 1.0, 100],
                       labels=["0.3주 이하", "0.3~1주 미만", "1주", "1주 초과(2~3주)"])
by_group(res, "비율 구간")

# %%
fig, ax = plt.subplots(figsize=(8, 4.5))
for y, g in res.groupby("연도"):
    ax.scatter(g["발행비율"], g["D0 초과"] * 100, alpha=.7, label=f"{y}년")
ax.axhline(0, color="gray", lw=.8)
ax.set_xlabel("발행비율 (1주당 신주배정 주식수)"); ax.set_ylabel("D0 초과수익 (%)")
ax.set_title("발행비율 vs 발표 당일 초과수익"); ax.legend(); ax.grid(alpha=.3)
print("발행비율과 D0 초과수익의 순위상관(스피어만):",
      round(res[["발행비율", "D0 초과"]].corr(method="spearman").iloc[0, 1], 2))

# %% [markdown]
# ### 4-4. 반응이 컸던 사건
# 표의 `상세URL`은 KIND 공시 뷰어 링크입니다.

# %%
show = res.sort_values("D0 초과", ascending=False)
cols = ["반응일", "시장", "회사명", "발행비율", "D0 초과", "D-1~D+1 초과", "D0~D+5 초과", "상세URL"]
fmt = lambda d: d[cols].assign(**{c: d[c].map(pct) for c in cols if "초과" in c})
pd.concat([fmt(show.head(5)), fmt(show.tail(5))])

# %% [markdown]
# ## 결과 읽는 법과 한계
# - **D0와 D0~D+5를 비교**하세요. D0~D+5가 더 크면 첫날 이후에도 더 올랐다는 뜻이고(이 표본이 그렇습니다), 작으면 첫날 과열이 되돌려진 것입니다.
#   첫날 상한가(+30%)에 막힌 종목은 다음 날 나머지가 반영되므로 D-1~D+1 창도 같이 봅니다.
# - **발표 전 20일**이 이미 크게 올라 있으면 정보가 새었거나, 주가가 오른 회사가 무상증자를 택한 것(역인과)일 수 있습니다.
# - 초과수익은 **시장조정 모형**(종목 − 소속 시장 지수)입니다. 베타·규모 차이는 보정하지 않았고, 소형 코스닥주가 많아
#   지수 대비 변동이 큽니다.
# - **권리락일** 수익률은 수정주가 기준이라 기계적 하락이 빠진 "순수" 반응입니다. 원주가로 보면 1/(1+비율)만큼 떨어져 보입니다.
#   권리락일이 아직 오지 않은 최근 사건은 빠집니다.
# - 발행비율·기준일은 **최종 정정본** 값입니다. 발표 당시 비율과 다를 수 있습니다(정정 사유 대부분은 일정 변경).
# - 상장폐지·종목코드가 바뀐 회사는 기준일 시세표에 없어 빠질 수 있습니다(3절에 이름 출력).
# - 공시 시각 15:30 이후는 다음 거래일을 D0로 잡았습니다. 15:30~18:00 시간외 단일가 반응은 D0에 섞입니다.
