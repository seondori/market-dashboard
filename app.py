import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import cloudscraper
import FinanceDataReader as fdr
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import requests
import re

# 1. 페이지 설정
st.set_page_config(page_title="Seondori.com", layout="wide", page_icon="📊")

# 2. 스타일 설정 (상승=빨강, 하락=초록)
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
# 🚀 가격 파싱 함수
# ==========================================
def parse_price_data(price_text):
    """
    텍스트에서 CPU/RAM 가격 정보를 파싱합니다.
    예: "8-12.i9 10900KF - 170.000원" -> {"name": "i9 10900KF", "price": 170000}
    """
    prices = {}
    
    # 정규표현식으로 가격 정보 추출
    # 패턴: 번호. 제품명 - 가격원
    pattern = r'[\d\-\.]+\s*([A-Za-z0-9\s\-]+?)\s*-\s*([\d,\.]+)\s*원'
    
    for line in price_text.split('\n'):
        match = re.search(pattern, line)
        if match:
            product_name = match.group(1).strip()
            price_str = match.group(2).replace(',', '').replace('.', '')
            
            try:
                price = int(price_str)
                
                # 카테고리 분류
                category = "기타"
                if 'DDR5' in line or 'D5' in line:
                    category = "DDR5 RAM"
                elif 'DDR4' in line or 'D4' in line:
                    category = "DDR4 RAM"
                elif 'DDR3' in line or 'D3' in line:
                    category = "DDR3 RAM"
                elif any(cpu in line for cpu in ['i3', 'i5', 'i7', 'i9', 'G3', 'G4', 'G5', 'G6']):
                    if '세대' in line or '레이크' in line or '샌디' in line or '아이비' in line or '하스웰' in line:
                        category = "Intel CPU"
                elif 'R3' in line or 'R5' in line or 'R7' in line or 'R9' in line:
                    category = "AMD CPU"
                elif 'GTX' in line or 'RTX' in line or 'RX' in line:
                    category = "그래픽카드"
                elif 'SSD' in line or 'M.2' in line:
                    category = "SSD"
                elif 'HDD' in line or '하드' in line or 'TB' in line or 'TB' in product_name:
                    category = "HDD"
                elif any(board in line for board in ['H61', 'H67', 'B75', 'Z77', 'H81', 'B85', 'Z97', 'B150', 'B250', 'B360', 'Z370', 'Z390', 'B460', 'Z490', 'B560', 'Z590', 'B660', 'Z690', 'B760', 'Z790', 'A320', 'B350', 'B450', 'B550', 'B650', 'X670']):
                    category = "메인보드"
                
                if category not in prices:
                    prices[category] = []
                
                prices[category].append({
                    'product': product_name,
                    'price': price,
                    'price_formatted': f"{price:,}원"
                })
            except ValueError:
                continue
    
    return prices

