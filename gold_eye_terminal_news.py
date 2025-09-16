# gold_eye_volatility_fixed.py
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.express as px
import logging
import traceback

# === Page config ===
st.set_page_config(page_title="Gold Eye - Volatility", layout="wide")
logging.basicConfig(level=logging.ERROR)

# === CSS for badges ===
st.markdown(
    """
    <style>
    .note-bullish { background-color: #004d00; color: #00ff66; padding: 4px 8px; border-radius:6px; display:inline-block; margin:4px 2px;}
    .note-bearish { background-color: #4d0000; color: #ff9999; padding: 4px 8px; border-radius:6px; display:inline-block; margin:4px 2px;}
    .note-neutral { background-color: #333300; color: #ffff99; padding: 4px 8px; border-radius:6px; display:inline-block; margin:4px 2px;}
    small { color: #cfcfcf; }
    </style>
    """,
    unsafe_allow_html=True,
)

# === Improved volatility fetch ===
@st.cache_data(ttl=600, show_spinner=False)
def fetch_volatility(ticker: str, period: str = "180d", interval: str = "1d", window: int = 20) -> pd.DataFrame:
    """
    Download OHLC data via yfinance and compute rolling volatility.
    Returns a DataFrame with Close, Returns, Volatility.
    """
    try:
        raw = yf.download(ticker, period=period, interval=interval, progress=False, threads=True)
        if raw is None or raw.empty or "Close" not in raw.columns:
            return pd.DataFrame()

        df = raw.copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        df["Returns"] = df["Close"].pct_change()

        # pick annualization factor based on sample frequency
        if "d" in interval:
            annual_factor = np.sqrt(252)
        elif "h" in interval:
            annual_factor = np.sqrt(252 * 24)
        else:
            annual_factor = np.sqrt(252)

        df["Volatility"] = df["Returns"].rolling(window=window).std() * annual_factor
        df = df.dropna(subset=["Volatility"])
        return df
    except Exception:
        logging.error(traceback.format_exc())
        return pd.DataFrame()

# === Bias / interpretation function (uses price trend) ===
def interpret_market(asset_name: str, df: pd.DataFrame) -> list[str]:
    """
    Determine Bullish/Bearish/Neutral based on last close vs previous close.
    Returns a list of HTML-styled note strings.
    """
    notes = []
    if df is None or df.empty or "Close" not in df.columns:
        notes.append('<span class="note-neutral">ℹ️ No data</span>')
        return notes

    last = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2]) if len(df["Close"]) >= 2 else last
    pct = (last - prev) / prev if prev != 0 else 0.0

    # small threshold to avoid noise
    thr = 0.001  # 0.1%
    if pct > thr:
        bias = "bullish"
    elif pct < -thr:
        bias = "bearish"
    else:
        bias = "neutral"

    # Human-friendly messages by asset group
    if "Gold" in asset_name or "GC=F" in asset_name:
        if bias == "bullish":
            notes.append('<span class="note-bullish">🟢 Gold trending up — bullish</span>')
        elif bias == "bearish":
            notes.append('<span class="note-bearish">🔴 Gold trending down — bearish</span>')
        else:
            notes.append('<span class="note-neutral">⚖️ Gold range-bound</span>')

    elif "Dollar Index" in asset_name or "DX=F" in asset_name:
        if bias == "bullish":
            notes.append('<span class="note-bullish">🟢 USD strengthening — pressure on Gold/EUR</span>')
        elif bias == "bearish":
            notes.append('<span class="note-bearish">🔴 USD weakening — supportive for Gold/risk assets</span>')
        else:
            notes.append('<span class="note-neutral">⚖️ USD sideways</span>')

    elif "10Y" in asset_name or "^TNX" in asset_name:
        if bias == "bullish":
            notes.append('<span class="note-bullish">🟢 Yields up — tighter financial conditions</span>')
        elif bias == "bearish":
            notes.append('<span class="note-bearish">🔴 Yields down — easier conditions</span>')
        else:
            notes.append('<span class="note-neutral">⚖️ Yields flat</span>')

    elif "S&P" in asset_name or "^GSPC" in asset_name:
        if bias == "bullish":
            notes.append('<span class="note-bullish">🟢 Stocks up — risk-on</span>')
        elif bias == "bearish":
            notes.append('<span class="note-bearish">🔴 Stocks down — risk-off</span>')
        else:
            notes.append('<span class="note-neutral">⚖️ Stocks sideways</span>')

    elif "EUR" in asset_name or "6E" in asset_name:
        if bias == "bullish":
            notes.append('<span class="note-bullish">🟢 EUR strength vs USD</span>')
        elif bias == "bearish":
            notes.append('<span class="note-bearish">🔴 EUR weakness vs USD</span>')
        else:
            notes.append('<span class="note-neutral">⚖️ EUR range-bound</span>')

    elif "GBP" in asset_name or "6B" in asset_name:
        if bias == "bullish":
            notes.append('<span class="note-bullish">🟢 GBP strength vs USD</span>')
        elif bias == "bearish":
            notes.append('<span class="note-bearish">🔴 GBP weakness vs USD</span>')
        else:
            notes.append('<span class="note-neutral">⚖️ GBP sideways</span>')

    elif "JPY" in asset_name or "6J" in asset_name or "JPY=X" in asset_name:
        # USD/JPY rising => JPY weaker (risk-on); falling => JPY stronger (risk-off)
        if bias == "bullish":
            notes.append('<span class="note-bullish">🟢 USD/JPY up — JPY weaker (risk-on)</span>')
        elif bias == "bearish":
            notes.append('<span class="note-bearish">🔴 USD/JPY down — JPY stronger (risk-off)</span>')
        else:
            notes.append('<span class="note-neutral">⚖️ USD/JPY sideways</span>')

    else:
        # fallback
        if bias == "bullish":
            notes.append('<span class="note-bullish">🟢 Price trending up</span>')
        elif bias == "bearish":
            notes.append('<span class="note-bearish">🔴 Price trending down</span>')
        else:
            notes.append('<span class="note-neutral">⚖️ No clear bias</span>')

    # Add tiny change summary
    notes.append(f"<small>Change: {pct*100:.2f}% ({prev:.4f} → {last:.4f})</small>")
    return notes

