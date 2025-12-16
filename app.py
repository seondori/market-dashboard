import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup

# 1. Page Configuration
st.set_page_config(page_title="Seondori Market Dashboard", layout="wide", page_icon="📊")

# 2. Style Configuration (Red=Up, Green=Down for Korea)
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
    .metric-delta-up { color: #ff5252; font-size: 13px; }   /* Up=Red */
    .metric-delta-down { color: #00e676; font-size: 13px; } /* Down=Green */
    .fallback-badge { font-size: 10px; background-color: #333; padding: 2px 6px; border-radius: 4px; color: #ff9800; margin-left: 5px; }
    
    /* Mobile Optimization (2 Columns) */
    @media (max-width: 640px) {
        div[data-testid="column"] {
            flex: 0 0 calc(50% - 10px) !important;
            min-width: calc(50% - 10px) !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

# 3. Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
    period_option = st.selectbox("Chart Period", ("5 Days", "1 Month", "6 Months", "1 Year"), index=0)

if "5" in period_option: p, i = "5d", "30m"
elif "1 Month" in period_option: p, i = "1mo", "1d"
elif "6 Months" in period_option: p, i = "6mo", "1d"
else: p, i = "1y", "1d"

# ==========================================
# 🚀 Core Tech: Bypassing Naver Block with CloudScraper
# ==========================================
@st.cache_data(ttl=600) 
def get_korea_bond_yield(code, etf_ticker):
    # Try 1: Scrape Naver Finance using CloudScraper (Returns %)
    try:
        url = f"https://finance.naver.com/marketindex/interestDetail.naver?marketindexCd={code}"
        
        # Use cloudscraper to mimic a real browser
        scraper = cloudscraper.create_scraper() 
        res = scraper.get(url)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Extract Data
        value_str = soup.select_one('div.head_info > span.value').text
        value = float(value_str.replace(',', ''))
        
        change_str = soup.select_one('div.head_info > span.change').text
        change_val = float(change_str.replace(',', '').strip())
        
        # Check Direction
        direction = soup.select_one('div.head_info > span.blind').text
        if "하락" in direction:
            change_val = -change_val
        elif "보합" in direction:
            change_val = 0.0
            
        # Calc Pct Change
        prev = value - change_val
        pct = (change_val / prev) * 100 if prev != 0 else 0
        
        return {
            "current": value,
            "delta": change_val,
            "delta_pct": pct,
            "is_fallback": False,
            "history": None
        }

    except Exception:
        # Try 2: Fallback to ETF Price (Fixed lower error)
        try:
            # Use yf.download to prevent 'lower' error
            df = yf.download(etf_ticker, period=p, interval=i, progress=False)
            
            # Flatten MultiIndex if present
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs('Close', level=0, axis=1)
            
            # Select Ticker
            if etf_ticker in df.columns:
                series = df[etf_ticker]
            else:
                series = df.iloc[:, 0]
                
            series = series.dropna()
            if series.empty: return None
            
            latest = float(series.iloc[-1])
            prev = float(series.iloc[-2])
            delta = latest - prev
            pct = (delta / prev) * 100
            
            return {
                "current": latest,
                "delta": delta,
                "delta_pct": pct,
                "is_fallback": True, # Backup Mode
                "history": series
            }
        except Exception:
            return None

# ==========================================
# 🚀 Yahoo Data (Other Indicators)
# ==========================================
tickers = {
    "indices": [("🇰🇷 코스피", "^KS11"), ("🇺🇸 다우존스", "^DJI"), ("🇺🇸 S&P 500", "^GSPC"), ("🇺🇸 나스닥", "^IXIC")],
    "macro": [("🛢️ WTI 원유", "CL=F"), ("👑 금", "GC=F"), ("😱 VIX", "^VIX"), ("🏭 구리", "HG=F")],
    "forex": [("🇰🇷 원/달러", "KRW=X"), ("🇨🇳 원/위안", "CALC_CNYKRW"), ("🇯🇵 원/엔 (100엔)", "JPYKRW=X"), ("🌎 달러 인덱스", "DX-Y.NYB")],
    "us_bonds": [("🇺🇸 미국 2년 금리", "ZT=F"), ("🇺🇸 미국 10년 금리", "^TNX")]
}

# Create Ticker List
all_tickers_list = []
for group in tickers.values():
    for name, ticker in group:
        if ticker != "CALC_CNYKRW":
            all_tickers_list.append(ticker)
all_tickers_list.append("CNY=X") # For Yuan Calculation

# Download Data (using yf.download)
@st.cache_data(ttl=60)
def get_yahoo_data(ticker_list, period, interval):
    try:
        data = yf.download(ticker_list, period=period, interval=interval, group_by='ticker', threads=True, progress=False)
        return data
    except:
        return None

raw_data = get_yahoo_data(list(set(all_tickers_list)), p, i)

# ==========================================
# 📟 Draw Card Function
# ==========================================
def draw_card(name, ticker, is_korea_bond=False, etf_code=None):
    # A. Korea Bond Logic
    if is_korea_bond:
        data = get_korea_bond_yield(ticker, etf_code)
        if not data:
            st.markdown(f"<div class='metric-card' style='border:1px solid #ff5252'><div class='metric-title'>{name}</div><div class='metric-value' style='color:#ff5252; font-size:16px'>Loading Failed</div></div>", unsafe_allow_html=True)
            return
            
        val, delta, pct, history = data['current'], data['delta'], data['delta_pct'], data['history']
        
        # Badge
        if data['is_fallback']: name += " <span class='fallback-badge'>ETF(Backup)</span>"
        else: name += " <span class='fallback-badge' style='color:#00e676; background:#003300;'>Naver(%)</span>"

    # B. General Indicators
    else:
        try:
            if ticker == "CALC_CNYKRW":
                # Won/Yuan = (Won/USD) / (Yuan/USD)
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
            
            # Yen Adjustment (100 Yen)
            if "JPYKRW" in ticker:
                val *= 100
                prev *= 100
                
            delta = val - prev
            pct = (delta / prev) * 100
            history = series
        except:
            return

    # C. Display (Chart & Card)
    color = '#ff5252' if delta >= 0 else '#00e676' # Up=Red, Down=Green
    
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
    
    # Add % unit for Yields
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
# 🖥️ Main Display
# ==========================================
st.title(f"📊 Seondori Market Dashboard ({period_option})")

if raw_data is None:
    st.error("Connecting to server... (Please wait)")
else:
    tab1, tab2, tab3 = st.tabs(["📈 Indices & Macro", "💰 Bond Yields", "💱 Forex"])
    
    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        with c1: draw_card("🇰🇷 Kospi", "^KS11")
        with c2: draw_card("🇺🇸 Dow Jones", "^DJI")
        with c3: draw_card("🇺🇸 S&P 500", "^GSPC")
        with c4: draw_card("🇺🇸 Nasdaq", "^IXIC")
        
        c5, c6, c7, c8 = st.columns(4)
        with c5: draw_card("🛢️ WTI Oil", "CL=F")
        with c6: draw_card("👑 Gold", "GC=F")
        with c7: draw_card("😱 VIX", "^VIX")
        with c8: draw_card("🏭 Copper", "HG=F")

    with tab2:
        col_kr, col_us = st.columns(2)
        with col_kr:
            st.markdown("##### 🇰🇷 Korea Bonds")
            # Passes both Naver Code and Backup ETF Code
            draw_card("Korea 3Y Bond", "IRr_GOV03Y", is_korea_bond=True, etf_code="114260.KS")
            draw_card("Korea 10Y Bond", "IRr_GOV10Y", is_korea_bond=True, etf_code="148070.KS")
            
        with col_us:
            st.markdown("##### 🇺🇸 US Bonds")
            draw_card("US 2Y Yield (Futures)", "ZT=F")
            draw_card("US 10Y Yield", "^TNX")

    with tab3:
        c1, c2, c3, c4 = st.columns(4)
        with c1: draw_card("🇰🇷 Won/Dollar", "KRW=X")
        with c2: draw_card("🇨🇳 Won/Yuan", "CALC_CNYKRW")
        with c3: draw_card("🇯🇵 Won/Yen (100)", "JPYKRW=X")
        with c4: draw_card("🌎 DXY", "DX-Y.NYB")