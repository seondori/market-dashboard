import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import requests
from bs4 import BeautifulSoup

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
# 🚀 핵심 기술 1: 네이버 금융 크롤링 (차단 우회 적용)
# ==========================================
@st.cache_data(ttl=300) 
def get_naver_bond(code):
    try:
        # [중요] 가짜 신분증(User-Agent) 만들기
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        url = f"https://finance.naver.com/marketindex/interestDetail.naver?marketindexCd={code}"
        
        # 헤더를 포함해서 요청 (이제 네이버가 안 막음)
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 데이터 추출
        value = soup.select_one('div.head_info > span.value').text
        value = float(value.replace(',', ''))
        
        change_val = soup.select_one('div.head_info > span.change').text
        change_val = float(change_val.replace(',', '').strip())
        
        # 방향 확인 (상승/하락/보합)
        direction_element = soup.select_one('div.head_info > span.blind')
        direction = direction_element.text if direction_element else ""
        
        if "하락" in direction:
            change_val = -change_val
        elif "보합" in direction:
            change_val = 0.0
        
        # 변화율 계산
        prev = value - change_val
        pct = (change_val / prev) * 100 if prev != 0 else 0
        
        return {
            "current": value,
            "delta": change_val,
            "delta_pct": pct
        }
    except Exception as e:
        # 에러가 나면 None 반환 (화면에 X 표시됨)
        # st.error(f"디버깅용 에러 메시지: {e}") # 필요시 주석 해제해서 확인
        return None

# ==========================================
# 🚀 핵심 기술 2: 야후 파이낸스
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
# 📟 카드 그리기 함수
# ==========================================
def draw_card(name, ticker, is_naver=False):
    # 1. 네이버 데이터 처리
    if is_naver:
        data = get_naver_bond(ticker)
        if not data:
            # 실패 시 UI
            st.markdown(f"""
            <div class="metric-card" style="border-color: #ff5252;">
                <div class="metric-title">{name}</div>
                <div class="metric-value" style="font-size:16px; color:#ff5252;">데이터 로딩 실패</div>
            </div>""", unsafe_allow_html=True)
            return
        
        val = data['current']
        delta = data['delta']
        pct = data['delta_pct']
        
        # 차트 없음 (공백 처리)
        fig = go.Figure()
        fig.update_layout(height=0, margin=dict(l=0,r=0,t=0,b=0), xaxis=dict(visible=False), yaxis=dict(visible=False))
        
    # 2. 야후 데이터 처리
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
        
        color = '#00e676' if delta >= 0 else '#ff5252'
        y_min, y_max = series.min(), series.max()
        padding = (y_max - y_min) * 0.1 if y_max != y_min else 1.0
        
        fig = go.Figure(data=go.Scatter(
            x=series.index, y=series.values, mode='lines',
            line=dict(color=color, width=2),
            fill='tozeroy', fillcolor=f"rgba{tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0,2,4)) + (0.1,)}"
        ))
        fig.update_layout(
            margin=dict(l=0, r=0, t=5, b=5), height=50,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(visible=False), yaxis=dict(visible=False, range=[y_min-padding, y_max+padding]),
            showlegend=False, hovermode="x"
        )

    delta_sign = "▲" if delta > 0 else "▼"
    delta_color = "metric-delta-up" if delta >= 0 else "metric-delta-down"
    
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">{name}</div>
        <div class="metric-value">{val:,.2f}{'%' if is_naver or 'TNX' in ticker else ''}</div>
        <div class="{delta_color}">{delta_sign} {abs(delta):.2f} ({pct:.2f}%)</div>
    </div>""", unsafe_allow_html=True)
    
    if not is_naver:
        st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})


# ==========================================
# 🖥️ 메인 화면
# ==========================================
st.title(f"📊 Seondori Market Dashboard ({period_option})")

if raw_data is None:
    st.error("데이터 로딩 중...")
else:
    tab1, tab2, tab3 = st.tabs(["📈 주가지수 & 매크로", "💰 국채 금리 (%)", "💱 환율"])
    
    with tab1:
        st.caption("글로벌 지수 및 경기 선행 지표")
        c1, c2, c3, c4 = st.columns(4)
        with c1: draw_card("🇰🇷 코스피", "^KS11")
        with c2: draw_card("🇺🇸 다우존스", "^DJI")
        with c3: draw_card("🇺🇸 S&P 500", "^GSPC")
        with c4: draw_card("🇺🇸 나스닥", "^IXIC")
        
        c5, c6, c7, c8 = st.columns(4)
        with c5: draw_card("🛢️ WTI 원유", "CL=F")
        with c6: draw_card("👑 금", "GC=F")
        with c7: draw_card("😱 VIX (공포)", "^VIX")
        with c8: draw_card("🏭 구리 (제조업)", "HG=F")

    with tab2:
        st.caption("⚠️ 한국 국채는 네이버 금융 실시간 금리(%)를 크롤링합니다.")
        col_kr, col_us = st.columns(2)
        
        with col_kr:
            st.markdown("##### 🇰🇷 한국 국채 (Naver)")
            draw_card("한국 3년 국채 금리", "IRr_GOV03Y", is_naver=True)
            draw_card("한국 10년 국채 금리", "IRr_GOV10Y", is_naver=True)
            
        with col_us:
            st.markdown("##### 🇺🇸 미국 국채 (Yahoo)")
            draw_card("미국 2년 금리 (선물)", "ZT=F")
            draw_card("미국 10년 금리 (지수)", "^TNX")

    with tab3:
        c1, c2, c3, c4 = st.columns(4)
        with c1: draw_card("🇰🇷/🇺🇸 원/달러", "KRW=X")
        with c2: draw_card("🇨🇳/🇰🇷 위안/원", "CALC_CNYKRW")
        with c3: draw_card("🇯🇵/🇰🇷 엔/원", "JPYKRW=X")
        with c4: draw_card("🌎 달러 인덱스", "DX-Y.NYB")