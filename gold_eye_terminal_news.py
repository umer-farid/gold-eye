# gold_eye_terminal_news.py (fixed)
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

# --- Streamlit config must come first ---
st.set_page_config(page_title="Gold Eye - Terminals", layout="wide")

# --- Setup logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Inject custom CSS for Bloomberg-style terminal ---
st.markdown(
    """
    <style>
    body {
        background-color: #0d0d0d;
        color: #e6e600;
    }
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
    .stMetric {
        background-color: #000000 !important;
        border: 1px solid #333333;
        padding: 10px;
        border-radius: 5px;
    }
    a { color: #76f1c0; }
    .streamlit-expanderHeader { color: #e6e600 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Feeds list ---
feeds = {
    "Market News": [
        "https://www.investing.com/rss/news.rss",
        "https://www.marketwatch.com/feeds/topstories",
    ],
    "Global News": [
        "https://www.reutersagency.com/feed/?best-topics=business-finance",
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    ],
    "Jobs Data": [
        "https://www.bls.gov/feed/at-a-glance/Employment.xml",
    ],
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
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            description = item.findtext("description", "").strip()
            link = item.findtext("link", "").strip()
            pubRaw = item.findtext("pubDate")
            pub = parse_pub_date(pubRaw) if pubRaw else datetime.now(timezone.utc)
            items.append(
                {
                    "feed": feed_name,
                    "title": title,
                    "description": description,
                    "link": link,
                    "pub": pub,
                    "impact": analyze_impact(title, description),
                    "sentiment": analyze_sentiment(title, description),
                }
            )
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
            for fname, urls in feeds.items()
            for url in urls
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
    Download price data for `ticker` and return a DataFrame with simple columns:
      - Close
      - Returns
      - Volatility
    Robust to yfinance returning MultiIndex columns.
    """
    try:
        raw = yf.download(ticker, period="1mo", interval="1h", progress=False)
        if raw is None or raw.empty:
            logging.warning(f"No data returned for {ticker}")
            return pd.DataFrame()

        # If yfinance returns MultiIndex columns (e.g. when group_by='ticker' or multiple tickers),
        # extract the price series robustly:
        if isinstance(raw.columns, pd.MultiIndex):
            # prefer 'Close' then 'Adj Close'
            price_col = None
            for preferred in ("Close", "Adj Close", "Adj_Close", "AdjClose"):
                matches = [c for c in raw.columns if c[0] == preferred]
                if matches:
                    price_col = matches[0]
                    break
            if price_col is None:
                # fallback: try to collapse to single-level by joining column tuples
                raw.columns = ["_".join([str(x) for x in col if x]) for col in raw.columns]
                # pick first column that looks like a price
                for cand in ("Close", "Adj Close", "Adj_Close", "AdjClose", "close"):
                    if cand in raw.columns:
                        price_series = raw[cand]
                        break
                else:
                    price_series = raw.iloc[:, 0]
            else:
                price_series = raw[price_col]
        else:
            # single-level columns
            if "Close" in raw.columns:
                price_series = raw["Close"]
            elif "Adj Close" in raw.columns:
                price_series = raw["Adj Close"]
            else:
                price_series = raw.iloc[:, 0]

        # build a clean DataFrame
        df = pd.DataFrame({"Close": price_series})
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # need at least 2 points to compute returns
        if len(df) < 3:
            logging.warning(f"Not enough data points to compute volatility for {ticker}")
            return pd.DataFrame()

        df["Returns"] = df["Close"].pct_change()
        # 24 hourly periods -> dailyize (sqrt of periods per day). If interval isn't hourly this is approximate.
        df["Volatility"] = df["Returns"].rolling(window=24).std() * (24 ** 0.5)
        df = df.dropna(subset=["Volatility"])
        return df
    except Exception as e:
        logging.error(f"Volatility fetch failed for {ticker}: {e}")
        return pd.DataFrame()


# --- Streamlit UI ---
st.title("💻 Gold Eye - Bloomberg Style Terminals")

slow_refresh = st.sidebar.slider("Refresh interval (seconds)", 60, 900, 300)

col1, col2 = st.columns([2, 2])

# --- News Terminal ---
with col1:
    st.markdown('<div class="terminal-box"><div class="terminal-title">📰 Terminal News</div>', unsafe_allow_html=True)
    feed_data = fetch_feeds()

    all_news = []
    for category, items in feed_data.items():
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
            safe_title = re.sub(r"<.*?>", "", n["title"])
            st.markdown(f"🔹 **[{safe_title}]({n['link']})**")
            st.caption(f"{n['impact'].title()} | {n['sentiment']} | {n['pub'].strftime('%Y-%m-%d %H:%M %Z')}")
    else:
        st.info("No important news detected.")

    st.markdown("**📊 Sentiment Heatmap**")
    if all_news:
        df_news = pd.DataFrame(all_news)
        if not df_news.empty and "impact" in df_news and "sentiment" in df_news:
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
                st.warning("No sentiment buckets to display.")
        else:
            st.warning("No sentiment data available.")
    else:
        st.warning("No news data available.")
    st.markdown("</div>", unsafe_allow_html=True)

# --- Volatility Terminal ---
with col2:
    st.markdown('<div class="terminal-box"><div class="terminal-title">📉 Volatility Terminal</div>', unsafe_allow_html=True)
    vol_cols = st.columns(2)
    idx = 0
    for name, ticker in assets.items():
        df_vol = fetch_volatility(ticker)
        if not df_vol.empty:
            # plot using index as x and simple 'Volatility' column name
            with vol_cols[idx % 2]:
                st.markdown(f"**{name}**")
                try:
                    fig = px.line(df_vol, x=df_vol.index, y="Volatility", template="plotly_dark")
                    st.plotly_chart(fig, use_container_width=True, height=200)
                    latest_vol = df_vol["Volatility"].iloc[-1]
                    st.metric("Current Vol", f"{latest_vol:.2%}")
                except Exception as e:
                    logging.error(f"Plotting failed for {ticker}: {e}")
                    st.warning(f"Plot failed for {name}")
        else:
            st.warning(f"No volatility data for {name}")
        idx += 1
    st.markdown("</div>", unsafe_allow_html=True)
