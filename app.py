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

# 4. 데이터 로딩 (안정성 강화)
@st.cache_data(ttl=300) # 차단 방지를 위해 캐시 시간을 5분으로 늘림
def get_data(ticker, p, i):
    try:
        df = yf.download(ticker, period=p, interval=i, progress=False)
        if df.empty:
            return None
        # 최신 yfinance 버전의 MultiIndex 대응
        if isinstance(df.columns, pd.MultiIndex):
            return df['Close'][ticker]
        return df['Close']
    except Exception as e:
        return None

# 5. 카드 그리기 함수 (ValueError 방지)
def draw_card(name, ticker, p, i):
    series = get_data(ticker, p, i)
    
    # 데이터가 정상적으로 수집되었는지 엄격히 확인
    if series is not None and not series.empty and len(series) >= 2:
        try:
            # 값을 확실하게 float 숫자로 추출 (Series 방지)
            val = float(series.iloc[-1])
            prev = float(series.iloc[-2])
            
            delta = val - prev
            pct = (delta / prev) * 100 if prev != 0 else 0
            
            # 숫자 비교이므로 이제 에러가 나지 않음
            color_class = "metric-delta-up" if delta >= 0 else "metric-delta-down"
            arrow = "▲" if delta >= 0 else "▼"
            
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">{name}</div>
                <div class="metric-value">{val:,.2f}</div>
                <div class="{color_class}">{arrow} {abs(delta):.2f} ({pct:.2f}%)</div>
            </div>""", unsafe_allow_html=True)
        except Exception:
            st.warning(f"{name} 데이터 계산 오류")
    else:
        # 데이터가 없을 때 앱이 꺼지는 대신 표시할 내용
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">{name}</div>
            <div class="metric-value" style="color:gray; font-size:18px;">데이터 대기 중</div>
            <div style="color:gray; font-size:12px;">(Rate Limit/시장 휴장)</div>
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

