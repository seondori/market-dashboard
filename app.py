import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import requests

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
    .metric-delta-up { color: #00e676; font-size: 13px; }
    .metric-delta-down { color: #ff5252; font-size: 13px; }
    .fallback-badge { font-size: 10px; background-color: #333; padding: 2px 6px; border-radius: 4px; color: #ff9800; margin-left: 5px; }
    </style>
""", unsafe_allow_html=True)

# 3. 사이드바 설정
with st.sidebar:
    st.header("⚙️ 설정")
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
    period_option = st.selectbox("차트 기간", ("5일 (단기)", "1개월", "6개월", "1년"), index=0)

if "5일" in period_option: p, i = "5d", "30m"
elif "1개월" in period_option: p, i = "1mo", "1d"
elif "6개월" in period_option: p, i = "6mo", "1d"
else: p, i = "1y", "1d"

# ==========================================
# 🚀 핵심 기술: 네이버 모바일 API + ETF 자동 백업
# ==========================================
@st.cache_data(ttl=300) 
def get_korea_bond_smart(code, etf_ticker):
    # 1단계: 네이버 모바일 API 시도 (가볍고 차단 덜 됨)
    try:
        url = f"https://api.stock.naver.com/marketindex/match/{code}"
        headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'}
        
        res = requests.get(url, headers=headers, timeout=3)
        data = res.json()
        
        # 데이터 파싱
        value = float(data['closePrice'].replace(',', ''))
        change_val = float(data['compareToPreviousClosePrice'].replace(',', ''))
        pct = float(data['fluctuationRate'].replace(',', ''))
        
        # 하락 반영 (API는 절대값만 주는 경우가 있음)
        if data['fluctuationRate'] and '-' in data['fluctuationRate']:
             pass # 이미 음수면 패스
        elif change_val > 0 and value < (value + change_val): 
             change_val = -change_val # 로직상 보정 (네이버 API 특성)

        # 네이버 API는 전일대비 부호를 따로 줌 ('+' or '-')
        # 안전하게 계산: (오늘 - 어제)
        
        return {
            "current": value,
            "delta": change_val,
            "delta_pct": pct,
            "is_fallback": False,
            "history": None # API는 히스토리 안줌 -> 차트 없음
        }

    except Exception:
        # 2단계: 실패 시 ETF 데이터로 자동 전환 (무조건 성공함)
        try:
            stock = yf.Ticker(etf_ticker)
            df = stock.history(period=p, interval=i)
            
            if df.empty: return None
            
            latest = df['Close'].iloc[-1]
            prev = df['Close'].iloc[-2]
            delta = latest - prev
            pct = (delta / prev) * 100
            
            return {
                "current": latest,
                "delta": delta,
                "delta_pct": pct,
                "is_fallback": True, # 백업 모드 가동
                "history": df['Close']
            }
        except:
            return None

# ==========================================
# 🚀 야후 데이터 (나머지 지표용)
# ==========================================
tickers = {
    "indices": [("🇰🇷 코스피", "^KS11"), ("🇺🇸 다우존스", "^DJI"), ("🇺🇸 S&P 500", "^GSPC"), ("🇺🇸 나스닥", "^IXIC")],
    "macro": [("🛢️ WTI 원유", "CL=F"), ("👑 금", "GC=F"), ("😱 VIX", "^VIX"), ("🏭 구리", "HG=F")],
    "forex": [("🇰🇷/🇺🇸 원/달러", "KRW=X"), ("🇨🇳/🇺🇸 위안/달러", "CNY=X"), ("🇯🇵/🇰🇷 엔/원", "JPYKRW=X"), ("🌎 달러 인덱스", "DX-Y.NYB")],
    "us_bonds": [("🇺🇸 미국 2년 금리", "ZT=F"), ("🇺🇸 미국 10년 금리", "^TNX")]
}

all_tickers_list = []
for group in tickers.values():
    for name, ticker in group:
        all_tickers_list.append(ticker)

@st.cache_data(ttl=60)
def get_yahoo_data(ticker_list, period, interval):
    try:
        return yf.download(ticker_list, period=period, interval=interval, group_by='ticker', threads=True, progress=False)
    except:
        return None

raw_data = get_yahoo_data(all_tickers_list, p, i)

# ==========================================
# 📟 그리기 함수 (지능형)
# ==========================================
def draw_card(name, ticker, is_korea_bond=False, etf_code=None):
    # A. 한국 국채 처리
    if is_korea_bond:
        data = get_korea_bond_smart(ticker, etf_code)
        
        if not data:
            st.error(f"❌ {name}")
            return
            
        val = data['current']
        delta = data['delta']
        pct = data['delta_pct']
        
        # 백업 모드(ETF)일 때 처리
        if data['is_fallback']:
            name += " <span class='fallback-badge'>ETF대체</span>"
            # ETF는 가격이 내리면(파란불) -> 금리 상승(나쁜거 아님)
            # 하지만 직관성을 위해 그냥 가격 등락대로 표시
            history = data['history']
        else:
            name += " <span class='fallback-badge' style='color:#00e676; background:#003300;'>Naver실시간</span>"
            history = None # API는 차트 없음

    # B. 일반 지표 처리
    else:
        if ticker == "CALC_CNYKRW":
            try:
                s1 = raw_data["KRW=X"]["Close"]
                s2 = raw_data["CNY=X"]["Close"]
                series = s1 / s2
            except: return
        else:
            if ticker not in raw_data: return
            series = raw_data[ticker]['Close']
        
        series = series.dropna()
        if len(series) < 2: return
        
        val = float(series.iloc[-1])
        prev = float(series.iloc[-2])
        delta = val - prev
        pct = (delta / prev) * 100
        history = series

    # C. 공통: 차트 및 카드 렌더링
    color = '#00e676' if delta >= 0 else '#ff5252'
    
    if history is not None:
        y_min, y_max = history.min(), history.max()
        padding = (y_max - y_min) * 0.1 if y_max != y_min else 1.0
        
        fig = go.Figure(data=go.Scatter(
            x=history.index, y=history.values, mode='lines',
            line=dict(color=color, width=2),
            fill='tozeroy', fillcolor=f"rgba{tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0,2,4)) + (0.1,)}"
        ))
        fig.update_layout(
            margin=dict(l=0, r=0, t=5, b=5), height=50,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(visible=False), yaxis=dict(visible=False, range=[y_min-padding, y_max+padding]),
            showlegend=False, hovermode="x"
        )
    else:
        # 차트 데이터 없을 때 (API 성공 시) - 빈 차트
        fig = go.Figure()
        fig.update_layout(height=0, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(visible=False), yaxis=dict(visible=False))

    delta_sign = "▲" if delta > 0 else "▼"
    delta_color = "metric-delta-up" if delta >= 0 else "metric-delta-down"
    
    # 한국 국채 백업모드일 경우 단위 표시 변경
    unit = "%" if is_korea_bond and not data.get('is_fallback') else ""
    if 'TNX' in ticker: unit = "%"
    
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">{name}</div>
        <div class="metric-value">{val:,.2f}{unit}</div>
        <div class="{delta_color}">{delta_sign} {abs(delta):.2f} ({pct:.2f}%)</div>
    </div>""", unsafe_allow_html=True)
    
    if history is not None:
        st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})


