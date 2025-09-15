import streamlit as st
import requests
from xml.etree import ElementTree as ET
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import pytz
import plotly.express as px
import pandas as pd
from dateutil import parser

# -----------------------
# Page Config & Header
# -----------------------
st.set_page_config(page_title="GOLDEye Terminal", layout="wide")
st.markdown("<h1 style='text-align: center;'>GOLDEye Terminal</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-style: italic; color: orange;'>“From Headlines to Market Moves – Umer Farid”</p>", unsafe_allow_html=True)

# -----------------------
# Sidebar Controls
# -----------------------
st.sidebar.header("Controls")
slow_refresh = st.sidebar.number_input("News refresh interval (seconds)", 30, 600, 60)
st_autorefresh(interval=slow_refresh*1000, key="refresh")

tz = pytz.timezone("Asia/Karachi")
def _ts(): return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
def safe_domain(url): return urlparse(url).netloc.replace("www.","") if url else url

def parse_pub_date(pub_raw: str):
    """Parse publication date safely from RSS/Atom feeds."""
    if not pub_raw:
        return datetime.utcnow().replace(tzinfo=pytz.utc)
    try:
        dt = parser.parse(pub_raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=pytz.utc)
        return dt
    except:
        return datetime.utcnow().replace(tzinfo=pytz.utc)

# -----------------------
# Feeds
# -----------------------
feeds = {
    "market_feeds": {
        "tradingview": "https://www.tradingview.com/news/rss/",
        "fxstreet": "https://www.fxstreet.com/rss/news",
        "fxempire": "https://www.fxempire.com/news/feed",
    },
    "global_feeds": {
        "reuters": "https://feeds.reuters.com/reuters/topNews",
        "bbc": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml"
    },
    "jobs_feeds": {
        "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
        "anadolu": "https://www.aa.com.tr/en/rss/default?cat=economy"
    }
}

def _fetch_feed(name, url, max_items=50):
    items=[]
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            elements = root.findall('.//item')[:max_items]
            for it in elements:
                title = it.findtext('title') or ""
                desc = it.findtext('description') or ""
                pub = it.findtext('pubDate') or _ts()
                link = it.findtext('link') or ""
                text = title if title else desc
                if text:
                    items.append({"text":text,"source":safe_domain(url),"pub":pub,"link":link})
    except: 
        pass
    return items

@st.cache_data(ttl=slow_refresh, show_spinner=False)
def fetch_feeds(feeds_dict):
    all_items=[]
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_feed, n, u): n for n,u in feeds_dict.items()}
        for fut in as_completed(futures):
            all_items.extend(fut.result())
    return all_items

market_items = fetch_feeds(feeds["market_feeds"])
global_items = fetch_feeds(feeds["global_feeds"])
jobs_items = fetch_feeds(feeds["jobs_feeds"])

# -----------------------
# Currencies
# -----------------------
CURRENCIES = ["USD","GOLD","EUR","JPY","AUD","GBP","NZD","CAD","CHF"]

# -----------------------
# Impact Analysis
# -----------------------
def analyze_impact_short(headline: str):
    h = headline.lower()
    impact = {c: {"value":0,"news":[]} for c in CURRENCIES}

    if any(k in h for k in ["nfp","payroll","employment","jobless","claims","jolts","ism"]):
        if any(k in h for k in ["strong","beat","better","surge","rise","increase","positive","higher"]):
            impact["USD"]["value"] += 2; impact["USD"]["news"].append(headline)
            impact["GOLD"]["value"] -= 1; impact["GOLD"]["news"].append(headline)
        if any(k in h for k in ["weak","miss","fall","drop","decline","worse","below"]):
            impact["USD"]["value"] -= 2; impact["USD"]["news"].append(headline)
            impact["GOLD"]["value"] += 1; impact["GOLD"]["news"].append(headline)

    if any(k in h for k in ["inflation","rate hike","interest rate","fed","ecb","central bank"]):
        for c in ["USD","EUR"]:
            impact[c]["value"] += 1; impact[c]["news"].append(headline)
        impact["GOLD"]["value"] -= 1; impact["GOLD"]["news"].append(headline)

    if any(k in h for k in ["war","attack","conflict","terror","sanction"]):
        for c in ["USD","JPY","GOLD"]:
            impact[c]["value"] += 1; impact[c]["news"].append(headline)
        for c in ["EUR","AUD"]:
            impact[c]["value"] -= 1; impact[c]["news"].append(headline)

    return impact

