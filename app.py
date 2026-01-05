import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import cloudscraper
import FinanceDataReader as fdr
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import requests
import streamlit.components.v1 as components

# 1. 페이지 설정
st.set_page_config(page_title="Seondori Market Dashboard", layout="wide", page_icon="📊")

# 2. 스타일 설정
st.markdown("""
    <style>
    .metric-card { 
        background-color: #1e1e1e; 
        padding: 15px; 
        border-radius: 10px; 
        border: 1px solid #333; 
        margin-bottom: 10px; 
    }
    .metric-title { font-size: 13px; color: #aaa; margin-bottom: 5px; }
    .metric-value { font-size: 24px; font-weight: bold; color: #fff; }
    .metric-delta-up { color: #ff5252; font-size: 13px; }   
    .metric-delta-down { color: #00e676; font-size: 13px; } 
    .fallback-badge { font-size: 10px; background-color: #333; padding: 2px 6px; border-radius: 4px; color: #ff9800; margin-left: 5px; }
    </style>
""", unsafe_allow_html=True)

# 3. 사이드바 및 설정
with st.sidebar:
    st.header("⚙️ 설정")
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
    period_option = st.selectbox("차트 기간", ("5일 (단기)", "1개월", "6개월", "1년"), index=0)

if "5일" in period_option: p, i = "5d", "30m"
elif "1개월" in period_option: p, i = "1mo", "1d"
elif "6개월" in period_option: p, i = "6mo", "1d"
else: p, i = "1y", "1d"

# --- 데이터 로딩 함수들 (기존과 동일) ---
@st.cache_data(ttl=600) 
def get_korea_bond_yield(naver_code, etf_ticker):
    try:
        fdr_symbol = "KR3YT=RR" if "03Y" in naver_code else "KR10YT=RR"
        df = fdr.DataReader(fdr_symbol, start=(datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d'))
        latest, prev = float(df['Close'].iloc[-1]), float(df['Close'].iloc[-2])
        return {"current": latest, "delta": latest-prev, "delta_pct": ((latest-prev)/prev)*100, "source_type": "FDR", "is_fallback": False}
    except: return None

@st.cache_data(ttl=60)
def get_yahoo_data(ticker_list, period, interval):
    return yf.download(ticker_list, period=period, interval=interval, group_by='ticker', threads=True, progress=False)

# 티커 리스트 준비
tickers_raw = ["^KS11", "^DJI", "^GSPC", "^IXIC", "CL=F", "GC=F", "^VIX", "HG=F", "KRW=X", "CNY=X", "JPYKRW=X", "DX-Y.NYB", "ZT=F", "^TNX"]
raw_data = get_yahoo_data(tickers_raw, p, i)

# 카드 그리기 함수
def draw_card(name, ticker):
    try:
        series = raw_data[ticker]['Close'].dropna()
        val, prev = float(series.iloc[-1]), float(series.iloc[-2])
        if "JPYKRW" in ticker: val, prev = val*100, prev*100
        delta = val - prev
        pct = (delta / prev) * 100
        color = '#ff5252' if delta >= 0 else '#00e676'
        st.markdown(f"""<div class="metric-card"><div class="metric-title">{name}</div><div class="metric-value">{val:,.2f}</div>
        <div class="{'metric-delta-up' if delta >= 0 else 'metric-delta-down'}">{'▲' if delta >= 0 else '▼'} {abs(delta):.2f} ({pct:.2f}%)</div></div>""", unsafe_allow_html=True)
    except: st.error(f"{name} 로드 실패")

# ==========================================
# 🖥️ 메인 화면 구성 (중요: 탭을 여기서 한 번만 정의!)
# ==========================================
st.title(f"📊 Seondori Market Dashboard ({period_option})")

# 탭을 4개로 생성합니다.
tabs = st.tabs(["📈 지수/매크로", "💰 국채 금리", "💱 환율", "🔍 기술적 분석(RSI)"])

with tabs[0]:
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_card("🇰🇷 코스피", "^KS11")
    with c2: draw_card("🇺🇸 나스닥", "^IXIC")
    with c3: draw_card("🛢️ 원유", "CL=F")
    with c4: draw_card("👑 금", "GC=F")

with tabs[1]:
    st.write("국채 금리 데이터 섹션")
    # (기존 국채 코드 삽입 가능)

with tabs[2]:
    c1, c2 = st.columns(2)
    with c1: draw_card("🇰🇷 원/달러", "KRW=X")
    with c2: draw_card("🌎 달러인덱스", "DX-Y.NYB")

# ✅ 4번째 탭: 질문하신 트레이딩뷰 + RSI 페이지
with tabs[3]:
    st.subheader("📈 실시간 상세 분석 (TradingView)")
    
    # 보고 싶은 종목 선택
    symbol_map = {
        "원/달러 환율": "FX_IDC:USDKRW",
        "코스피 지수": "KRX:KOSPI",
        "S&P 500": "SPY",
        "나스닥 100": "NASDAQ:QQQ",
        "비트코인": "BINANCE:BTCUSDT"
    }
    selected_name = st.selectbox("종목 선택", list(symbol_map.keys()))
    target_symbol = symbol_map[selected_name]

    # TradingView 위젯 (RSI 포함)
    # 
    tv_script = f"""
    <div style="height:600px;">
        <div id="tv-chart" style="height:100%;"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script type="text/javascript">
        new TradingView.widget({{
            "autosize": true, "symbol": "{target_symbol}", "interval": "D",
            "timezone": "Asia/Seoul", "theme": "dark", "style": "1",
            "locale": "kr", "toolbar_bg": "#f1f3f6", "enable_publishing": false,
            "hide_side_toolbar": false, "allow_symbol_change": true,
            "studies": ["RSI@tv-basicstudies"],
            "container_id": "tv-chart"
        }});
        </script>
    </div>
    """
    components.html(tv_script, height=620)
