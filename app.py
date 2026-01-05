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
        background-color: #1e1e1e; padding: 15px; border-radius: 10px; border: 1px solid #333; margin-bottom: 10px; 
    }
    .metric-title { font-size: 13px; color: #aaa; margin-bottom: 5px; }
    .metric-value { font-size: 24px; font-weight: bold; color: #fff; }
    .metric-delta-up { color: #ff5252; font-size: 13px; }   
    .metric-delta-down { color: #00e676; font-size: 13px; } 
    </style>
""", unsafe_allow_html=True)

# 3. 사이드바 설정
with st.sidebar:
    st.header("⚙️ 설정")
    if st.button("🔄 새로고침"): st.cache_data.clear()
    period_option = st.selectbox("차트 기간", ("5일 (단기)", "1개월", "6개월", "1년"), index=0)

# 4. 데이터 로딩 (간소화 버전)
@st.cache_data(ttl=60)
def get_data(ticker, p, i):
    try:
        df = yf.download(ticker, period=p, interval=i, progress=False)
        return df['Close']
    except: return None

# 5. 카드 그리기 함수
def draw_card(name, ticker, p, i):
    series = get_data(ticker, p, i)
    if series is not None and not series.empty:
        val, prev = series.iloc[-1], series.iloc[-2]
        delta = val - prev
        pct = (delta / prev) * 100
        color_class = "metric-delta-up" if delta >= 0 else "metric-delta-down"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">{name}</div>
            <div class="metric-value">{val:,.2f}</div>
            <div class="{color_class}">{'▲' if delta >= 0 else '▼'} {abs(delta):.2f} ({pct:.2f}%)</div>
        </div>""", unsafe_allow_html=True)

# ==========================================
# 🖥️ 메인 화면 구성 (핵심: 탭을 여기서 한 번만 선언!)
# ==========================================
st.title(f"📊 Seondori Market Dashboard")

# 탭 이름을 리스트로 정의 (여기서 4번째 탭을 확실히 넣습니다)
tab_titles = ["📈 지수/매크로", "💰 국채 금리", "💱 환율", "🔍 기술적 분석"]
tabs = st.tabs(tab_titles)

p, i = ("5d", "30m") if "5일" in period_option else ("1mo", "1d")

# 1번 탭
with tabs[0]:
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_card("🇰🇷 코스피", "^KS11", p, i)
    with c2: draw_card("🇺🇸 다우존스", "^DJI", p, i)
    with c3: draw_card("🇺🇸 S&P 500", "^GSPC", p, i)
    with c4: draw_card("🇺🇸 나스닥", "^IXIC", p, i)

# 2번 탭
with tabs[1]:
    st.info("국채 금리 데이터 섹션 (FinanceDataReader 등을 활용해 구성하세요)")

# 3번 탭
with tabs[2]:
    c1, c2 = st.columns(2)
    with c1: draw_card("🇰🇷 원/달러", "KRW=X", p, i)
    with c2: draw_card("🌎 달러 인덱스", "DX-Y.NYB", p, i)

# 4번 탭: 사용자가 원하셨던 TradingView + RSI
with tabs[3]:
    st.subheader("💡 TradingView 실시간 차트 (RSI 포함)")
    
    # 선택 박스
    sb = {
        "원/달러 환율": "FX_IDC:USDKRW",
        "코스피 지수": "KRX:KOSPI",
        "나스닥 100": "NASDAQ:QQQ",
        "비트코인": "BINANCE:BTCUSDT"
    }
    target = st.selectbox("종목 선택", list(sb.keys()), key="unique_tv_key")
    symbol = sb[target]

    # TradingView 위젯 HTML
    tv_html = f"""
    <div style="height:600px;">
        <div id="tv_chart_container" style="height:100%;"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script type="text/javascript">
        new TradingView.widget({{
            "autosize": true, "symbol": "{symbol}", "interval": "D",
            "timezone": "Asia/Seoul", "theme": "dark", "style": "1",
            "locale": "kr", "enable_publishing": false,
            "allow_symbol_change": true,
            "studies": ["RSI@tv-basicstudies"],
            "container_id": "tv_chart_container"
        }});
        </script>
    </div>
    """
    components.html(tv_html, height=620)