def analyze_trader_impact(headline: str):
    h = headline.lower()
    impact = {c: {"value":0,"news":[]} for c in CURRENCIES}
    if "usd" in h:
        impact["USD"]["value"] += 1; impact["USD"]["news"].append(headline)
        impact["GOLD"]["value"] -= 1; impact["GOLD"]["news"].append(headline)
    if "gold" in h:
        impact["GOLD"]["value"] += 1; impact["GOLD"]["news"].append(headline)
        impact["USD"]["value"] -= 1; impact["USD"]["news"].append(headline)
    return impact

# -----------------------
# Aggregate impacts
# -----------------------
combined_impact = {c: {"value":0,"news":[]} for c in CURRENCIES}
trader_impact = {c: {"value":0,"news":[]} for c in CURRENCIES}
all_news = market_items + global_items + jobs_items

for news in all_news:
    cur = analyze_impact_short(news["text"])
    tra = analyze_trader_impact(news["text"])
    for c in CURRENCIES:
        if cur[c]["value"] != 0:
            combined_impact[c]["value"] += cur[c]["value"]
            combined_impact[c]["news"].append(news["text"])
        if tra[c]["value"] != 0:
            trader_impact[c]["value"] += tra[c]["value"]
            trader_impact[c]["news"].append(news["text"])

# -----------------------
# Terminal CSS Styles
# -----------------------
st.markdown("""
<style>
.terminal {
    background-color: #111;
    color: #0f0;
    font-family: monospace;
    font-size: 14px;
    padding: 12px;
    border-radius: 8px;
    border: 1px solid #444;
    max-height: 500px;
    overflow-y: auto;
    box-shadow: 0px 0px 10px #000 inset;
}
.small-terminal {
    background-color: #000;
    color: #0f0;
    font-family: monospace;
    font-size: 13px;
    padding: 10px;
    border-radius: 6px;
    border: 1px solid #333;
    max-height: 350px;
    overflow-y: auto;
    box-shadow: 0px 0px 5px #000 inset;
}
</style>
""", unsafe_allow_html=True)

# -----------------------
# Breaking News Terminal
# -----------------------
st.markdown("### 🔔 Breaking News Alerts")
breaking_keywords = ["fed","cpi","nfp","payroll","inflation","rate hike","interest","ecb","bank","war","conflict","attack","oil","gold","usd"]
breaking_news = [n for n in all_news if any(k in n["text"].lower() for k in breaking_keywords)]
if breaking_news:
    top_breaking = breaking_news[:5]
    lines = []
    for it in top_breaking:
        dt = parse_pub_date(it["pub"])
        local_dt = dt.astimezone(tz)
        time_str = local_dt.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(
            f"<span style='color:red;'>⚡ {it['text']}</span> "
            f"<span style='color:yellow;'>({time_str})</span> "
            f"<a href='{it['link']}' target='_blank'>[{safe_domain(it['link'])}]</a>"
        )
    st.markdown("<div class='terminal'>"+"<br>".join(lines)+"</div>", unsafe_allow_html=True)
else:
    st.info("No breaking news right now.")

# -----------------------
# Important Trading Headlines Terminal
# -----------------------
st.markdown("### 📌 Important Trading Headlines (With Impacted Pairs)")
trading_keywords = ["usd","gold","oil","eur","gbp","jpy","cpi","pmi","nfp","payroll","inflation",
                    "interest rate","ecb","fed","rate hike","fomc","recession","gdp","central bank"]

important_news = []
for n in all_news:
    if any(k in n["text"].lower() for k in trading_keywords):
        cur = analyze_impact_short(n["text"])
        tra = analyze_trader_impact(n["text"])
        impacted = {}
        for c in CURRENCIES:
            net = cur[c]["value"] + tra[c]["value"]
            if net != 0:
                impacted[c] = net
        if impacted:
            n["impacted"] = impacted
            important_news.append(n)

if important_news:
    lines = []
    for it in important_news[:40]:
        dt = parse_pub_date(it["pub"])
        local_dt = dt.astimezone(tz)
        time_str = local_dt.strftime("%Y-%m-%d %H:%M:%S")
        tags = []
        for c, val in it["impacted"].items():
            if val > 0:
                tags.append(f"<span style='color:lime; font-weight:bold;'>[{c} ↑]</span>")
            elif val < 0:
                tags.append(f"<span style='color:red; font-weight:bold;'>[{c} ↓]</span>")
        tags_str = " ".join(tags)
        lines.append(
            f"<span style='color:cyan;'>[{time_str}]</span> "
            f"<a href='{it['link']}' target='_blank'>{it['text']}</a> "
            f"{tags_str} <span style='color:gray;'>({safe_domain(it['link'])})</span>"
        )
    st.markdown("<div class='small-terminal'>"+"<br>".join(lines)+"</div>", unsafe_allow_html=True)