# ==========================================
# 🖥️ 메인 화면
# ==========================================
st.title(f"📊 Seondori Market Dashboard ({period_option})")

if raw_data is None:
    st.error("서버 연결 확인 중...")
else:
    tab1, tab2, tab3 = st.tabs(["📈 주가지수 & 매크로", "💰 국채 금리", "💱 환율"])
    
    with tab1:
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

    with tab2:
        col_kr, col_us = st.columns(2)
        with col_kr:
            st.markdown("##### 🇰🇷 한국 국채 (Auto)")
            # 네이버 코드 + ETF 코드(백업용) 함께 전달
            draw_card("한국 3년 금리", "IRr_GOV03Y", is_korea_bond=True, etf_code="114260.KS")
            draw_card("한국 10년 금리", "IRr_GOV10Y", is_korea_bond=True, etf_code="148070.KS")
            
        with col_us:
            st.markdown("##### 🇺🇸 미국 국채")
            draw_card("미국 2년 금리 (선물)", "ZT=F")
            draw_card("미국 10년 금리 (지수)", "^TNX")

    with tab3:
        c1, c2, c3, c4 = st.columns(4)
        with c1: draw_card("🇰🇷/🇺🇸 원/달러", "KRW=X")
        with c2: draw_card("🇨🇳/🇰🇷 위안/원", "CALC_CNYKRW")
        with c3: draw_card("🇯🇵/🇰🇷 엔/원", "JPYKRW=X")
        with c4: draw_card("🌎 달러 인덱스", "DX-Y.NYB")