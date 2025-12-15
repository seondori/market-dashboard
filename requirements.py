import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd

# 1. 페이지 설정
st.set_page_config(page_title="글로벌 마켓 워치", layout="wide", page_icon="⚡")

# 2. 스타일 설정
st.markdown("""
    <style>
    .metric-card { background-color: #1e1e1e; padding: 15px; border-radius: 10px; border: 1px solid #333; margin-bottom: 10px; }
    .metric-title { font-size: 14px; color: #aaa; margin-bottom: 5px; }
    .metric-value { font-size: 24px; font-weight: bold; color: #fff; }
    .metric-delta-up { color: #00e676; font-size: 14px; }
    .metric-delta-down { color: #ff5252; font-size: 14px; }
    .error-text { font-size: 12px; color: #ff5252; }
    </style>
""", unsafe_allow_html=True)

# 3. 사이드바 설정
with st.sidebar:
    st.header("⚙️ 설정")
    if st.button("데이터 새로고침"):
        st.cache_data.clear()
    period_option = st.selectbox("기간 선택", ("5일 (단기)", "1개월", "6개월", "1년"), index=0)

# 기간/간격 매핑
if "5일" in period_option: p, i = "5d", "30m"
elif "1개월" in period_option: p, i = "1mo", "1d"
elif "6개월" in period_option: p, i = "6mo", "1d"
else: p, i = "1y", "1d"

# 4. 티커 리스트 정의 (이름, 티커)
indicators_map = [
    [("🇰🇷 3년 국채(ETF)", "114260.KS"), ("🇰🇷 10년 국채(ETF)", "148070.KS"), ("🇺🇸 2년 국채(선물)", "ZT=F"), ("🇺🇸 10년 금리", "^TNX")],
    [("🇰🇷/🇺🇸 원달러", "KRW=X"), ("🌎 달러 인덱스", "DX-Y.NYB"), ("🇪🇺/🇰🇷 유로/원", "EURKRW=X"), ("🇨🇳/🇺🇸 달러/위안", "CNY=X")],
    [("🇰🇷 코스피", "^KS11"), ("🇺🇸 S&P 500", "^GSPC"), ("🇺🇸 나스닥", "^IXIC"), ("🇯🇵/🇰🇷 엔/원", "JPYKRW=X")]
]

# 모든 티커를 한 리스트로 모으기 (한 방에 요청하기 위함)
all_tickers = []
for row in indicators_map:
    for name, ticker in row:
        all_tickers.append(ticker)

# 5. 데이터 가져오기 (배치 다운로드 방식)
@st.cache_data(ttl=60)
def get_batch_data(tickers, period, interval):
    try:
        # 그룹 다운로드 (threads=True로 병렬 처리) -> 속도 빠름, 에러 적음
        data = yf.download(tickers, period=period, interval=interval, group_by='ticker', threads=True, progress=False)
        return data
    except Exception as e:
        return None

# 데이터 로딩
raw_data = get_batch_data(all_tickers, p, i)

# 6. 개별 데이터 추출 및 차트 그리기
def process_and_draw(ticker, name, full_data):
    try:
        # 데이터프레임에서 해당 티커만 꺼내기
        if full_data is None or full_data.empty:
            return None

        # MultiIndex 처리 (yfinance 버전에 따라 구조가 다를 수 있음)
        try:
            df = full_data[ticker]
        except KeyError:
            return None # 티커 이름이 안 맞으면 패스

        # 종가(Close)만 가져오기
        if 'Close' in df.columns:
            series = df['Close']
        else:
            series = df.iloc[:, 0] # 첫번째 컬럼 강제 사용

        # 결측치 제거
        series = series.dropna()
        if len(series) < 2:
            return None

        # 값 계산
        latest = float(series.iloc[-1]) # float로 강제 변환 (중요!)
        prev = float(series.iloc[-2])
        delta = latest - prev
        delta_pct = (delta / prev) * 100
        
        # 차트 그리기
        y_min, y_max = series.min(), series.max()
        padding = (y_max - y_min) * 0.1 if y_max != y_min else 1.0
        
        color = '#00e676' if delta >= 0 else '#ff5252'
        
        fig = go.Figure(data=go.Scatter(
            x=series.index, y=series.values, mode='lines',
            line=dict(color=color, width=2),
            fill='tozeroy', fillcolor=f"rgba{tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0,2,4)) + (0.1,)}"
        ))
        fig.update_layout(
            margin=dict(l=0, r=0, t=5, b=5), height=60,
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(visible=False),
            yaxis=dict(visible=False, range=[y_min - padding, y_max + padding]),
            showlegend=False, hovermode="x"
        )
        
        return {
            'current': latest,
            'delta': delta,
            'delta_pct': delta_pct,
            'fig': fig
        }
    except Exception as e:
        return {'error': str(e)}

# === 메인 화면 출력 ===
st.title(f"⚡ 글로벌 마켓 워치 ({period_option})")

if raw_data is None:
    st.error("데이터 서버 연결 실패. 잠시 후 다시 시도해주세요.")
else:
    for row in indicators_map:
        cols = st.columns(4)
        for idx, (name, ticker) in enumerate(row):
            with cols[idx]:
                result = process_and_draw(ticker, name, raw_data)
                
                if result and 'error' not in result:
                    delta_sign = "▲" if result['delta'] > 0 else "▼"
                    delta_color = "metric-delta-up" if result['delta'] >= 0 else "metric-delta-down"
                    
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">{name}</div>
                        <div class="metric-value">{result['current']:,.2f}</div>
                        <div class="{delta_color}">{delta_sign} {abs(result['delta']):.2f} ({result['delta_pct']:.2f}%)</div>
                    </div>""", unsafe_allow_html=True)
                    st.plotly_chart(result['fig'], use_container_width=True, config={'staticPlot': True})
                
                elif result and 'error' in result:
                    st.error(f"⚠️ {name}")
                else:
                    st.warning(f"⏳ {name} (로딩중)")