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
# 통합된 draw_card 함수 (이걸로 교체하세요)
def draw_card(name, ticker, is_korea_bond=False, etf_code=None):
    # A. 한국 국채 처리
    if is_korea_bond:
        data = get_korea_bond_yield(ticker, etf_code)
        if not data:
            st.error(f"{name} 로드 실패")
            return
        val, delta, pct = data['current'], data['delta'], data['delta_pct']
        unit = "%" if not data.get('is_fallback') else ""
    
    # B. 일반 지수/환율 처리
    else:
        try:
            # 주가지수 등은 사이드바에서 설정한 p(기간), i(간격) 사용
            # 전역 변수 p, i가 함수 밖에서 정의되어 있어야 합니다.
            df = yf.download(ticker, period=p, interval=i, progress=False)
            series = df['Close'].dropna()
            if series.empty: return
            val, prev = float(series.iloc[-1]), float(series.iloc[-2])
            if "JPYKRW" in ticker: val, prev = val*100, prev*100
            delta = val - prev
            pct = (delta / prev) * 100
            unit = ""
        except:
            st.error(f"{name} 로드 실패")
            return

    # 공통 렌더링
    color_class = "metric-delta-up" if delta >= 0 else "metric-delta-down"
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">{name}</div>
        <div class="metric-value">{val:,.2f}{unit}</div>
        <div class="{color_class}">{'▲' if delta >= 0 else '▼'} {abs(delta):.2f} ({pct:.2f}%)</div>
    </div>""", unsafe_allow_html=True)
# ==========================================
# 🖥️ 메인 화면 (순서 변경 및 차트 크기 확장)
# ==========================================
st.title(f"📊 Seondori Market Dashboard")

if raw_data is None:
    st.error("데이터 서버 연결 중...")
else:
    # 1. '트레이딩뷰'를 가장 앞으로 보내고 탭 생성
    tab_names = ["🔍 트레이딩뷰", "📈 주가지수 & 매크로", "💰 국채 금리", "💱 환율"]
    tabs = st.tabs(tab_names)
    
    # 🚀 [첫 번째 탭] 트레이딩뷰 (상세 분석)
    with tabs[0]:
        st.subheader("💡 실시간 상세 분석 (TradingView)")
        
        symbol_map = {
            "원/달러 환율": "FX_IDC:USDKRW",
            "코스피 지수": "KRX:KOSPI",
            "나스닥 100": "NASDAQ:QQQ",
            "S&P 500": "SPY",
            "비트코인": "BINANCE:BTCUSDT"
        }
        selected_name = st.selectbox("종목 선택", list(symbol_map.keys()), key="main_tv_select")
        target_symbol = symbol_map[selected_name]

        # 차트 가독성을 위해 높이를 800으로 확장했습니다.
        import streamlit.components.v1 as components
        
        tv_html = f"""
        <div style="height:800px;">
            <div id="tv_chart_main" style="height:100%;"></div>
            <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
            <script type="text/javascript">
            new TradingView.widget({{
                "autosize": true,
                "symbol": "{target_symbol}",
                "interval": "D",
                "timezone": "Asia/Seoul",
                "theme": "dark",
                "style": "1",
                "locale": "kr",
                "toolbar_bg": "#f1f3f6",
                "enable_publishing": false,
                "hide_side_toolbar": false,
                "allow_symbol_change": true,
                "details": true,  /* 우측 상세 정보창 활성화 */
                "studies": [
                    "RSI@tv-basicstudies"
                ],
                "container_id": "tv_chart_main"
            }});
            </script>
        </div>
        """
        components.html(tv_html, height=820) # 컨테이너 높이도 함께 조절

    # [두 번째 탭] 주가지수 & 매크로 (기존 tabs[0] 내용)
    with tabs[1]:
        c1, c2, c3, c4 = st.columns(4)
        with c1: draw_card("🇰🇷 코스피", "^KS11")
        with c2: draw_card("🇺🇸 다우존스", "^DJI")
        with c3: draw_card("🇺🇸 S&P 500", "^GSPC")
        with c4: draw_card("🇺🇸 나스닥", "^IXIC")
        
        c5, c6, c7, c8 = st.columns(4)
        with c5: draw_card("🛢️ WTI 원유", "CL=F")
        with c6: draw_card("👑 금", "GC=F")
        with c7: draw_card("😱 VIX", "^VIX")
        with c8: draw_card("🏭 구리", "HG=F")

    # [세 번째 탭] 국채 금리 (기존 tabs[1] 내용)
    with tabs[2]:
        col_kr, col_us = st.columns(2)
        with col_kr:
            st.markdown("##### 🇰🇷 한국 국채")
            draw_card("한국 3년 국채", "IRr_GOV03Y", is_korea_bond=True, etf_code="114260.KS")
            draw_card("한국 10년 국채", "IRr_GOV10Y", is_korea_bond=True, etf_code="148070.KS")
        with col_us:
            st.markdown("##### 🇺🇸 미국 국채")
            draw_card("미국 2년 금리 (선물)", "ZT=F")
            draw_card("미국 10년 금리 (지수)", "^TNX")

    # [네 번째 탭] 환율 (기존 tabs[2] 내용)
    with tabs[3]:
        c1, c2, c3, c4 = st.columns(4)
        with c1: draw_card("🇰🇷 원/달러", "KRW=X")
        with c2: draw_card("🇨🇳 원/위안", "CALC_CNYKRW")
        with c3: draw_card("🇯🇵 원/엔 (100엔)", "JPYKRW=X")
        with c4: draw_card("🌎 달러 인덱스", "DX-Y.NYB")