# ==========================================
# 🚀 핵심 기술: 국채 금리 4중 확보 전략 (개선)
# ==========================================
@st.cache_data(ttl=600) 
def get_korea_bond_yield(naver_code, etf_ticker):
    # 전략 1: FinanceDataReader (Investing.com 소스)
    try:
        fdr_symbol = "KR3YT=RR" if "03Y" in naver_code else "KR10YT=RR"
        start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        df = fdr.DataReader(fdr_symbol, start=start_date)
        
        if df is None or df.empty: raise Exception("Empty Data")
        
        latest = float(df['Close'].iloc[-1])
        prev = float(df['Close'].iloc[-2])
        delta = latest - prev
        pct = (delta / prev) * 100
        
        return {
            "current": latest, "delta": delta, "delta_pct": pct,
            "source_type": "FDR", "is_fallback": False, "history": None
        }
    except:
        pass

    # 전략 2: 한국은행 API (공식 데이터)
    try:
        # 한국은행 경제통계시스템 (인증키 불필요한 공개 데이터)
        stat_code = "817Y002" if "03Y" in naver_code else "817Y004"  # 국고채 3년/10년
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr/1/10/{stat_code}/D/"
        
        # 최근 날짜 2개 요청
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
        url += f"{start_date}/{end_date}/"
        
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if 'StatisticSearch' in data and 'row' in data['StatisticSearch']:
            rows = data['StatisticSearch']['row']
            if len(rows) >= 2:
                latest = float(rows[-1]['DATA_VALUE'])
                prev = float(rows[-2]['DATA_VALUE'])
                delta = latest - prev
                pct = (delta / prev) * 100
                
                return {
                    "current": latest, "delta": delta, "delta_pct": pct,
                    "source_type": "BOK", "is_fallback": False, "history": None
                }
    except:
        pass

    # 전략 3: CloudScraper (네이버 크롤링)
    try:
        url = f"https://finance.naver.com/marketindex/interestDetail.naver?marketindexCd={naver_code}"
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        res = scraper.get(url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
        })
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
            "source_type": "Naver", "is_fallback": False, "history": None
        }
    except:
        pass

    # 전략 4: ETF 가격 그대로 표시 (금리 변환 포기)
    try:
        df = yf.download(etf_ticker, period="5d", interval="1d", progress=False)
        
        # MultiIndex 처리
        if isinstance(df.columns, pd.MultiIndex): 
            try:
                if etf_ticker in df.columns.get_level_values(1):
                    df = df.xs(etf_ticker, level=1, axis=1)
                else:
                    df = df.xs('Close', level=0, axis=1)
            except:
                df = df.iloc[:, 0].to_frame()

        if 'Close' in df.columns: series = df['Close']
        else: series = df.iloc[:, 0]
            
        series = series.dropna()
        if series.empty: return None
        
        latest = float(series.iloc[-1])
        prev = float(series.iloc[-2])
        delta = latest - prev
        pct = (delta / prev) * 100
        
        # ETF는 가격으로 표시 (금리 아님)
        return {
            "current": latest,
            "delta": delta,
            "delta_pct": pct,
            "source_type": "ETF대체",
            "is_fallback": True,  # 가격 단위
            "history": None
        }
    except Exception as e:
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
        
        val, delta, pct = data['current'], data['delta'], data['delta_pct']
        src_type = data['source_type']
        
        # 배지 표시
        badge_colors = {
            "FDR": ("#004d00", "#00ff00"),
            "BOK": ("#003d5c", "#00bfff"), 
            "Naver": ("#4d3800", "#ffa500"),
            "ETF대체": ("#4d0000", "#ff6b6b")
        }
        badge_bg, badge_fg = badge_colors.get(src_type, ("#333", "#ff9800"))
        
        # ETF 대체일 경우 단위 표시
        if data.get('is_fallback'):
            name += f" <span class='fallback-badge' style='background:{badge_bg}; color:{badge_fg};'>{src_type} (가격)</span>"
        else:
            name += f" <span class='fallback-badge' style='background:{badge_bg}; color:{badge_fg};'>{src_type}</span>"
        history = None

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
    delta_sign = "▲" if delta > 0 else "▼"
    delta_color = "metric-delta-up" if delta >= 0 else "metric-delta-down"
    
    # 단위: 금리 소스일 때만 % (ETF 폴백 제외)
    unit = "%" if (is_korea_bond and not data.get('is_fallback')) or 'TNX' in ticker else ""
    
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">{name}</div>
        <div class="metric-value">{val:,.2f}{unit}</div>
        <div class="{delta_color}">{delta_sign} {abs(delta):.2f} ({pct:.2f}%)</div>
    </div>""", unsafe_allow_html=True)
    
    # 차트는 히스토리가 있을 때만 표시
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
        st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})


# ==========================================
# 🖥️ 메인 화면 (수정본)
# ==========================================
st.title(f"📊 Seondori Market Dashboard ({period_option})")

if raw_data is None:
    st.error("데이터 서버 연결 중...")
else:
    # 탭 생성 (가격 정보 탭 추가)
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔍 Trading View", "📈 주가지수", "💰 국채 금리", "💱 환율", "💻 부품 시세"])
    
    with tab1:
        st.subheader("💡 TradingView 실시간 차트 (RSI 포함)")
        
        # 사용자가 심볼을 직접 고를 수 있게 구성
        symbol_map = {
            "🇰🇷 원/달러 환율": "FX_IDC:USDKRW",
            "🇰🇷 코스피 지수": "KRX:KOSPI",
            "🇺🇸 나스닥 100": "NASDAQ:QQQ",
            "🇺🇸 S&P 500": "SPY",
            "👑 금 선물": "TVC:GOLD",
            "🛢️ WTI 원유": "TVC:USOIL"
        }

        selected_name = st.selectbox("분석할 자산을 선택하세요", list(symbol_map.keys()))
        target_symbol = symbol_map[selected_name]
        
        # 앞서 정의한 함수 호출 (반드시 위쪽에 정의되어 있어야 함)
        import streamlit.components.v1 as components
        
        tradingview_script = f"""
        <div class="tradingview-widget-container" style="height:600px;">
          <div id="tradingview_chart" style="height:100%;"></div>
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
            "studies": [
              "RSI@tv-basicstudies"
            ],
            "container_id": "tradingview_chart"
          }});
          </script>
        </div>
        """
        components.html(tradingview_script, height=620)

        
    with tab2:
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

    with tab3:
        col_kr, col_us = st.columns(2)
        with col_kr:
            st.markdown("##### 🇰🇷 한국 국채")
            draw_card("한국 3년 국채", "IRr_GOV03Y", is_korea_bond=True, etf_code="114260.KS")
            draw_card("한국 10년 국채", "IRr_GOV10Y", is_korea_bond=True, etf_code="148070.KS")
        with col_us:
            st.markdown("##### 🇺🇸 미국 국채")
            draw_card("미국 2년 금리 (선물)", "ZT=F")
            draw_card("미국 10년 금리 (지수)", "^TNX")

    with tab4:
        c1, c2, c3, c4 = st.columns(4)
        with c1: draw_card("🇰🇷 원/달러", "KRW=X")
        with c2: draw_card("🇨🇳 원/위안", "CALC_CNYKRW")
        with c3: draw_card("🇯🇵 원/엔 (100엔)", "JPYKRW=X")
        with c4: draw_card("🌎 달러 인덱스", "DX-Y.NYB")

    with tab5:
        st.subheader("💻 PC 부품 매입 시세")
        st.info("💡 아래에 가격 정보를 붙여넣으면 자동으로 파싱되어 카테고리별로 정리됩니다.")
        
        # 텍스트 입력 영역
        price_input = st.text_area(
            "가격 정보 입력 (예: 8-12.i9 10900KF - 170.000원)",
            height=200,
            placeholder="여기에 가격 정보를 붙여넣으세요..."
        )
        
        if price_input:
            # 가격 데이터 파싱
            parsed_prices = parse_price_data(price_input)
            
            if parsed_prices:
                # 카테고리별로 표시
                categories_order = [
                    "Intel CPU", "AMD CPU", "그래픽카드", 
                    "DDR5 RAM", "DDR4 RAM", "DDR3 RAM",
                    "메인보드", "SSD", "HDD", "기타"
                ]
                
                for category in categories_order:
                    if category in parsed_prices and parsed_prices[category]:
                        with st.expander(f"📦 {category} ({len(parsed_prices[category])}개)", expanded=True):
                            # 데이터프레임으로 변환
                            df = pd.DataFrame(parsed_prices[category])
                            df = df.sort_values('price', ascending=False)
                            
                            # 표 표시
                            st.dataframe(
                                df[['product', 'price_formatted']].rename(columns={
                                    'product': '제품명',
                                    'price_formatted': '가격'
                                }),
                                hide_index=True,
                                use_container_width=True
                            )
                            
                            # 간단한 통계
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("최고가", f"{df['price'].max():,}원")
                            with col2:
                                st.metric("최저가", f"{df['price'].min():,}원")
                            with col3:
                                st.metric("평균가", f"{int(df['price'].mean()):,}원")
            else:
                st.warning("가격 정보를 찾을 수 없습니다. 형식을 확인해주세요.")
        else:
            # 샘플 데이터 표시
            st.markdown("""
            ### 사용 방법
            1. 위의 텍스트 영역에 가격 정보를 붙여넣으세요
            2. 자동으로 파싱되어 카테고리별로 정리됩니다
            3. 각 카테고리를 펼쳐서 상세 정보를 확인하세요
            
            #### 입력 형식 예시:
            ```
            8-12.i9 10900KF - 170.000원
            14-1.삼성 16G PC4 25600 [3200mhz] - 138.000원
            25-14.RTX 2060 - 120.000원
            ```
            """)
