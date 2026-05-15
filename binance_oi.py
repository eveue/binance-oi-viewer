"""币安 USDT 永续合约 OI 数据采集模块"""

from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests

VISION_BASE = "https://data.binance.vision/data/futures/um/daily/metrics"
FAPI_BASE = "https://fapi.binance.com"
EXCHANGE_INFO_URL = f"{FAPI_BASE}/fapi/v1/exchangeInfo"
OI_HIST_URL = f"{FAPI_BASE}/futures/data/openInterestHist"

HTTP_TIMEOUT = 30
MAX_WORKERS = 8

METRICS_COLUMNS = [
    "create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
    "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
    "count_long_short_ratio", "sum_taker_long_short_vol_ratio",
]


def fetch_usdt_perpetual_symbols() -> list:
    resp = requests.get(EXCHANGE_INFO_URL, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    symbols = []
    for s in data.get("symbols", []):
        if (s.get("contractType") == "PERPETUAL"
                and s.get("quoteAsset") == "USDT"
                and s.get("status") == "TRADING"):
            symbols.append(s["symbol"])
    return sorted(symbols)


def _build_vision_url(symbol: str, day: date) -> str:
    fname = f"{symbol}-metrics-{day.isoformat()}.zip"
    return f"{VISION_BASE}/{symbol}/{fname}"


def _fetch_one_day(symbol: str, day: date) -> Optional[pd.DataFrame]:
    url = _build_vision_url(symbol, day)
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = zf.namelist()[0]
            with zf.open(csv_name) as f:
                raw = f.read().decode("utf-8")
        first_line = raw.splitlines()[0]
        has_header = "create_time" in first_line
        df = pd.read_csv(
            io.StringIO(raw),
            header=0 if has_header else None,
            names=None if has_header else METRICS_COLUMNS,
        )
    except Exception:
        return None

    if "create_time" not in df.columns:
        return None

    df["create_time"] = pd.to_datetime(df["create_time"], utc=True, errors="coerce")
    df["sum_open_interest"] = pd.to_numeric(df["sum_open_interest"], errors="coerce")
    df["sum_open_interest_value"] = pd.to_numeric(df["sum_open_interest_value"], errors="coerce")
    df = df.dropna(subset=["create_time", "sum_open_interest_value"])
    df = df[["create_time", "symbol", "sum_open_interest", "sum_open_interest_value"]]
    return df


def fetch_history_range(symbol, start, end, progress_callback=None):
    if end < start:
        return pd.DataFrame(columns=["create_time", "symbol", "sum_open_interest", "sum_open_interest_value"])

    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)

    frames = []
    completed = 0
    total = len(days)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_one_day, symbol, d): d for d in days}
        for fut in as_completed(futures):
            df = fut.result()
            if df is not None and not df.empty:
                frames.append(df)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    if not frames:
        return pd.DataFrame(columns=["create_time", "symbol", "sum_open_interest", "sum_open_interest_value"])

    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values("create_time").reset_index(drop=True)
    return out


def fetch_recent_oi(symbol, period="5m", limit=500):
    params = {"symbol": symbol, "period": period, "limit": limit}
    resp = requests.get(OI_HIST_URL, params=params, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return pd.DataFrame(columns=["create_time", "symbol", "sum_open_interest", "sum_open_interest_value"])

    df = pd.DataFrame(rows)
    df["create_time"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["sum_open_interest"] = pd.to_numeric(df["sumOpenInterest"], errors="coerce")
    df["sum_open_interest_value"] = pd.to_numeric(df["sumOpenInterestValue"], errors="coerce")
    return df[["create_time", "symbol", "sum_open_interest", "sum_open_interest_value"]].sort_values("create_time").reset_index(drop=True)


def fetch_full_range(symbol, start, end, progress_callback=None):
    today_utc = datetime.now(timezone.utc).date()
    yesterday_utc = today_utc - timedelta(days=1)

    start_date = start.date()
    end_date = end.date()

    archive_end = min(end_date, yesterday_utc)
    if start_date <= archive_end:
        hist = fetch_history_range(symbol, start_date, archive_end, progress_callback)
    else:
        hist = pd.DataFrame(columns=["create_time", "symbol", "sum_open_interest", "sum_open_interest_value"])

    recent = pd.DataFrame(columns=hist.columns)
    if end_date >= yesterday_utc:
        try:
            recent = fetch_recent_oi(symbol, period="5m", limit=500)
        except Exception:
            pass

    combined = pd.concat([hist, recent], ignore_index=True)
    if combined.empty:
        return combined

    combined = combined.drop_duplicates(subset=["create_time"], keep="last")
    combined = combined.sort_values("create_time").reset_index(drop=True)

    start_utc = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    end_utc = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    mask = (combined["create_time"] >= start_utc) & (combined["create_time"] <= end_utc)
    return combined.loc[mask].reset_index(drop=True)
