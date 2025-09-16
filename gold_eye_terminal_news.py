# gold_eye_terminal_news_fixed.py
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import logging
import re
import streamlit as st
import pandas as pd
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed
from dateutil import parser as date_parser
import yfinance as yf

# --- Streamlit config ---
st.set_page_config(page_title="Gold Eye Terminal", layout="wide")

# --- Setup logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Inject custom CSS ---
st.markdown(
    """
    <style>
    body { background-color: #0d0d0d; color: #e6e600; }
    .terminal-box {
        background-color: #1a1a1a;
        border: 2px solid #333333;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 20px;
        box-shadow: 0px 0px 10px #000000;
    }
    .terminal-title {
        font-size: 20px;
        font-weight: bold;
        color: #00ffcc;
        border-bottom: 2px solid #00ffcc;
        margin-bottom: 10px;
        padding-bottom: 5px;
    }
    .note-bullish {
        background-color: #004d00;
        color: #00ff66;
        padding: 3px 6px;
        border-radius: 4px;
        margin-right: 4px;
        display: inline-block;
    }
    .note-bearish {
        background-color: #4d0000;
        color: #ff6666;
        padding: 3px 6px;
        border-radius: 4px;
        margin-right: 4px;
        display: inline-block;
    }
    .note-neutral {
        background-color: #333300;
        color: #ffff66;
        padding: 3px 6px;
        border-radius: 4px;
        display: inline-block;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Feeds list (cleaned, working) ---
feeds = {
    "market_feeds": {
        "fxstreet": "https://www.fxstreet.com/rss/news",
        "fxempire": "https://www.fxempire.com/news/feed",
        "investing_commodities": "https://www.investing.com/commodities/rss/news.rss",
        "kitco_metals": "https://www.kitco.com/rss",
        "reuters_commodities": "https://feeds.reuters.com/reuters/commoditiesNews",
    },
    "global_feeds": {
        "reuters": "https://feeds.reuters.com/reuters/topNews",
        "bbc": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
        "dawn": "https://www.dawn.com/feed",
        "usgs_quakes_day": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
    }
}

# --- Keywords ---
impact_keywords = {
    "gold": ["gold", "bullion", "precious metal"],
    "usd": ["dollar", "usd", "greenback"],
    "rates": ["interest rate", "rate hike", "fed", "federal reserve"],
    "inflation": ["inflation", "cpi", "ppi"],
    "jobs": ["jobs", "employment", "unemployment", "payroll"],
}
positive_words = ["rise", "growth", "bullish", "positive", "strong"]
negative_words = ["fall", "decline", "bearish", "negative", "weak"]

# --- Assets for Volatility Terminal ---
assets = {
    "Gold Futures": "GC=F",
    "US Dollar Index": "DX-Y.NYB",
    "US 10Y Yield": "^TNX",
    "S&P 500": "^GSPC",
}

# --- Helpers ---
def parse_pub_date(pub_date_str):
    try:
        dt = date_parser.parse(pub_date_str)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def analyze_impact(title, description):
    impact = []
    text = (title + " " + description).lower()
    for k, words in impact_keywords.items():
        if any(w in text for w in words):
            impact.append(k)
    return ", ".join(impact) if impact else "general"


def analyze_sentiment(title, description):
    text = (title + " " + description).lower()
    pos = any(word in text for word in positive_words)
    neg = any(word in text for word in negative_words)
    if pos and not neg:
        return "Positive"
    elif neg and not pos:
        return "Negative"
    elif pos and neg:
        return "Mixed"
    else:
        return "Neutral"


def _fetch_feed(feed_name, url):
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "").lower()

        # JSON feeds (USGS earthquakes, etc.)
        if "json" in content_type or url.endswith(".json") or url.endswith(".geojson"):
            data = r.json()
            items = []
            if "features" in data:  # USGS format
                for f in data["features"]:
                    props = f.get("properties", {})
                    items.append({
                        "feed": feed_name,
                        "title": props.get("title", ""),
                        "description": props.get("place", ""),
                        "link": props.get("url", ""),
                        "pub": datetime.fromtimestamp(props.get("time", 0) / 1000, tz=timezone.utc),
                        "impact": "general",
                        "sentiment": "Neutral",
                    })
            return items

        # XML / RSS feeds
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            description = item.findtext("description", "").strip()
            link = item.findtext("link", "").strip()
            pubRaw = item.findtext("pubDate")
            pub = parse_pub_date(pubRaw) if pubRaw else datetime.now(timezone.utc)
            items.append({
                "feed": feed_name,
                "title": title,
                "description": description,
                "link": link,
                "pub": pub,
                "impact": analyze_impact(title, description),
                "sentiment": analyze_sentiment(title, description),
            })
        return items

    except Exception as e:
        logging.error(f"Failed to fetch {feed_name} ({url}): {e}")
        return []


@st.cache_data(ttl=300, show_spinner=False)
def fetch_feeds():
    all_data = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_fetch_feed, fname, url): (fname, url)
            for category, feed_group in feeds.items()
            for fname, url in feed_group.items()
        }
        for f in as_completed(futures):
            fname, url = futures[f]
            try:
                items = f.result()
                if fname not in all_data:
                    all_data[fname] = []
                all_data[fname].extend(items)
            except Exception as e:
                logging.error(f"Error in future for {fname} ({url}): {e}")
    return all_data


@st.cache_data(ttl=900, show_spinner=False)
def fetch_volatility(ticker: str) -> pd.DataFrame:
    """
    Fetch volatility with intraday (1h) if available,
    otherwise fallback to daily candles.
    """
    try:
        # Try 1h data first
        raw = yf.download(ticker, period="1mo", interval="1h", progress=False)
        if raw is None or raw.empty:
            # Fallback to daily data
            raw = yf.download(ticker, period="6mo", interval="1d", progress=False)

        if raw is None or raw.empty:
            return pd.DataFrame()

        price_series = raw["Close"] if "Close" in raw.columns else raw.iloc[:, 0]
        df = pd.DataFrame({"Close": price_series})
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        if len(df) < 3:
            return pd.DataFrame()

        df["Returns"] = df["Close"].pct_change()
        window = 24 if "h" in raw.index.freqstr.lower() if raw.index.freqstr else False else 5
        df["Volatility"] = df["Returns"].rolling(window=window).std() * (window ** 0.5)
        df = df.dropna(subset=["Volatility"])
        return df

    except Exception as e:
        logging.error(f"Volatility fetch failed for {ticker}: {e}")
        return pd.DataFrame()


# --- Trader-friendly Interpretation with Styling ---
def interpret_market(asset: str, df: pd.DataFrame) -> list[str]:
    notes = []
    if asset == "US 10Y Yield":
        latest_value = df["Volatility"].iloc[-1]
        if latest_value < 0.02:
            notes = [
                '<span class="note-bullish">🟢 Bullish Gold</span>',
                '<span class="note-bearish">🔴 Bearish USD</span>',
                '<span class="note-bullish">🟢 Supportive Stocks</span>',
            ]
        elif latest_value > 0.04:
            notes = [
                '<span class="note-bearish">🔴 Bearish Gold</span>',
                '<span class="note-bullish">🟢 Bullish USD</span>',
                '<span class="note-bearish">🔴 Risk-Off Stocks</span>',
            ]
        else:
            notes = ['<span class="note-neutral">⚖️ Neutral across markets</span>']

    elif asset == "US Dollar Index":
        latest_value = df["Close"].iloc[-1]
        if latest_value > 105:
            notes = [
                '<span class="note-bearish">🔴 Bearish Gold</span>',
                '<span class="note-bullish">🟢 Bullish USD</span>',
                '<span class="note-bearish">🔴 Weighs on Stocks</span>',
            ]
        elif latest_value < 100:
            notes = [
                '<span class="note-bullish">🟢 Bullish Gold</span>',
                '<span class="note-bearish">🔴 Weak USD</span>',
                '<span class="note-bullish">🟢 Supportive Stocks</span>',
            ]
        else:
            notes = ['<span class="note-neutral">⚖️ Range-bound impact</span>']

    elif asset == "Gold Futures":
        trend_up = df["Close"].iloc[-1] > df["Close"].iloc[-2]
        notes = [
            '<span class="note-bullish">🟢 Rising Gold supports bulls</span>'
            if trend_up else '<span class="note-bearish">🔴 Falling Gold pressures bulls</span>'
        ]

    elif asset == "S&P 500":
        trend_up = df["Close"].iloc[-1] > df["Close"].iloc[-2]
        notes = [
            '<span class="note-bullish">🟢 Bullish Stocks = Risk-On, 🔴 Bearish Gold</span>'
            if trend_up else '<span class="note-bearish">🔴 Bearish Stocks = Risk-Off, 🟢 Bullish Gold</span>'
        ]

    else:
        notes = ['<span class="note-neutral">ℹ️ No bias rules defined</span>']
    return notes

# --- Streamlit UI ---
st.title("Gold Eye - Terminal")
slow_refresh = st.sidebar.slider("Refresh interval (seconds)", 60, 900, 300)

col1, col2 = st.columns([2, 2])

# --- News Terminal ---
with col1:
    st.markdown('<div class="terminal-box"><div class="terminal-title">Headlines</div>', unsafe_allow_html=True)
    feed_data = fetch_feeds()

    all_news = []
    for _, items in feed_data.items():
        all_news.extend(items)

    dedup = {item["link"]: item for item in all_news if item.get("link")}
    all_news = list(dedup.values())
    all_news.sort(key=lambda x: x["pub"], reverse=True)

    important_news = [
        n for n in all_news if n["impact"] != "general" or n["sentiment"] != "Neutral"
    ]

    st.markdown("**⚡ Important News**")
    if important_news:
        for n in important_news[:10]:
            safe_title = re.sub(r"<.*?>", "", n["title"], flags=re.DOTALL)
            st.markdown(f"🔹 **[{safe_title}]({n['link']})**")
            st.caption(f"{n['impact'].title()} | {n['sentiment']} | {n['pub'].strftime('%Y-%m-%d %H:%M %Z')}")
    else:
        st.info("No important news detected, showing latest headlines.")
        for n in all_news[:10]:
            safe_title = re.sub(r"<.*?>", "", n["title"], flags=re.DOTALL)
            st.markdown(f"▫️ **[{safe_title}]({n['link']})**")
            st.caption(f"{n['impact'].title()} | {n['sentiment']} | {n['pub'].strftime('%Y-%m-%d %H:%M %Z')}")

    st.markdown("** Sentiment Heatmap**")
    if all_news:
        df_news = pd.DataFrame(all_news)
        if not df_news.empty and {"impact", "sentiment"}.issubset(df_news.columns):
            impact_counts = df_news.groupby(["impact", "sentiment"]).size().reset_index(name="count")
            if not impact_counts.empty:
                fig = px.density_heatmap(
                    impact_counts,
                    x="impact",
                    y="sentiment",
                    z="count",
                    text_auto=True,
                    color_continuous_scale="Viridis",
                    template="plotly_dark",
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No sentiment buckets to display.")
        else:
            st.info("No sentiment data available.")
    else:
        st.info("No news data available.")
    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("🔎 Debug: Raw Feeds"):
        st.json(all_news[:5])

# --- Volatility Terminal ---
with col2:
    st.markdown('<div class="terminal-box"><div class="terminal-title"> Volatility Terminal</div>', unsafe_allow_html=True)
    vol_cols = st.columns(2)
    idx = 0
    for name, ticker in assets.items():
        df_vol = fetch_volatility(ticker)
        if not df_vol.empty:
            with vol_cols[idx % 2]:
                st.markdown(f"**{name}**")
                try:
                    fig = px.line(df_vol, x=df_vol.index, y="Volatility", template="plotly_dark", height=200)
                    st.plotly_chart(fig, use_container_width=True)
                    latest_vol = df_vol["Volatility"].iloc[-1]
                    st.metric("Current Vol", f"{latest_vol:.2%}")
                    notes = interpret_market(name, df_vol)
                    for n in notes:
                        st.markdown(n, unsafe_allow_html=True)
                except Exception as e:
                    logging.error(f"Plotting failed for {ticker}: {e}")
                    st.warning(f"Plot failed for {name}")
        else:
            st.warning(f"No volatility data for {name}")
        idx += 1
    st.markdown("</div>", unsafe_allow_html=True)