# === Assets ===
assets_core = {
    "Gold Futures": "GC=F",
    "US Dollar Index": "DX=F",
    "US 10Y Yield": "^TNX",
    "S&P 500": "^GSPC",
}

assets_spot = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
}

assets_futures = {
    "Euro Futures (6E)": "6E=F",
    "British Pound Futures (6B)": "6B=F",
    "Japanese Yen Futures (6J)": "6J=F",
}

# === Dashboard renderer with better debug and robust plotting ===
def show_volatility_dashboard(assets_dict, period="180d", interval="1d", window=20):
    cols = st.columns(2)
    i = 0
    for name, ticker in assets_dict.items():
        col = cols[i % 2]
        with col:
            st.markdown(f"**{name}** — `{ticker}`")
            df = fetch_volatility(ticker, period=period, interval=interval, window=window)

            if df.empty:
                st.warning(f"No volatility data for {name} ({ticker})")
                # helpful debug expander
                with st.expander(f"Debug: raw download for {ticker}"):
                    try:
                        raw = yf.download(ticker, period="60d", interval="1d", progress=False, threads=True)
                        st.write("raw.tail():")
                        st.write(raw.tail())
                    except Exception as e:
                        st.write("Raw download failed:", str(e))
            else:
                # Plot volatility (px uses fig height and st.plotly_chart with use_container_width)
                try:
                    fig = px.line(df, x=df.index, y="Volatility", template="plotly_dark", height=220)
                    fig.update_xaxes(showgrid=False)
                    fig.update_yaxes(showgrid=False)
                    st.plotly_chart(fig, use_container_width=True)

                    latest_vol = df["Volatility"].iloc[-1]
                    st.metric("Current Vol", f"{latest_vol:.2%}")

                    # now interpret using price trend (df is passed)
                    notes = interpret_market(name, df)
                    for n in notes:
                        st.markdown(n, unsafe_allow_html=True)
                except Exception:
                    logging.error(traceback.format_exc())
                    st.error(f"Plot failed for {name}. See debug expander.")
                    with st.expander(f"Plot debug for {ticker}"):
                        st.write(df.tail())
        i += 1

# === UI ===
st.title("Gold Eye — Volatility (fixed)")
tab1, tab2, tab3 = st.tabs(["📈 Core Markets", "💱 Spot FX", "📊 Currency Futures"])

with tab1:
    show_volatility_dashboard(assets_core, period="180d", interval="1d", window=20)

with tab2:
    show_volatility_dashboard(assets_spot, period="180d", interval="1d", window=20)

with tab3:
    show_volatility_dashboard(assets_futures, period="180d", interval="1d", window=20)

# Optional debug summary at bottom
with st.expander("🔎 Quick debug: show last few rows for all tickers"):
    for name, ticker in {**assets_core, **assets_spot, **assets_futures}.items():
        df = fetch_volatility(ticker, period="60d", interval="1d", window=10)
        st.write(f"--- {name} ({ticker}) ---")
        if df.empty:
            st.write("No data returned")
        else:
            st.dataframe(df.tail(), use_container_width=True)