else:
    st.info("No important trading headlines impacting pairs were found.")

# -----------------------
# Overall Impact Terminal
# -----------------------
st.markdown("### 📊 Overall Impact")
def format_dual_impact(current, trader):
    val1, val2 = current.get("value",0), trader.get("value",0)
    color1 = "lime" if val1>0 else "red" if val1<0 else "gray"
    color2 = "lime" if val2>0 else "red" if val2<0 else "gray"
    news1 = "<br>".join(f"• {n}" for n in current.get("news",[])[:2])
    news2 = "<br>".join(f"• {n}" for n in trader.get("news",[])[:2])
    return f"<b style='color:{color1}'>Current: {val1}</b><br>{news1}<br><b style='color:{color2}'>Trader: {val2}</b><br>{news2}"

lines = [f"<span style='color:cyan;'>{c}</span><br>{format_dual_impact(combined_impact[c], trader_impact[c])}" for c in CURRENCIES]
st.markdown("<div class='terminal'>"+"<br><br>".join(lines)+"</div>", unsafe_allow_html=True)

# -----------------------
# Market Heatmap Terminal
# -----------------------
st.markdown("### 🌍 Market Heatmap (News Impact)")
heatmap_data = {c: combined_impact[c]["value"] for c in CURRENCIES}
df = pd.DataFrame(list(heatmap_data.items()), columns=["Asset","Impact"])
df = df.pivot_table(index=["Asset"], values="Impact")
fig = px.imshow(df,
                color_continuous_scale="RdYlGn",
                aspect="auto",
                title="News Impact Heatmap",
                labels=dict(color="Impact"))
st.plotly_chart(fig, use_container_width=True)

# -----------------------
# Volatility Terminal
# -----------------------
st.markdown("### ⚡ Volatility Index")
sample_vol = {"EURUSD": 0.9, "GBPJPY": 1.5, "XAUUSD": 2.1}
lines = [f"<span>{s}: {v}% volatility</span>" for s,v in sample_vol.items()]
st.markdown("<div class='small-terminal'>"+"<br>".join(lines)+"</div>", unsafe_allow_html=True)

# -----------------------
# News Sentiment Terminal
# -----------------------
st.markdown("### 📰 News Sentiment Analysis")
def news_sentiment(text):
    positive_words = ["beat","strong","rise","gain","bullish","surge","higher","growth"]
    negative_words = ["miss","fall","weak","loss","bearish","drop","lower","decline"]
    t = text.lower()
    if any(w in t for w in positive_words): return "🟢 Positive"
    elif any(w in t for w in negative_words): return "🔴 Negative"
    return "⚪ Neutral"

sentiment_samples = all_news[:10]
lines = [f"{news_sentiment(it['text'])} – {it['text']}" for it in sentiment_samples]
st.markdown("<div class='small-terminal'>"+"<br>".join(lines)+"</div>", unsafe_allow_html=True)
# -----------------------
# News Terminals (Market / Global / Jobs)
# -----------------------
r1c1, r1c2, r1c3 = st.columns(3)

with r1c1:
    st.markdown("### Market / Forex News")
    lines = []
    for it in market_items[:50]:
        dt = parse_pub_date(it["pub"])
        local_dt = dt.astimezone(tz)
        time_str = local_dt.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{time_str}] <a href='{it['link']}' target='_blank'>{it['text']}</a>")
    st.markdown("<div class='small-terminal'>" + "<br>".join(lines) + "</div>", unsafe_allow_html=True)

with r1c2:
    st.markdown("### Global / Geo Events")
    lines = []
    for it in global_items[:50]:
        dt = parse_pub_date(it["pub"])
        local_dt = dt.astimezone(tz)
        time_str = local_dt.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{time_str}] <a href='{it['link']}' target='_blank'>{it['text']}</a>")
    st.markdown("<div class='small-terminal'>" + "<br>".join(lines) + "</div>", unsafe_allow_html=True)

with r1c3:
    st.markdown("### Economic / Jobs Data")
    lines = []
    for it in jobs_items[:50]:
        dt = parse_pub_date(it["pub"])
        local_dt = dt.astimezone(tz)
        time_str = local_dt.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{time_str}] <a href='{it['link']}' target='_blank'>{it['text']}</a>")
    st.markdown("<div class='small-terminal'>" + "<br>".join(lines) + "</div>", unsafe_allow_html=True)
