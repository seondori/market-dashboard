import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import requests

# 1. 페이지 설정
st.set_page_config(page_title="Seondori Market Dashboard", layout="wide", page_icon="📊")

# ==========================================
# 🔑 [중요] 한국은행 API 키 입력란
# ==========================================
# https://ecos.bok.or.kr/ 에서 발급받은 키를 아래 따옴표 안에 넣으세요
BOK_API_KEY = "여기에_발급받은_키를_넣으세요" 

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
    .source-badge { font-size: 10px; background-color: #333; padding: 2px 6px; border-radius: 4px; color: #888; margin-left: 5px; }
    
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
# 🚀 한국은행(ECOS) API 통신 함수
# ==========================================
@st.cache_data(ttl=3600) # 1시간마다 갱신 (국채는 하루 1번 발표라 자주 할 필요 없음)
def get_bok_yield(stat_code, item_code, etf_ticker):
    # 1. 한국은행 API 시도
    try:
        # ECOS API URL (최근 5일치 요청)
        url = f"http://ecos.bok.or.kr/api/StatisticSearch/{BOK_API_KEY}/json/kr/1/5/{stat_code}/D/20230101/20301231/{item_code}/"
        res = requests.get(url, timeout=3)
        data = res.json()
        
        rows = data['StatisticSearch']['row']
        # 날짜순 정렬 보장 및 최근값 추출
        df_bok = pd.DataFrame(rows)
        df_bok['TIME'] = pd.to_datetime(df_bok['TIME'])
        df_bok = df_bok.sort_values('TIME')
        
        latest = float(df_bok.iloc[-1]['DATA_VALUE'])
        prev = float(df_bok.iloc[-2]['DATA_VALUE'])
        
        delta = latest - prev
        pct = (delta / prev) * 100 if prev != 0 else 0
        
        return {
            "current": latest, "delta": delta, "delta_pct": pct,
            "source": "한국은행(%)", "history": None # ECOS는 차트용으론 데이터가 적음
        }
    except:
        # 2. 실패 시 ETF 백업 (가격)
        try:
            df = yf.download(etf_ticker, period=p, interval=i, progress=False)
            if isinstance(df.columns, pd.MultiIndex): df = df.xs('Close', level=0, axis=1)
            series = df[etf_ticker] if etf_ticker in df.columns else df.iloc[:,0]
            series = series.dropna()
            
            latest = float(series.iloc[-1])
            prev = float(series.iloc[-2])
            delta = latest - prev
            pct = (delta / prev) * 100
            
            return {
                "current": latest, "delta": delta, "delta_pct": pct,
                "source": "ETF대체", "history": series
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
def draw_card(name, ticker, is_korea_bond=False, bok_codes=None, etf_code=None):
    # A. 한국 국채 (한국은행 or ETF)
    if is_korea_bond:
        # BOK_API_KEY가 없으면 바로 ETF로 감
        if "여기에" in BOK_API_KEY:
            data = None # 키 미입력 시 강제 실패 처리 -> ETF로 넘어감
        else:
            data = get_bok_yield(bok_codes[0], bok_codes[1], etf_code)
            
        # 1차 실패 시 ETF로 재시도 (함수 내부 로직이 아닌 외부 호출로 처리)
        if not data: 
             # 여기서는 ETF 함수를 따로 호출하거나 해야하는데, 
             # 편의상 get_bok_yield 함수 내부의 2단계 ETF 백업을 사용.
             # 단, 키가 없으면 바로 ETF 로직만 타도록 수정된 함수 필요하나 
             # 일단 위 함수가 2단계를 포함하므로 키가 틀리면 '실패' 후 ETF로 감
             pass

        # 만약 함수 내부 ETF도 실패했다면? -> 로딩 실패
        if not data:
             # ETF 전용으로 한 번 더 시도 (키 미입력 유저용)
             try:
                df = yf.download(etf_code, period=p, interval=i, progress=False)
                if isinstance(df.columns, pd.MultiIndex): df = df.xs('Close', level=0, axis=1)
                series = df.iloc[:,0].dropna()
                latest = float(series.iloc[-1])
                prev = float(series.iloc[-2])
                data = {
                    "current": latest, "delta": latest-prev, "delta_pct": 0,
                    "source": "ETF대체", "history": series
                }
             except:
                st.markdown(f"<div class='metric-card' style='border:1px solid #ff5252'><div class='metric-title'>{name}</div><div class='metric-value' style='color:#ff5252; font-size:16px'>로딩 실패</div></div>", unsafe_allow_html=True)
                return

        val, delta, pct, history = data['current'], data['delta'], data['delta_pct'], data['history']
        src = data['source']
        
        # 배지 색상
        badge_style = "color:#ff9800; background:#333;" if "ETF" in src else "color:#00e676; background:#003300;"
        name += f" <span class='source-badge' style='{badge_style}'>{src}</span>"

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

    # C. 화면 렌더링
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
    
    unit = "%" if (is_korea_bond and "ETF" not in src) or 'TNX' in ticker else ""
    
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
    st.error("데이터 로딩 중...")
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
            if "여기에" in BOK_API_KEY:
                st.warning("⚠️ 한국은행 API 키를 입력하면 '진짜 금리(%)'가 나옵니다. (지금은 ETF 가격 표시)")
            
            # 817Y002: 시장금리(일별) / 010200000: 국고채(3년) / 010210000: 국고채(10년)
            draw_card("한국 3년 국채", "KR3", is_korea_bond=True, bok_codes=["817Y002", "010200000"], etf_code="114260.KS")
            draw_card("한국 10년 국채", "KR10", is_korea_bond=True, bok_codes=["817Y002", "010210000"], etf_code="148070.KS")
            
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
