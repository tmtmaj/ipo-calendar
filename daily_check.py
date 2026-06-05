"""데일리 체크 5대 신호 수집 → daily_check_history.json 누적 (독립 실행용).

GitHub Actions가 매일 실행해 PC 무관하게 시장 신호를 날짜별로 쌓는다.
데이터: FRED(M2·금리), yfinance(지수·VIX·환율·금·DXY), alternative.me(공포탐욕).
모두 공개 소스라 API 키 불필요.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

KST = timezone(timedelta(hours=9))
HISTORY = Path(__file__).resolve().parent / "daily_check_history.json"
UA = {"User-Agent": "Mozilla/5.0"}


def _fred_csv(series: str, days_back: int = 90) -> pd.DataFrame:
    """FRED CSV를 requests(타임아웃)로 받아 DataFrame으로 반환.

    cosd(시작일)로 범위를 제한해 일별 장기 시리즈(DGS10 등)도 빠르게 받는다.
    """
    cosd = (datetime.now(KST) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={cosd}"
    res = requests.get(url, headers=UA, timeout=20)
    res.raise_for_status()
    return pd.read_csv(io.StringIO(res.text))


def _fred(series: str) -> float:
    df = _fred_csv(series, days_back=90)
    df.columns = [c.strip() for c in df.columns]
    dc = "observation_date" if "observation_date" in df.columns else "DATE"
    vc = series if series in df.columns else df.columns[-1]
    df = df.rename(columns={dc: "DATE", vc: "VAL"})
    df["VAL"] = pd.to_numeric(df["VAL"], errors="coerce")
    return float(df.dropna().iloc[-1]["VAL"])


def collect() -> dict:
    result: dict = {}

    # ① M2 YoY
    try:
        m2 = _fred_csv("M2SL", days_back=450)  # YoY 계산용 14개월
        m2.columns = [c.strip() for c in m2.columns]
        dc = "observation_date" if "observation_date" in m2.columns else "DATE"
        vc = "M2SL" if "M2SL" in m2.columns else m2.columns[-1]
        m2 = m2.rename(columns={dc: "DATE", vc: "M2SL"})
        m2["M2SL"] = pd.to_numeric(m2["M2SL"], errors="coerce")
        m2 = m2.dropna().tail(14)
        latest, yr_ago = float(m2.iloc[-1]["M2SL"]), float(m2.iloc[-13]["M2SL"])
        yoy = (latest - yr_ago) / yr_ago * 100
        result["m2"] = {"value": round(latest, 1), "yoy": round(yoy, 2), "ok": True}
    except Exception:
        result["m2"] = {"ok": False}

    # ② 금리
    try:
        fed, t10, t2 = _fred("FEDFUNDS"), _fred("DGS10"), _fred("DGS2")
        result["rates"] = {"fed": round(fed, 2), "t10": round(t10, 2),
                           "t2": round(t2, 2), "spread": round(t10 - t2, 2), "ok": True}
    except Exception:
        result["rates"] = {"ok": False}

    # ③ 지수·VIX·환율·금·DXY
    try:
        import yfinance as yf
        tk = yf.download(["^IXIC", "^GSPC", "^VIX", "USDKRW=X", "GC=F", "DX-Y.NYB"],
                         period="5d", progress=False, auto_adjust=True)
        closes = tk["Close"].dropna(how="all")

        def chg(sym):
            s = closes[sym].dropna()
            cur, prev = float(s.iloc[-1]), float(s.iloc[-2])
            return cur, round((cur - prev) / prev * 100, 2)

        ndx, ndx_c = chg("^IXIC")
        spx, spx_c = chg("^GSPC")
        vix, vix_c = chg("^VIX")
        krw, krw_c = chg("USDKRW=X")
        gold, gold_c = chg("GC=F")
        dxy, dxy_c = chg("DX-Y.NYB")
        result["market"] = {
            "nasdaq": ndx, "nasdaq_chg": ndx_c, "sp500": spx, "sp500_chg": spx_c,
            "vix": vix, "vix_chg": vix_c, "krw": krw, "krw_chg": krw_c,
            "gold": gold, "gold_chg": gold_c, "dxy": dxy, "dxy_chg": dxy_c, "ok": True,
        }
    except Exception:
        result["market"] = {"ok": False}

    # ④ 공포탐욕지수
    try:
        fng = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5).json()
        result["fear_greed"] = {"value": int(fng["data"][0]["value"]),
                                "classification": fng["data"][0]["value_classification"],
                                "ok": True}
    except Exception:
        result["fear_greed"] = {"ok": False}

    return result


def main() -> None:
    history = {}
    if HISTORY.exists():
        try:
            history = json.loads(HISTORY.read_text())
        except Exception:
            history = {}

    today = datetime.now(KST).strftime("%Y-%m-%d")
    history[today] = collect()
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2))
    print(f"✅ {today} 데일리 체크 저장 (총 {len(history)}일 누적)")


if __name__ == "__main__":
    main()
