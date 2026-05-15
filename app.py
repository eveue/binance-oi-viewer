"""
Binance OI Viewer — 币安 USDT 永续合约持仓量历史查询工具
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from binance_oi import (
    fetch_full_range,
    fetch_usdt_perpetual_symbols,
)

st.set_page_config(
    page_title="Binance OI Viewer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      html, body, [class*="css"] {
        font-family: -apple-system, "SF Pro Display", "Segoe UI", "PingFang SC",
                     "Microsoft YaHei", sans-serif;
      }
      .main-header { font-size: 1.85rem; font-weight: 600; letter-spacing: -0.02em; margin-bottom: 0.2rem; }
      .subtitle { color: #6b7280; font-size: 0.9rem; margin-bottom: 2rem; }
      .metric-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1rem 1.2rem; }
      .metric-label { color: #64748b; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; }
      .metric-value { font-size: 1.4rem; font-weight: 600; color: #0f172a; margin-top: 0.2rem; }
      .footer-note { color: #94a3b8; font-size: 0.8rem; margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid #e2e8f0; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="main-header">Binance OI Viewer</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">币安 USDT 永续合约 · 任意历史时段持仓量精确查询</div>', unsafe_allow_html=True)


@st.cache_data(ttl=3600)
def get_symbol_list():
    return fetch_usdt_perpetual_symbols()


@st.cache_data(ttl=600, show_spinner=False)
def get_oi_data(symbol, start_iso, end_iso):
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    return fetch_full_range(symbol, start, end)


with st.sidebar:
    st.markdown("### 查询条件")
    try:
        symbols = get_symbol_list()
    except Exception as e:
        st.error(f"加载交易对清单失败：{e}")
        st.stop()

    default_index = symbols.index("BTCUSDT") if "BTCUSDT" in symbols else 0
    symbol = st.selectbox("交易对", symbols, index=default_index)

    st.markdown("##### 时间范围（UTC）")
    today = datetime.now(timezone.utc).date()
    default_start = today - timedelta(days=30)

    col_start, col_end = st.columns(2)
    with col_start:
        start_date = st.date_input("起始日期", value=default_start,
                                    min_value=date(2019, 9, 8), max_value=today)
        start_time = st.time_input("起始时间", value=time(0, 0))
    with col_end:
        end_date = st.date_input("结束日期", value=today,
                                  min_value=date(2019, 9, 8), max_value=today)
        end_time = st.time_input("结束时间", value=time(23, 59))

    start_dt = datetime.combine(start_date, start_time, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, end_time, tzinfo=timezone.utc)

    if end_dt <= start_dt:
        st.warning("结束时间必须晚于起始时间")
        st.stop()

    span_days = (end_dt - start_dt).days
    st.caption(f"查询跨度：{span_days} 天")
    run = st.button("查询", type="primary", use_container_width=True)


if not run:
    st.info(
        "在左侧选择交易对和时间范围，然后点击「查询」。\n\n"
        "**数据说明**：\n"
        "- 历史数据来自币安官方公开归档（data.binance.vision），5 分钟粒度\n"
        "- 当天最新数据来自币安实时 API\n"
        "- OI = Open Interest，未平仓合约总量\n"
        "- USD 名义价值精度优于 1 USD（远超 0.1M 要求）"
    )
    st.stop()

with st.spinner(f"正在加载 {symbol} 在 {start_dt:%Y-%m-%d %H:%M} 至 {end_dt:%Y-%m-%d %H:%M} UTC 期间的数据..."):
    try:
        df = get_oi_data(symbol, start_dt.isoformat(), end_dt.isoformat())
    except Exception as e:
        st.error(f"数据加载失败：{e}")
        st.stop()

if df.empty:
    st.warning(f"该时段无 {symbol} 的 OI 数据。可能该交易对尚未上线，或币安归档暂无该日数据。")
    st.stop()

latest = df.iloc[-1]
peak_idx = df["sum_open_interest_value"].idxmax()
trough_idx = df["sum_open_interest_value"].idxmin()

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f'<div class="metric-card"><div class="metric-label">期末 OI</div><div class="metric-value">${latest["sum_open_interest_value"]/1e6:,.2f}M</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="metric-card"><div class="metric-label">峰值 OI</div><div class="metric-value">${df.loc[peak_idx, "sum_open_interest_value"]/1e6:,.2f}M</div></div>', unsafe_allow_html=True)
    st.caption(f"@ {df.loc[peak_idx, 'create_time']:%Y-%m-%d %H:%M} UTC")
with c3:
    st.markdown(f'<div class="metric-card"><div class="metric-label">谷值 OI</div><div class="metric-value">${df.loc[trough_idx, "sum_open_interest_value"]/1e6:,.2f}M</div></div>', unsafe_allow_html=True)
    st.caption(f"@ {df.loc[trough_idx, 'create_time']:%Y-%m-%d %H:%M} UTC")
with c4:
    first_val = df.iloc[0]["sum_open_interest_value"]
    last_val = df.iloc[-1]["sum_open_interest_value"]
    pct = (last_val - first_val) / first_val * 100 if first_val else 0
    st.markdown(f'<div class="metric-card"><div class="metric-label">区间变化</div><div class="metric-value">{pct:+.1f}%</div></div>', unsafe_allow_html=True)

st.markdown("")

tab_chart, tab_table, tab_lookup = st.tabs(["📈 曲线图", "📋 数据表", "🔍 精确时刻查询"])

with tab_chart:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["create_time"], y=df["sum_open_interest_value"] / 1e6,
        mode="lines", name="OI (USD, M)", line=dict(color="#2563eb", width=2),
        hovertemplate="<b>%{x|%Y-%m-%d %H:%M} UTC</b><br>OI (USD): $%{y:,.3f}M<extra></extra>",
    ))
    fig.update_layout(
        title=f"{symbol} 持仓量历史 ({start_dt:%Y-%m-%d} ~ {end_dt:%Y-%m-%d} UTC)",
        xaxis_title="时间 (UTC)", yaxis_title="未平仓合约名义价值 (Million USD)",
        height=520, hovermode="x unified",
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(gridcolor="#f1f5f9", rangeslider=dict(visible=True, thickness=0.06),
                   rangeselector=dict(buttons=[
                       dict(count=1, label="1d", step="day", stepmode="backward"),
                       dict(count=7, label="1w", step="day", stepmode="backward"),
                       dict(count=1, label="1m", step="month", stepmode="backward"),
                       dict(count=3, label="3m", step="month", stepmode="backward"),
                       dict(step="all", label="全部"),
                   ])),
        yaxis=dict(gridcolor="#f1f5f9"),
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("查看持仓张数（base asset）"):
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=df["create_time"], y=df["sum_open_interest"],
            mode="lines", name="OI (张数)", line=dict(color="#10b981", width=2),
            hovertemplate="<b>%{x|%Y-%m-%d %H:%M} UTC</b><br>OI 张数: %{y:,.2f}<extra></extra>",
        ))
        base_asset = symbol.replace("USDT", "")
        fig2.update_layout(
            xaxis_title="时间 (UTC)", yaxis_title=f"未平仓张数 ({base_asset})",
            height=400, plot_bgcolor="white", paper_bgcolor="white",
            xaxis=dict(gridcolor="#f1f5f9"), yaxis=dict(gridcolor="#f1f5f9"),
        )
        st.plotly_chart(fig2, use_container_width=True)


with tab_table:
    st.markdown(f"**共 {len(df):,} 条记录**（5 分钟粒度）")
    display_df = df.copy()
    display_df["create_time"] = display_df["create_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    display_df["sum_open_interest_value"] = display_df["sum_open_interest_value"].round(2)
    display_df["sum_open_interest"] = display_df["sum_open_interest"].round(4)
    display_df.columns = ["时间 (UTC)", "交易对", "OI 张数", "OI (USD)"]
    st.dataframe(display_df, use_container_width=True, height=500, hide_index=True)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label="📥 下载 CSV", data=csv,
        file_name=f"{symbol}_oi_{start_dt:%Y%m%d_%H%M}_{end_dt:%Y%m%d_%H%M}.csv",
        mime="text/csv")


with tab_lookup:
    st.markdown("查询任意精确时刻的 OI 值（返回最接近的 5 分钟快照）")
    col_a, col_b = st.columns([3, 2])
    with col_a:
        lookup_date = st.date_input("日期", value=df["create_time"].dt.date.iloc[-1],
            min_value=df["create_time"].dt.date.min(),
            max_value=df["create_time"].dt.date.max(), key="lookup_date")
    with col_b:
        lookup_time = st.time_input("时间 (UTC)", value=time(12, 0), key="lookup_time")

    lookup_dt = datetime.combine(lookup_date, lookup_time, tzinfo=timezone.utc)
    df_sorted = df.copy()
    df_sorted["diff"] = (df_sorted["create_time"] - lookup_dt).abs()
    closest = df_sorted.nsmallest(1, "diff").iloc[0]
    diff_minutes = closest["diff"].total_seconds() / 60

    st.markdown("---")
    rc1, rc2 = st.columns(2)
    with rc1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">最近快照时间 (UTC)</div><div class="metric-value" style="font-size:1.1rem">{closest["create_time"]:%Y-%m-%d %H:%M:%S}</div></div>', unsafe_allow_html=True)
        st.caption(f"距查询时间 {diff_minutes:.1f} 分钟")
    with rc2:
        st.markdown(f'<div class="metric-card"><div class="metric-label">OI 值</div><div class="metric-value">${closest["sum_open_interest_value"]/1e6:,.4f}M</div></div>', unsafe_allow_html=True)
        st.caption(f"= ${closest['sum_open_interest_value']:,.2f} = {closest['sum_open_interest']:,.4f} {symbol.replace('USDT', '')}")


st.markdown('<div class="footer-note">数据源：data.binance.vision（历史归档）+ fapi.binance.com（实时段）· 所有时间均为 UTC</div>', unsafe_allow_html=True)
