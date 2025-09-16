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

# --- Setup logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

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

# --- Helpers ---
def parse_pub_date(pub_date_str):
    try:
        dt = date_parser.parse(pub_date_str)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        logging.warning(f"Date parse failed: {pub_date_str} ({e})")
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
def fetch_gold_volatility():
    try:
        df = yf.download("GC=F", period="1mo", interval="1h")  # Gold futures
        df["Returns"] = df["Close"].pct_change()
        df["Volatility"] = df["Returns"].rolling(window=24).std() * (24 ** 0.5)  # dailyized
        return df.dropna()
    except Exception as e:
        logging.error(f"Volatility fetch failed: {e}")
        return pd.DataFrame()


# --- Streamlit app ---
st.set_page_config(page_title="Gold Eye - Terminal", layout="wide")
st.title("🟡 Gold Eye - Multi-Terminal")

slow_refresh = st.sidebar.slider("Refresh interval (seconds)", 60, 900, 300)

# --- News Terminal ---
st.header("📰 Terminal News")
with st.spinner("Fetching latest feeds..."):
    feed_data = fetch_feeds()

all_news = []
for category, items in feed_data.items():
    for item in items:
        all_news.append(item)

dedup = {item["link"]: item for item in all_news if item["link"]}
all_news = list(dedup.values())
all_news.sort(key=lambda x: x["pub"], reverse=True)

important_news = [
    n for n in all_news if n["impact"] != "general" or n["sentiment"] != "Neutral"
]

st.subheader("⚡ Important News")
if important_news:
    for n in important_news[:15]:
        safe_title = re.sub(r'<.*?>', '', n["title"])
        st.markdown(f"**[{safe_title}]({n['link']})**  ")
        st.caption(f"{n['impact'].title()} | {n['sentiment']} | {n['pub'].strftime('%Y-%m-%d %H:%M %Z')}")
else:
    st.info("No important news detected.")

st.subheader("📊 Sentiment Heatmap")
if all_news:
    df = pd.DataFrame(all_news)
    impact_counts = df.groupby(["impact", "sentiment"]).size().reset_index(name="count")
    fig = px.density_heatmap(
        impact_counts,
        x="impact",
        y="sentiment",
        z="count",
        text_auto=True,
        color_continuous_scale="Viridis",
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("No data available to plot heatmap.")

# --- Volatility Terminal ---
st.header("📉 Volatility Terminal")
with st.spinner("Calculating gold volatility..."):
    vol_data = fetch_gold_volatility()

if not vol_data.empty:
    st.line_chart(vol_data["Volatility"], height=300)
    latest_vol = vol_data["Volatility"].iloc[-1]
    st.metric("Current Gold Volatility (1D)", f"{latest_vol:.2%}")
else:
    st.error("Could not fetch gold volatility data.")
