import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.express as px
import logging

# ---------------------------------
# Streamlit page config
# ---------------------------------
st.set_page_config(page_title="Market Dashboard", layout="wide")
logging.basicConfig(level=logging.ERROR)

# ---------------------------------
# Volatility Fetch Function
# ---------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def fetch_volatility(ticker, period="6mo", interval="1d", window=20):
    """
    Download market data and calculate rolling volatility.
    """
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty or "Close" not in df.columns:
            return pd.DataFrame()

        df["Returns"] = df["Close"].pct_change()
        df["Volatility"] = df["Returns"].rolling(window=window).std() * np.sqrt(252)

        df = df.dropna()
        return df
    except Exception as e:
        logging.error(f"Volatility fetch failed for {ticker}: {e}")
        return pd.DataFrame()

# ---------------------------------
# Interpretation Logic
# ---------------------------------
def interpret_market(asset, latest_value):
    notes = []
    if asset == "US Dollar Index":
        notes.append("🟢 Stronger USD pressures EUR, GBP, Gold"
                     if latest_value > 0 else "🔴 Weak USD supports risk assets")
    elif asset == "US 10Y Yield":
        notes.append("🟢 Rising yields = tighter conditions"
                     if latest_value > 0 else "🔴 Falling yields = supportive for equities")
    elif asset == "Gold Futures":
        notes.append("🟢 Rising Gold = bullish hedge demand"
                     if latest_value > 0 else "🔴 Falling Gold = risk appetite improving")
    elif asset == "S&P 500":
        notes.append("🟢 Rising S&P = bullish sentiment"
                     if latest_value > 0 else "🔴 Falling S&P = bearish sentiment")
    elif asset in ["EUR/USD", "Euro Futures (6E)"]:
        notes.append("🟢 EUR gaining vs USD (risk-on)"
                     if latest_value > 0 else "🔴 EUR weakening (risk-off, USD stronger)")
    elif asset in ["GBP/USD", "British Pound Futures (6B)"]:
        notes.append("🟢 GBP strengthening vs USD"
                     if latest_value > 0 else "🔴 GBP weakening vs USD")
    elif asset in ["USD/JPY", "Japanese Yen Futures (6J)"]:
        notes.append("🟢 Rising USD/JPY = Yen weakens (risk-on)"
                     if latest_value > 0 else "🔴 Falling USD/JPY = Yen safe-haven demand")
    return notes

# ---------------------------------
# Assets
# ---------------------------------
assets_core = {
    "Gold Futures": "GC=F",
    "US Dollar Index": "DX=F",   # fixed ticker
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

# ---------------------------------
# Volatility Dashboard Function
# ---------------------------------
def show_volatility_dashboard(assets_dict):
    vol_cols = st.columns(2)
    idx = 0
    for name, ticker in assets_dict.items():
        df_vol = fetch_volatility(ticker)
        if not df_vol.empty:
            with vol_cols[idx % 2]:
                st.markdown(f"**{name}**")
                try:
                    fig = px.line(df_vol, x=df_vol.index, y="Volatility", template="plotly_dark")
                    st.plotly_chart(fig, use_container_width=True, height=200)

                    latest_vol = df_vol["Volatility"].iloc[-1]
                    st.metric("Current Vol", f"{latest_vol:.2%}")

                    notes = interpret_market(name, latest_vol)
                    for n in notes:
                        st.markdown(n, unsafe_allow_html=True)

                except Exception as e:
                    logging.error(f"Plotting failed for {ticker}: {e}")
                    st.warning(f"Plot failed for {name}")
        else:
            st.warning(f"No volatility data for {name}")
        idx += 1

# ---------------------------------
# UI Layout
# ---------------------------------
st.title("📊 Market Volatility Dashboard")

tab1, tab2, tab3 = st.tabs(["📈 Core Markets", "💱 Spot FX", "📊 Currency Futures"])

with tab1:
    show_volatility_dashboard(assets_core)

with tab2:
    show_volatility_dashboard(assets_spot)

with tab3:
    show_volatility_dashboard(assets_futures)

# ---------------------------------
# Debug Section (Optional)
# ---------------------------------
st.markdown("### 🔎 Debug Data Check")
for name, ticker in {**assets_core, **assets_spot, **assets_futures}.items():
    df = fetch_volatility(ticker)
    st.write(name, ticker, df.tail())
