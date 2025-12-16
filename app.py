import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import cloudscraper
import FinanceDataReader as fdr
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

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
    
    @media (max-width: 640px) {
        div[data-testid="column"] {
            flex: 0 0 calc(50% - 10px) !important;
            min-width: calc(50% - 10px) !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

# 3. 사이드바
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
# 🚀 핵심 기술: 국채 금리 3중 확보 전략
# ==========================================
@st.cache_data(ttl=600) 
def get_korea_bond_yield(naver_code, etf_ticker):
    # 전략 1: FinanceDataReader (Investing.com 소스) - 가장 깔끔함
    try:
        # 네이버 코드를 FDR 심볼로 변환
        fdr_symbol = "KR3YT=RR" if "03Y" in naver_code else "KR10YT=RR"
        
        # 최근 1주일 데이터 가져오기
        start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        df = fdr.DataReader(fdr_symbol, start=start_date)
        
        if df is None or df.empty: raise Exception("Empty Data")
        
        latest = float(df['Close'].iloc[-1])
        prev = float(df['Close'].iloc[-2])
        delta = latest - prev
        pct = (delta / prev) * 100
        
        return {
            "current": latest, "delta": delta, "delta_pct": pct,
            "source_type": "FDR(%)", "is_fallback": False, "history": None
        }
    except:
        pass # 실패 시 전략 2로 이동

    # 전략 2: CloudScraper (네이버 크롤링) - 뚫어뻥 시도
    try:
        url = f"https://finance.naver.com/marketindex/interestDetail.naver?marketindexCd={naver_code}"
        scraper = cloudscraper.create_scraper(browser='chrome') # 브라우저 위장 강화
        res = scraper.get(url, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        value_str = soup.select_one('div.head_info > span.value').text
        value = float(value_str.replace(',', ''))
        
        change_str = soup.select_one('div.head_info > span.change').text
        change_val = float(change_str.replace(',', '').strip())
        
        direction = soup.select_one('div.head_info > span.blind').text
        if "하락" in direction: change_val = -change_val
        elif "보합" in direction: change_val = 0.0
            
        prev = value - change_val
        pct = (change_val / prev) * 100 if prev != 0 else 0
        
        return {
            "current": value, "delta": change_val, "delta_pct": pct,
            "source_type": "Naver(%)", "is_fallback": False, "history": None
        }
    except:
        pass # 실패 시 전략 3으로 이동

    # 전략 3: ETF 가격 (최후의 보루) - 이건 무조건 됨
    try:
        df = yf.download(etf_ticker, period=p, interval=i, progress=False)
        if isinstance(df.columns, pd.MultiIndex): df = df.xs('Close', level=0, axis=1)
        
        if etf_ticker in df.columns: series = df[etf_ticker]
        else: series = df.iloc[:, 0]
            
        series = series.dropna()
        if series.empty: return None
        
        latest = float(series.iloc[-1])
        prev = float(series.iloc[-2])
        delta = latest - prev
        pct = (delta / prev) * 100
        
        return {
            "current": latest, "delta": delta, "delta_pct": pct,
            "source_type": "ETF대체", "is_fallback": True, "history": series
        }
    except:
        return None

# ==========================================
# 🚀 야후 데이터 (나머지)
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
        if ticker != "CALC_CNYKRW": all_tickers_list.append(ticker)
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
        data = get_korea_bond_yield(ticker, etf_code)
        if not data:
            st.markdown(f"<div class='metric-card' style='border:1px solid #ff5252'><div class='metric-title'>{name}</div><div class='metric-value' style='color:#ff5252; font-size:16px'>로딩 실패</div></div>", unsafe_allow_html=True)
            return
        
        val, delta, pct, history = data['current'], data['delta'], data['delta_pct'], data['history']
        src_type = data['source_type']
        
        # 배지 표시 (성공한 소스 알려줌)
        badge_color = "#333" if data['is_fallback'] else "#003300"
        text_color = "#ff9800" if data['is_fallback'] else "#00e676"
        name += f" <span class='fallback-badge' style='background:{badge_color}; color:{text_color};'>{src_type}</span>"

    # B. 일반 지표
    else:
        try:
            if ticker == "CALC_CNYKRW":
                s1 = raw_data["KRW=X"]["Close"] if "KRW=X" in raw_data else raw_data.iloc[:,0] 
                s2 = raw_data["CNY=X"]["Close"] if "CNY=X" in raw_data else raw_data.iloc[:,0]
                series = s1 / s2
            else:
                if raw_data is None or ticker not in raw_data: return
                series = raw_data[ticker]['Close']
            
            series = series.dropna()
            if series.empty: return
            
            val = float(series.iloc[-1])
            prev = float(series.iloc[-2])
            
            if "JPYKRW" in ticker:
                val *= 100
                prev *= 100
                
            delta = val - prev
            pct = (delta / prev) * 100
            history = series
        except:
            return

    # C. 공통 렌더링
    color = '#ff5252' if delta >= 0 else '#00e676'
    
    if history is not None:
        y_min, y_max = history.min(), history.max()
        padding = (y_max - y_min) * 0.1 if y_max != y_min else 1.0
        fill_color = f"rgba{tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0,2,4)) + (0.1,)}"

        fig = go.Figure(data=go.Scatter(
            x=history.index, y=history.values, mode='lines',
            line=dict(color=color, width=2),
            fill='tozeroy', fillcolor=fill_color
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
    
    # 단위: % 붙이기 (국채 성공 or TNX)
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
st.title(f"📊 Seondori Market Dashboard ({period_option})")

if raw_data is None:
    st.error("데이터 서버 연결 중...")
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
            st.markdown("##### 🇰🇷 한국 국채")
            draw_card("한국 3년 국채", "IRr_GOV03Y", is_korea_bond=True, etf_code="114260.KS")
            draw_card("한국 10년 국채", "IRr_GOV10Y", is_korea_bond=True, etf_code="148070.KS")
            
        with col_us:
            st.markdown("##### 🇺🇸 미국 국채")
            draw_card("미국 2년 금리 (선물)", "ZT=F")
            draw_card("미국 10년 금리 (지수)", "^TNX")

    with tab3:
        c1, c2, c3, c4 = st.columns(4)
        with c1: draw_card("🇰🇷 원/달러", "KRW=X")
        with c2: draw_card("🇨🇳 원/위안", "CALC_CNYKRW")
        with c3: draw_card("🇯🇵 원/엔 (100엔)", "JPYKRW=X")
        with c4: draw_card("🌎 달러 인덱스", "DX-Y.NYB")