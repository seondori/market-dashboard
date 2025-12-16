import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd

# 1. 페이지 설정
st.set_page_config(page_title="Seondori Market Dashboard", layout="wide", page_icon="📊")

# 2. 스타일 설정 (모바일 2열 + 탭 스타일)
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
    .metric-value { font-size: 22px; font-weight: bold; color: #fff; }
    .metric-delta-up { color: #00e676; font-size: 13px; }
    .metric-delta-down { color: #ff5252; font-size: 13px; }
    
    /* 모바일 최적화 (2열 배치) */
    @media (max-width: 640px) {
        div[data-testid="column"] {
            flex: 0 0 calc(50% - 10px) !important;
            min-width: calc(50% - 10px) !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

# 3. 사이드바 & 설정
with st.sidebar:
    st.header("⚙️ 대시보드 설정")
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
    period_option = st.selectbox("차트 기간", ("5일 (단기 흐름)", "1개월", "6개월", "1년"), index=0)

# 기간 매핑
if "5일" in period_option: p, i = "5d", "30m"
elif "1개월" in period_option: p, i = "1mo", "1d"
elif "6개월" in period_option: p, i = "6mo", "1d"
else: p, i = "1y", "1d"

# 4. 티커 정의 (그룹별 분류)
# 주의: 한국 국채 % 데이터는 무료 소스 부재로 ETF 유지
tickers = {
    "indices": [
        ("🇰🇷 코스피", "^KS11"), 
        ("🇺🇸 다우존스", "^DJI"), 
        ("🇺🇸 S&P 500", "^GSPC"), 
        ("🇺🇸 나스닥", "^IXIC")
    ],
    "bonds_short": [
        ("🇺🇸 미국 2년 금리", "ZT=F"), # 2년 국채 선물
        ("🇰🇷 한국 3년 국채(ETF)", "114260.KS") # 가격(Yield 아님)
    ],
    "bonds_long": [
        ("🇺🇸 미국 10년 금리", "^TNX"), # 실제 금리 지수
        ("🇰🇷 한국 10년 국채(ETF)", "148070.KS") # 가격
    ],
    "forex": [
        ("🇰🇷/🇺🇸 원/달러", "KRW=X"),
        ("🇨🇳/🇺🇸 위안/달러", "CNY=X"), # 계산용 (화면엔 원/위안 표시)
        ("🇯🇵/🇰🇷 엔/원", "JPYKRW=X"),
        ("🌎 달러 인덱스", "DX-Y.NYB")
    ],
    "macro": [
        ("🛢️ WTI 원유 (물가)", "CL=F"),
        ("👑 금 (안전 자산)", "GC=F"),
        ("😱 VIX (공포 지수)", "^VIX"),
        ("🏭 구리 (제조업)", "HG=F") # 구리는 제조업 선행지표 역할
    ]
}

# 모든 티커 추출
all_tickers_list = []
for group in tickers.values():
    for name, ticker in group:
        all_tickers_list.append(ticker)

# 5. 데이터 다운로드
@st.cache_data(ttl=60)
def get_all_data(ticker_list, period, interval):
    try:
        data = yf.download(ticker_list, period=period, interval=interval, group_by='ticker', threads=True, progress=False)
        return data
    except Exception:
        return None

raw_data = get_all_data(all_tickers_list, p, i)

# 6. 차트 및 데이터 가공 함수
def create_card(ticker, name, df_all):
    try:
        # 1. 데이터 추출
        if ticker == "CALC_CNYKRW": # 위안/원 계산 로직
            try:
                # 원/달러 ÷ 위안/달러 = 원/위안
                krw = df_all["KRW=X"]["Close"]
                cny = df_all["CNY=X"]["Close"]
                series = krw / cny
            except:
                return None
        else:
            if ticker not in df_all: return None
            series = df_all[ticker]['Close']
        
        # 2. 전처리
        series = series.dropna()
        if len(series) < 2: return None
        
        # 3. 값 계산
        latest = float(series.iloc[-1])
        prev = float(series.iloc[-2])
        delta = latest - prev
        delta_pct = (delta / prev) * 100
        
        # 4. 차트 그리기
        y_min, y_max = series.min(), series.max()
        padding = (y_max - y_min) * 0.1 if y_max != y_min else 1.0
        
        color = '#00e676' if delta >= 0 else '#ff5252'
        
        fig = go.Figure(data=go.Scatter(
            x=series.index, y=series.values, mode='lines',
            line=dict(color=color, width=2),
            fill='tozeroy', fillcolor=f"rgba{tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0,2,4)) + (0.1,)}"
        ))
        fig.update_layout(
            margin=dict(l=0, r=0, t=5, b=5), height=50,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(visible=False),
            yaxis=dict(visible=False, range=[y_min - padding, y_max + padding]),
            showlegend=False, hovermode="x"
        )
        
        # 5. 카드 렌더링
        delta_sign = "▲" if delta > 0 else "▼"
        delta_color = "metric-delta-up" if delta >= 0 else "metric-delta-down"
        
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">{name}</div>
            <div class="metric-value">{latest:,.2f}</div>
            <div class="{delta_color}">{delta_sign} {abs(delta):.2f} ({delta_pct:.2f}%)</div>
        </div>""", unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})
        
        return True
    except Exception:
        return False

# === 메인 화면 출력 ===
st.title(f"📊 Market Dashboard ({period_option})")

if raw_data is None:
    st.error("데이터 로딩 실패. 잠시 후 새로고침 해주세요.")
else:
    # 탭으로 구분하여 보여주기
    tab1, tab2, tab3 = st.tabs(["📈 주가지수 & 거시경제", "💰 국채 금리 (기간별)", "💱 환율"])
    
    with tab1:
        st.subheader("글로벌 주요 지수")
        cols = st.columns(4)
        for idx, (name, ticker) in enumerate(tickers["indices"]):
            with cols[idx]: create_card(ticker, name, raw_data)
            
        st.subheader("경기 선행 지표 (제조업/물가 대리)")
        cols2 = st.columns(4)
        for idx, (name, ticker) in enumerate(tickers["macro"]):
            with cols2[idx]: create_card(ticker, name, raw_data)

    with tab2:
        col_short, col_long = st.columns(2)
        with col_short:
            st.markdown("##### ⏳ 단기 채권/금리 (2~3년)")
            for name, ticker in tickers["bonds_short"]:
                create_card(ticker, name, raw_data)
        with col_long:
            st.markdown("##### ⏳ 장기 채권/금리 (10년)")
            for name, ticker in tickers["bonds_long"]:
                create_card(ticker, name, raw_data)
                
    with tab3:
        st.subheader("주요 통화 환율")
        cols3 = st.columns(4)
        
        # 1. 원달러
        with cols3[0]: create_card("KRW=X", "🇰🇷/🇺🇸 원/달러", raw_data)
        # 2. 위안/원 (계산된 지표)
        with cols3[1]: create_card("CALC_CNYKRW", "🇨🇳/🇰🇷 위안/원 (직접계산)", raw_data)
        # 3. 엔/원
        with cols3[2]: create_card("JPYKRW=X", "🇯🇵/🇰🇷 엔/원", raw_data)
        # 4. 달러인덱스
        with cols3[3]: create_card("DX-Y.NYB", "🌎 달러 인덱스", raw_data)