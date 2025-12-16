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
    period_option = st.selectbox("차트 기간", ("5일", "1개월", "6개월", "1년"), index=0)

if "5일" in period_option: p, i = "5d", "30m"
elif "1개월" in period_option: p, i = "1mo", "1d"
elif "6개월" in period_option: p, i = "6mo", "1d"
else: p, i = "1y", "1d"

# ==========================================
# 🚀 핵심 기술: 네이버 모바일 API + ETF 자동 백업
# ==========================================
@st.cache_data(ttl=300) 
def get_korea_bond_smart(code, etf_ticker):
    try:
        url = f"https://api.stock.naver.com/marketindex/match/{code}"
        headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'}
        
        res = requests.get(url, headers=headers, timeout=3)
        data = res.json()
        
        value = float(data['closePrice'].replace(',', ''))
        change_val = float(data['compareToPreviousClosePrice'].replace(',', ''))
        pct = float(data['fluctuationRate'].replace(',', ''))
        
        # 하락 반영
        if data['fluctuationRate'] and '-' in data['fluctuationRate']:
             pass 
        elif change_val > 0 and value < (value + change_val): 
             change_val = -change_val

        return {
            "current": value,
            "delta": change_val,
            "delta_pct": pct,
            "is_fallback": False,
            "history": None
        }

    except Exception:
        # ETF 백업
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
                "is_fallback": True,
                "history": df['Close']
            }
        except:
            return None

# ==========================================
# 🚀 야후 데이터
# ==========================================
tickers = {
    "indices": [("🇰🇷 코스피", "^KS11"), ("🇺🇸 다우존스", "^DJI"), ("🇺🇸 S&P 500", "^GSPC"), ("🇺🇸 나스닥", "^IXIC")],
    "macro": [("🛢️ WTI 원유", "CL=F"), ("👑 금", "GC=F"), ("😱 VIX", "^VIX"), ("🏭 구리", "HG=F")],
    "forex": [("🇰🇷 원/달러", "KRW=X"), ("🇨🇳 원/위안", "CALC_CNYKRW"), ("🇯🇵 원/엔 (100엔)", "JPYKRW=X"), ("🌎 달러 인덱스", "DX-Y.NYB")],
    "us_bonds": [("🇺🇸 미국 2년 금리", "ZT=F"), ("🇺🇸 미국 10년 금리", "^TNX")]
}

all_tickers_list = []
for group in tickers.values():
    for name, ticker in group:
        if ticker != "CALC_CNYKRW":
            all_tickers_list.append(ticker)
# 위안화 계산을 위해 USD/CNY 추가
all_tickers_list.append("CNY=X")

@st.cache_data(ttl=60)
def get_yahoo_data(ticker_list, period, interval):
    try:
        return yf.download(ticker_list, period=period, interval=interval, group_by='ticker', threads=True, progress=False)
    except:
        return None

raw_data = get_yahoo_data(list(set(all_tickers_list)), p, i)

# ==========================================
# 📟 그리기 함수
# ==========================================
def draw_card(name, ticker, is_korea_bond=False, etf_code=None):
    # A. 한국 국채
    if is_korea_bond:
        data = get_korea_bond_smart(ticker, etf_code)
        if not data:
            st.error(f"❌ {name}")
            return
        val, delta, pct, history = data['current'], data['delta'], data['delta_pct'], data['history']
        
        if data['is_fallback']: name += " <span class='fallback-badge'>ETF대체</span>"
        else: name += " <span class='fallback-badge' style='color:#00e676; background:#003300;'>Naver</span>"

    # B. 일반 지표
    else:
        # [수정됨] 원/위안 계산 (KRW/USD 나누기 CNY/USD)
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
        
        # [수정됨] 엔화 100엔 단위 변환
        if "JPYKRW" in ticker:
            val *= 100
            prev *= 100
            
        delta = val - prev
        pct = (delta / prev) * 100
        history = series

    # C. 공통 렌더링
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
        fig = go.Figure()
        fig.update_layout(height=0, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(visible=False), yaxis=dict(visible=False))

    delta_sign = "▲" if delta > 0 else "▼"
    delta_color = "metric-delta-up" if delta >= 0 else "metric-delta-down"
    
    unit = "%" if (is_korea_bond and not data.get('is_fallback')) or 'TNX' in ticker else ""
    
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
st.title(f"📊 Market Dashboard by_seondori ({period_option})")

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
            draw_card("한국 3년 금리", "IRr_GOV03Y", is_korea_bond=True, etf_code="114260.KS")
            draw_card("한국 10년 금리", "IRr_GOV10Y", is_korea_bond=True, etf_code="148070.KS")
            
        with col_us:
            st.markdown("##### 🇺🇸 미국 국채")
            draw_card("미국 2년 금리 (선물)", "ZT=F")
            draw_card("미국 10년 금리 (지수)", "^TNX")

    with tab3:
        c1, c2, c3, c4 = st.columns(4)
        with c1: draw_card("🇰🇷/🇺🇸 원/달러", "KRW=X")
        # [수정] 원/위안으로 표기 변경
        with c2: draw_card("🇨🇳/🇰🇷 원/위안", "CALC_CNYKRW")
        # [수정] 원/엔 (100엔 기준)으로 표기 및 계산 적용
        with c3: draw_card("🇯🇵/🇰🇷 원/엔 (100엔)", "JPYKRW=X")
        with c4: draw_card("🌎 달러 인덱스", "DX-Y.NYB")