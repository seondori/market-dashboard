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
import json
import os

# 1. 페이지 설정
st.set_page_config(page_title="Seondori.com", layout="wide", page_icon="📊")

# 버전 정보
VERSION = "2.1.0"  # 날짜 표시 개선, 백업/복원 기능 추가

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
    
    /* 모바일 최적화 */
    @media (max-width: 640px) {
        div[data-testid="column"] {
            flex: 0 0 calc(50% - 10px) !important;
            min-width: calc(50% - 10px) !important;
        }
        
        /* 모바일에서 메트릭 카드 크기 조정 */
        .metric-value {
            font-size: 18px !important;
        }
        
        .metric-title {
            font-size: 11px !important;
        }
        
        /* 모바일에서 Plotly 차트 높이 자동 조정 */
        .js-plotly-plot {
            width: 100% !important;
        }
        
        /* 모바일에서 expander 패딩 조정 */
        div[data-testid="stExpander"] {
            margin-bottom: 10px;
        }
        
        /* 모바일에서 텍스트 입력창 크기 조정 */
        textarea {
            font-size: 14px !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

# 3. 사이드바
with st.sidebar:
    st.header("⚙️ 설정")
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
    period_option = st.selectbox("차트 기간", ("5일", "1개월", "6개월", "1년"), index=0)
    
    # 버전 정보 표시
    st.markdown("---")
    st.caption(f"📌 Version {VERSION}")
    
    # 관리자 인증
    st.markdown("---")
    st.markdown("### 🔐 관리자 전용")
    
    if 'admin_authenticated' not in st.session_state:
        st.session_state.admin_authenticated = False
    
    if not st.session_state.admin_authenticated:
        admin_password = st.text_input("비밀번호", type="password", key="admin_pw")
        if st.button("로그인"):
            if admin_password == "admin123":
                st.session_state.admin_authenticated = True
                st.success("✅ 관리자 로그인 성공!")
                st.rerun()
            else:
                st.error("❌ 비밀번호가 틀렸습니다.")
    else:
        st.success("✅ 관리자 모드")
        if st.button("로그아웃"):
            st.session_state.admin_authenticated = False
            st.rerun()

if "5일" in period_option: p, i = "5d", "30m"
elif "1개월" in period_option: p, i = "1mo", "1d"
elif "6개월" in period_option: p, i = "6mo", "1d"
else: p, i = "1y", "1d"

# ==========================================
# 🚀 RAM 섹션 자동 추출 함수
# ==========================================
def extract_ram_section(full_text):
    """
    네이버 카페 게시글에서 RAM 관련 섹션만 추출
    시작: "RAM 메모리(삼성기준)"
    종료: "17.SSD 삼성 정품 기준" 또는 "SSD" 섹션 시작
    """
    # 시작 패턴들
    start_patterns = [
        "RAM 메모리(삼성기준)",
        "RAM 메모리",
        "16-1.데스크탑용 DDR5",
        "13.데스크탑 DDR3",
        "14.데스크탑 DDR4",
        "15.노트북용 DDR3",
        "16.노트북용 DDR4"
    ]
    
    # 종료 패턴들
    end_patterns = [
        "17.SSD",
        "20-3. 삼성 M.2",
        "0-1.삼성 120G,128G",
        "[모든 데이터는 포맷",
        "SSD 삼성 정품 기준"
    ]
    
    # 시작 위치 찾기
    start_pos = -1
    for pattern in start_patterns:
        pos = full_text.find(pattern)
        if pos != -1:
            if start_pos == -1 or pos < start_pos:
                start_pos = pos
    
    if start_pos == -1:
        return None
    
    # 종료 위치 찾기
    end_pos = len(full_text)
    for pattern in end_patterns:
        pos = full_text.find(pattern, start_pos)
        if pos != -1:
            if pos < end_pos:
                end_pos = pos
    
    # 추출
    extracted = full_text[start_pos:end_pos].strip()
    
    # 최소 길이 체크 (너무 짧으면 잘못된 추출)
    if len(extracted) < 100:
        return None
    
    return extracted

# ==========================================
# 🚀 데이터 저장/불러오기 함수
# ==========================================
PRICE_DATA_FILE = "price_data.json"
PRICE_HISTORY_FILE = "price_history.json"

def save_price_data(prices):
    """현재 가격 데이터 저장"""
    with open(PRICE_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(prices, f, ensure_ascii=False, indent=2)

def load_price_data():
    """현재 가격 데이터 불러오기"""
    if os.path.exists(PRICE_DATA_FILE):
        with open(PRICE_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_price_history(prices):
    """가격 히스토리 저장 (날짜별)"""
    history = load_price_history()
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 오늘 날짜로 데이터 추가
    if today not in history:
        history[today] = {}
    
    for category, items in prices.items():
        if category not in history[today]:
            history[today][category] = []
        history[today][category] = items
    
    with open(PRICE_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_price_history():
    """가격 히스토리 불러오기"""
    if os.path.exists(PRICE_HISTORY_FILE):
        with open(PRICE_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def get_price_trend(product_name, days=30):
    """특정 제품의 가격 추이 데이터 반환"""
    history = load_price_history()
    
    # 날짜 범위 계산
    from datetime import datetime, timedelta
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    # cutoff_date 이후의 날짜만 필터링
    valid_dates = [d for d in sorted(history.keys()) if d >= cutoff_date]
    
    price_trend = []
    for date in valid_dates:
        for category, items in history[date].items():
            for item in items:
                if item['product'] == product_name:
                    price_trend.append({
                        'date': date,
                        'price': item['price']
                    })
                    break
    
    return price_trend

# ==========================================
# 🚀 가격 파싱 함수
# ==========================================
def parse_price_data(price_text):
    """
    텍스트에서 CPU/RAM 가격 정보를 파싱합니다.
    다양한 형식 지원:
    - "8-12.i9 10900KF - 170.000원"
    - "삼성 D5 8G- 5600 [44800] - 110,000원"
    - "삼성 32G PC4 25600 [3200mhz] - 235.000원"
    - "14-2.삼성 16G PC4 21300[2666mhz] - 105,000원 , 19200[2400mhz] - 100.000원"
    데스크탑/노트북 구분 지원
    """
    prices = {}
    current_ram_type = None  # 'desktop' or 'laptop'
    
    for line in price_text.split('\n'):
        # 빈 줄이나 주석 건너뛰기
        if not line.strip() or line.strip().startswith('*') or line.strip().startswith('('):
            continue
        
        # 데스크탑/노트북 섹션 감지
        if '데스크탑용' in line or '데스크탑 DDR' in line:
            current_ram_type = 'desktop'
            continue
        elif '노트북용' in line or '노트북 DDR' in line:
            current_ram_type = 'laptop'
            continue
        
        # 여러 제품이 한 줄에 있는 경우 처리 (쉼표로 구분)
        if ' , ' in line:
            parts = line.split(' , ')
            
            # 첫 번째 파트에서 기본 정보 추출
            base_info = extract_base_info(parts[0])
            base_info['ram_type'] = current_ram_type  # 데스크탑/노트북 정보 추가
            
            for idx, part in enumerate(parts):
                if idx == 0:
                    parse_single_line(part, line, prices, None, current_ram_type)
                else:
                    # 이후 파트는 기본 정보를 상속
                    parse_single_line(part, line, prices, base_info, current_ram_type)
        else:
            parse_single_line(line, line, prices, None, current_ram_type)
    
    return prices

def extract_base_info(first_part):
    """첫 번째 파트에서 브랜드, 용량, 타입 등 기본 정보 추출"""
    info = {}
    
    # 삼성 체크
    if '삼성' in first_part:
        info['brand'] = '삼성'
    
    # DDR 타입 체크
    if 'D5' in first_part or 'DDR5' in first_part:
        info['ddr_type'] = 'DDR5'
    elif 'PC4' in first_part or 'DDR4' in first_part:
        info['ddr_type'] = 'DDR4'
    elif 'PC3' in first_part or 'DDR3' in first_part:
        info['ddr_type'] = 'DDR3'
    
    # 용량 체크
    capacity_match = re.search(r'(\d+G)', first_part)
    if capacity_match:
        info['capacity'] = capacity_match.group(1)
    
    return info

def parse_single_line(part, original_line, prices, base_info=None, ram_type=None):
    """단일 제품 라인 파싱"""
    # 패턴 1: DDR5 형식 - "삼성 D5 8G- 5600 [44800] - 110,000원"
    pattern1 = r'삼성\s*D5\s*(\d+G)[^\d]*([\d]+)\s*[\[\(]?[\d,\.]*[\]\)]?\s*-\s*([\d,\.]+)\s*원'
    match1 = re.search(pattern1, part, re.IGNORECASE)
    if match1:
        capacity = match1.group(1)
        speed = match1.group(2)
        price_str = match1.group(3).replace(',', '').replace('.', '')
        
        try:
            price = int(price_str)
            
            # 데스크탑/노트북 구분
            if ram_type == 'laptop':
                product_name = f"삼성 DDR5 {capacity} {speed}MHz (노트북)"
                category = "DDR5 RAM (노트북)"
            else:
                product_name = f"삼성 DDR5 {capacity} {speed}MHz"
                category = "DDR5 RAM (데스크탑)"
            
            if category not in prices:
                prices[category] = []
            
            prices[category].append({
                'product': product_name,
                'price': price,
                'price_formatted': f"{price:,}원"
            })
            return
        except ValueError:
            pass
    
    # 패턴 2: DDR4 형식 - "삼성 32G PC4 25600 [3200mhz] - 235.000원"
    pattern2 = r'삼성\s*(\d+G)\s*PC4\s*([\d]+)\s*[\[\(]?[\d,\.]*[Mm]?[Hh]?[Zz]?[\]\)]?\s*-\s*([\d,\.]+)\s*원'
    match2 = re.search(pattern2, part, re.IGNORECASE)
    if match2:
        capacity = match2.group(1)
        speed = match2.group(2)
        price_str = match2.group(3).replace(',', '').replace('.', '')
        
        try:
            price = int(price_str)
            
            # 데스크탑/노트북 구분
            if ram_type == 'laptop':
                product_name = f"삼성 DDR4 {capacity} PC4-{speed} (노트북)"
                category = "DDR4 RAM (노트북)"
            else:
                product_name = f"삼성 DDR4 {capacity} PC4-{speed}"
                category = "DDR4 RAM (데스크탑)"
            
            if category not in prices:
                prices[category] = []
            
            prices[category].append({
                'product': product_name,
                'price': price,
                'price_formatted': f"{price:,}원"
            })
            return
        except ValueError:
            pass
    
    # 패턴 2-1: DDR4/DDR5 추가 속도 (쉼표 뒤) - "19200[2400mhz] - 100.000원"
    # base_info가 있으면 이전 정보를 활용
    if base_info and base_info.get('ddr_type') in ['DDR4', 'DDR5']:
        pattern2_1 = r'([\d]+)\s*[\[\(]?[\d,\.]*[Mm]?[Hh]?[Zz]?[\]\)]?\s*-\s*([\d,\.]+)\s*원'
        match2_1 = re.search(pattern2_1, part)
        if match2_1:
            speed = match2_1.group(1)
            price_str = match2_1.group(2).replace(',', '').replace('.', '')
            
            try:
                price = int(price_str)
                capacity = base_info.get('capacity', '')
                ddr_type = base_info.get('ddr_type', '')
                current_ram_type = base_info.get('ram_type')
                
                if ddr_type == 'DDR5':
                    if current_ram_type == 'laptop':
                        product_name = f"삼성 DDR5 {capacity} {speed}MHz (노트북)"
                        category = "DDR5 RAM (노트북)"
                    else:
                        product_name = f"삼성 DDR5 {capacity} {speed}MHz"
                        category = "DDR5 RAM (데스크탑)"
                elif ddr_type == 'DDR4':
                    if current_ram_type == 'laptop':
                        product_name = f"삼성 DDR4 {capacity} PC4-{speed} (노트북)"
                        category = "DDR4 RAM (노트북)"
                    else:
                        product_name = f"삼성 DDR4 {capacity} PC4-{speed}"
                        category = "DDR4 RAM (데스크탑)"
                else:
                    return
                
                if category not in prices:
                    prices[category] = []
                
                prices[category].append({
                    'product': product_name,
                    'price': price,
                    'price_formatted': f"{price:,}원"
                })
                return
            except ValueError:
                pass
    
    # 패턴 3: DDR3 형식 - "삼성 8G PC3 12800 - 3,000원"
    pattern3 = r'삼성\s*(\d+G)\s*PC3\s*([\d]+)\s*-\s*([\d,\.]+)\s*원'
    match3 = re.search(pattern3, part, re.IGNORECASE)
    if match3:
        capacity = match3.group(1)
        speed = match3.group(2)
        price_str = match3.group(3).replace(',', '').replace('.', '')
        
        try:
            price = int(price_str)
            
            # 데스크탑/노트북 구분
            if ram_type == 'laptop':
                product_name = f"삼성 DDR3 {capacity} PC3-{speed} (노트북)"
                category = "DDR3 RAM (노트북)"
            else:
                product_name = f"삼성 DDR3 {capacity} PC3-{speed}"
                category = "DDR3 RAM (데스크탑)"
            
            if category not in prices:
                prices[category] = []
            
            prices[category].append({
                'product': product_name,
                'price': price,
                'price_formatted': f"{price:,}원"
            })
            return
        except ValueError:
            pass
    
    # 패턴 4: CPU 형식 - "8-12.i9 10900KF - 170.000원"
    pattern4 = r'[\d\-\.]+\s*([iR][3579]\s*[\-\s]?[\d]+[A-Z]*[A-Z]?)\s*-\s*([\d,\.]+)\s*원'
    match4 = re.search(pattern4, part, re.IGNORECASE)
    if match4:
        cpu_name = match4.group(1).strip()
        price_str = match4.group(2).replace(',', '').replace('.', '')
        
        try:
            price = int(price_str)
            
            # Intel vs AMD 구분
            if cpu_name.lower().startswith('i'):
                category = "Intel CPU"
                product_name = cpu_name
            elif cpu_name.lower().startswith('r'):
                category = "AMD CPU"
                product_name = cpu_name
            else:
                return
            
            if category not in prices:
                prices[category] = []
            
            prices[category].append({
                'product': product_name,
                'price': price,
                'price_formatted': f"{price:,}원"
            })
            return
        except ValueError:
            pass
    
    # 패턴 5: 그래픽카드 - "RTX 2060 - 120.000원"
    pattern5 = r'([GR]TX|RX)\s*([\d]+\s*[A-Z]*)\s*-\s*([\d,\.]+)\s*원'
    match5 = re.search(pattern5, part, re.IGNORECASE)
    if match5:
        gpu_type = match5.group(1)
        gpu_model = match5.group(2).strip()
        price_str = match5.group(3).replace(',', '').replace('.', '')
        
        try:
            price = int(price_str)
            product_name = f"{gpu_type} {gpu_model}"
            
            if "그래픽카드" not in prices:
                prices["그래픽카드"] = []
            
            prices["그래픽카드"].append({
                'product': product_name,
                'price': price,
                'price_formatted': f"{price:,}원"
            })
            return
        except ValueError:
            pass
    
    # 패턴 6: 메인보드 - "B660 칩셋 45.000원"
    pattern6 = r'([HBZAX][\d]+)\s*칩[셋]?\s*-?\s*([\d,\.]+)\s*원'
    match6 = re.search(pattern6, part, re.IGNORECASE)
    if match6:
        chipset = match6.group(1)
        price_str = match6.group(2).replace(',', '').replace('.', '')
        
        try:
            price = int(price_str)
            product_name = f"{chipset} 칩셋"
            
            if "메인보드" not in prices:
                prices["메인보드"] = []
            
            prices["메인보드"].append({
                'product': product_name,
                'price': price,
                'price_formatted': f"{price:,}원"
            })
            return
        except ValueError:
            pass
    
    # 패턴 7: SSD - "삼성 500G,512G - 40.000원"
    pattern7 = r'삼성\s*([\d]+G[,/]?[\d]*G?)\s*-\s*([\d,\.]+)\s*원'
    match7 = re.search(pattern7, part, re.IGNORECASE)
    if match7 and 'SSD' in original_line:
        capacity = match7.group(1).split(',')[0].split('/')[0]
        price_str = match7.group(2).replace(',', '').replace('.', '')
        
        try:
            price = int(price_str)
            product_name = f"삼성 SSD {capacity}"
            
            if "SSD" not in prices:
                prices["SSD"] = []
            
            prices["SSD"].append({
                'product': product_name,
                'price': price,
                'price_formatted': f"{price:,}원"
            })
            return
        except ValueError:
            pass
    
    # 패턴 8: HDD - "1테라,1TB - 6.000원"
    pattern8 = r'([\d]+)\s*[테테라]*[,/]?([\d]*)\s*TB\s*-\s*([\d,\.]+)\s*원'
    match8 = re.search(pattern8, part, re.IGNORECASE)
    if match8:
        capacity = match8.group(1)
        price_str = match8.group(3).replace(',', '').replace('.', '')
        
        try:
            price = int(price_str)
            product_name = f"{capacity}TB HDD"
            
            if "HDD" not in prices:
                prices["HDD"] = []
            
            prices["HDD"].append({
                'product': product_name,
                'price': price,
                'price_formatted': f"{price:,}원"
            })
            return
        except ValueError:
            pass

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
st.title(f"📊 Seondori.com ({period_option})")

if raw_data is None:
    st.error("데이터 서버 연결 중...")
else:
    # 탭 생성 (순서 변경: Trading View → 주가지수 → 환율 → RAM 시세 → 국채 금리)
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔍 Trading View", "📈 주가지수", "💱 환율", "💾 RAM 시세", "💰 국채 금리"])
    
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
        c1, c2, c3, c4 = st.columns(4)
        with c1: draw_card("🇰🇷 원/달러", "KRW=X")
        with c2: draw_card("🇨🇳 원/위안", "CALC_CNYKRW")
        with c3: draw_card("🇯🇵 원/엔 (100엔)", "JPYKRW=X")
        with c4: draw_card("🌎 달러 인덱스", "DX-Y.NYB")

    with tab4:
        st.subheader("💾 RAM 시세")
        
        # 기간 선택
        col_period1, col_period2 = st.columns([3, 1])
        with col_period1:
            view_period = st.selectbox(
                "시세 히스토리 기간",
                ["최근 5일", "최근 15일", "최근 1개월", "최근 6개월", "전체"],
                index=2,  # 기본값: 최근 1개월
                key="ram_period"
            )
        
        # 기간에 따른 일수 계산
        if "5일" in view_period:
            days = 5
        elif "15일" in view_period:
            days = 15
        elif "1개월" in view_period:
            days = 30
        elif "6개월" in view_period:
            days = 180
        else:
            days = 365 * 10  # 전체
        
        # 관리자 전용: 가격 업데이트
        if st.session_state.admin_authenticated:
            # ⚠️ 중요 경고 표시
            st.error("⚠️ **중요**: Streamlit Cloud는 앱 재시작 시 데이터가 삭제됩니다! 반드시 백업하세요!")
            
            with st.expander("📝 가격 정보 업데이트 (관리자 전용)", expanded=False):
                st.markdown("##### 📅 데이터 입력 날짜 선택")
                
                col_date1, col_date2 = st.columns(2)
                with col_date1:
                    input_date = st.date_input(
                        "날짜",
                        value=datetime.now().date(),
                        help="원하는 날짜를 선택하세요 (과거/현재/미래 모두 가능)"
                    )
                
                with col_date2:
                    st.info(f"선택된 날짜: **{input_date.strftime('%Y년 %m월 %d일')}**")
                
                st.markdown("##### 💡 입력 방법")
                st.info("""
                **네이버 카페에서 복사하기:**
                1. 게시글 전체를 복사 (Ctrl+A, Ctrl+C)
                2. 아래 입력창에 붙여넣기 (Ctrl+V)
                3. '💾 자동 추출 및 저장' 클릭
                
                → RAM 관련 섹션만 자동으로 추출됩니다!
                """)
                
                price_input = st.text_area(
                    "가격 정보 입력 (게시글 전체를 붙여넣으세요)",
                    height=200,
                    placeholder="네이버 카페 게시글 전체 내용을 붙여넣으세요...",
                    key="price_input"
                )
                
                col_btn1, col_btn2, col_btn3 = st.columns(3)
                with col_btn1:
                    if st.button("💾 자동 추출 및 저장", type="primary"):
                        if price_input:
                            # RAM 섹션 자동 추출
                            extracted_text = extract_ram_section(price_input)
                            
                            if extracted_text:
                                st.success(f"✅ RAM 섹션 추출 완료! ({len(extracted_text)} 글자)")
                                
                                with st.expander("📋 추출된 내용 미리보기", expanded=True):
                                    st.text_area("추출된 RAM 가격 정보", extracted_text, height=150, disabled=True)
                                
                                # 파싱 시도
                                parsed_prices = parse_price_data(extracted_text)
                                if parsed_prices:
                                    # 선택한 날짜로 저장
                                    selected_date = input_date.strftime('%Y-%m-%d')
                                    
                                    # 히스토리에 저장
                                    history = load_price_history()
                                    if selected_date not in history:
                                        history[selected_date] = {}
                                    
                                    for category, items in parsed_prices.items():
                                        history[selected_date][category] = items
                                    
                                    with open(PRICE_HISTORY_FILE, 'w', encoding='utf-8') as f:
                                        json.dump(history, f, ensure_ascii=False, indent=2)
                                    
                                    # 오늘 날짜면 현재 데이터로도 저장
                                    if selected_date == datetime.now().strftime('%Y-%m-%d'):
                                        save_price_data(parsed_prices)
                                    
                                    total_items = sum(len(items) for items in parsed_prices.values())
                                    st.success(f"✅ {selected_date} 가격 정보가 저장되었습니다! (총 {total_items}개 제품)")
                                    
                                    # 즉시 백업 다운로드 권장
                                    st.warning("🔔 **지금 바로 백업 다운로드를 권장합니다!** (아래 '저장된 히스토리' 섹션)")
                                    
                                    st.rerun()
                                else:
                                    st.error("❌ 파싱 가능한 가격 정보가 없습니다.")
                            else:
                                st.warning("⚠️ RAM 섹션을 찾을 수 없습니다. 게시글 전체를 복사했는지 확인해주세요.")
                        else:
                            st.warning("⚠️ 가격 정보를 입력해주세요.")
                
                with col_btn2:
                    if st.button("📋 수동 입력"):
                        if price_input:
                            parsed_prices = parse_price_data(price_input)
                            if parsed_prices:
                                # 선택한 날짜로 저장
                                selected_date = input_date.strftime('%Y-%m-%d')
                                
                                # 히스토리에 저장
                                history = load_price_history()
                                if selected_date not in history:
                                    history[selected_date] = {}
                                
                                for category, items in parsed_prices.items():
                                    history[selected_date][category] = items
                                
                                with open(PRICE_HISTORY_FILE, 'w', encoding='utf-8') as f:
                                    json.dump(history, f, ensure_ascii=False, indent=2)
                                
                                # 오늘 날짜면 현재 데이터로도 저장
                                if selected_date == datetime.now().strftime('%Y-%m-%d'):
                                    save_price_data(parsed_prices)
                                
                                st.success(f"✅ {selected_date} 가격 정보가 저장되었습니다!")
                                st.rerun()
                            else:
                                st.error("❌ 파싱 가능한 가격 정보가 없습니다.")
                        else:
                            st.warning("⚠️ 가격 정보를 입력해주세요.")
                
                with col_btn3:
                    if st.button("🗑️ 전체 삭제"):
                        if os.path.exists(PRICE_DATA_FILE):
                            os.remove(PRICE_DATA_FILE)
                        if os.path.exists(PRICE_HISTORY_FILE):
                            os.remove(PRICE_HISTORY_FILE)
                        st.success("✅ 모든 데이터가 삭제되었습니다.")
                        st.rerun()
                
                # 히스토리 관리
                st.markdown("---")
                st.markdown("##### 📊 저장된 히스토리")
                history = load_price_history()
                
                # 데이터 백업/복원 (항상 표시)
                st.markdown("##### 💾 데이터 백업 / 복원")
                col_backup1, col_backup2 = st.columns(2)
                
                with col_backup1:
                    # JSON 파일 다운로드
                    if history:
                        backup_data = {
                            'price_data': load_price_data(),
                            'price_history': history
                        }
                        backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2)
                        st.download_button(
                            label="📥 백업 다운로드 (JSON)",
                            data=backup_json,
                            file_name=f"ram_price_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            mime="application/json",
                            help="데이터를 안전하게 백업하세요"
                        )
                    else:
                        st.info("저장된 데이터가 없습니다")
                
                with col_backup2:
                    # 백업 복원
                    uploaded_backup = st.file_uploader(
                        "📤 백업 복원",
                        type=['json'],
                        help="이전에 다운로드한 백업 파일을 업로드하세요",
                        key="backup_restore_uploader"
                    )
                    if uploaded_backup is not None:
                        try:
                            backup_content = json.loads(uploaded_backup.read().decode('utf-8'))
                            
                            if 'price_data' in backup_content:
                                with open(PRICE_DATA_FILE, 'w', encoding='utf-8') as f:
                                    json.dump(backup_content['price_data'], f, ensure_ascii=False, indent=2)
                            
                            if 'price_history' in backup_content:
                                with open(PRICE_HISTORY_FILE, 'w', encoding='utf-8') as f:
                                    json.dump(backup_content['price_history'], f, ensure_ascii=False, indent=2)
                            
                            st.success("✅ 백업이 복원되었습니다!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ 백업 복원 실패: {e}")
                
                st.markdown("---")
                
                # 히스토리 목록
                if history:
                    dates = sorted(history.keys(), reverse=True)
                    st.write(f"총 **{len(dates)}일**의 데이터가 저장되어 있습니다.")
                    
                    date_df = pd.DataFrame({
                        '날짜': dates,
                        '카테고리 수': [len(history[d]) for d in dates],
                        '총 제품 수': [sum(len(items) for items in history[d].values()) for d in dates]
                    })
                    st.dataframe(date_df, hide_index=True, use_container_width=True)
                    
                    # 특정 날짜 삭제
                    st.markdown("##### 🗑️ 특정 날짜 데이터 삭제")
                    col_del1, col_del2 = st.columns([3, 1])
                    with col_del1:
                        date_to_delete = st.selectbox("삭제할 날짜 선택", dates)
                    with col_del2:
                        st.write("")  # 간격 조정
                        if st.button("삭제", key="delete_specific_date"):
                            del history[date_to_delete]
                            with open(PRICE_HISTORY_FILE, 'w', encoding='utf-8') as f:
                                json.dump(history, f, ensure_ascii=False, indent=2)
                            st.success(f"✅ {date_to_delete} 데이터가 삭제되었습니다.")
                            st.rerun()
                else:
                    st.info("아직 저장된 히스토리가 없습니다.")
        
        # 저장된 가격 정보 불러오기
        current_prices = load_price_data()
        
        if current_prices:
            # 마지막 업데이트 시간 표시
            if os.path.exists(PRICE_DATA_FILE):
                update_time = datetime.fromtimestamp(os.path.getmtime(PRICE_DATA_FILE))
                st.info(f"📅 마지막 업데이트: {update_time.strftime('%Y년 %m월 %d일 %H:%M:%S')}")
            
            # 카테고리별로 표시
            categories_order = [
                "Intel CPU", "AMD CPU", "그래픽카드", 
                "DDR5 RAM (데스크탑)", "DDR5 RAM (노트북)",
                "DDR4 RAM (데스크탑)", "DDR4 RAM (노트북)",
                "DDR3 RAM (데스크탑)", "DDR3 RAM (노트북)",
                "메인보드", "SSD", "HDD", "기타"
            ]
            
            # 검색 기능
            search_query = st.text_input("🔍 제품 검색", placeholder="제품명 입력...")
            
            for category in categories_order:
                if category in current_prices and current_prices[category]:
                    items = current_prices[category]
                    
                    # 검색 필터링
                    if search_query:
                        items = [item for item in items if search_query.lower() in item['product'].lower()]
                    
                    if items:
                        with st.expander(f"📦 {category} ({len(items)}개)", expanded=True):
                            # 데이터프레임으로 변환
                            df = pd.DataFrame(items)
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
                            
                            # 가격 추이 차트 - 제품 선택 방식
                            st.markdown("##### 📊 개별 제품 가격 추이")
                            
                            # 히스토리가 있는 제품만 필터링
                            products_with_history = []
                            for idx, row in df.iterrows():
                                product_name = row['product']
                                trend_data = get_price_trend(product_name, days)
                                if trend_data and len(trend_data) >= 2:
                                    products_with_history.append({
                                        'name': product_name,
                                        'current_price': row['price'],
                                        'trend_data': trend_data
                                    })
                            
                            if products_with_history:
                                # 제품 선택 드롭다운
                                product_options = [f"{p['name']} (현재가: {p['current_price']:,}원)" 
                                                 for p in products_with_history]
                                
                                selected_idx = st.selectbox(
                                    "제품 선택",
                                    range(len(product_options)),
                                    format_func=lambda x: product_options[x],
                                    key=f"product_select_{category}"
                                )
                                
                                # 선택된 제품의 가격 추이 그래프
                                selected_product = products_with_history[selected_idx]
                                trend_data = selected_product['trend_data']
                                
                                dates = [item['date'] for item in trend_data]
                                prices = [item['price'] for item in trend_data]
                                
                                # 가격 변동 계산
                                if len(prices) >= 2:
                                    price_change = prices[-1] - prices[0]
                                    price_change_pct = (price_change / prices[0]) * 100 if prices[0] != 0 else 0
                                    
                                    # 변동 정보 표시
                                    col_info1, col_info2, col_info3 = st.columns(3)
                                    with col_info1:
                                        st.metric("시작가", f"{prices[0]:,}원")
                                    with col_info2:
                                        st.metric("현재가", f"{prices[-1]:,}원")
                                    with col_info3:
                                        st.metric("변동", f"{price_change:+,}원", f"{price_change_pct:+.2f}%")
                                
                                # 그래프 생성 (모바일 최적화 + 등락폭 강조)
                                fig = go.Figure()
                                
                                # 가격 상승/하락 색상 결정
                                line_color = '#ff5252' if prices[-1] >= prices[0] else '#00e676'
                                fill_color = 'rgba(255,82,82,0.15)' if prices[-1] >= prices[0] else 'rgba(0,230,118,0.15)'
                                
                                fig.add_trace(go.Scatter(
                                    x=dates,
                                    y=prices,
                                    mode='lines+markers',
                                    name=selected_product['name'],
                                    line=dict(color=line_color, width=2.5),
                                    marker=dict(
                                        size=7, 
                                        color=line_color,
                                        line=dict(color='white', width=1)
                                    ),
                                    fill='tozeroy',
                                    fillcolor=fill_color,
                                    hovertemplate='<b>%{x}</b><br>가격: ₩%{y:,}<extra></extra>'
                                ))
                                
                                # Y축 범위 타이트하게 조정 (등락폭 강조)
                                price_min = min(prices)
                                price_max = max(prices)
                                price_range = price_max - price_min
                                
                                # 등락폭이 작을 때는 패딩을 작게, 클 때는 조금만
                                if price_range > 0:
                                    # 패딩을 3%로 축소하여 등락폭이 더 크게 보이도록
                                    y_padding = price_range * 0.03
                                else:
                                    # 가격 변동이 없을 경우
                                    y_padding = price_min * 0.05
                                
                                # X축 날짜 표시 전략 (2일에 1번)
                                num_points = len(dates)
                                
                                # 모든 기간에서 2일마다 표시
                                dtick = 'D2'  # 2일마다
                                tickmode = None
                                tickangle = -45
                                
                                # 모바일 최적화 레이아웃
                                fig.update_layout(
                                    autosize=True,
                                    height=280,  # 모바일에 최적화된 높이
                                    margin=dict(l=15, r=15, t=20, b=50),  # 하단 여백 증가 (날짜 표시)
                                    paper_bgcolor='rgba(0,0,0,0)',
                                    plot_bgcolor='rgba(30,30,30,0.8)',
                                    xaxis=dict(
                                        title="",
                                        gridcolor='rgba(255,255,255,0.08)',
                                        showgrid=True,
                                        tickfont=dict(size=8, color='#aaa'),
                                        tickangle=tickangle,
                                        tickmode=tickmode,
                                        dtick=dtick,
                                        tickformat='%m/%d'  # 월/일 형식
                                    ),
                                    yaxis=dict(
                                        title="",
                                        gridcolor='rgba(255,255,255,0.08)',
                                        showgrid=True,
                                        tickformat=',.0f',
                                        tickprefix='₩',
                                        tickfont=dict(size=9, color='#aaa'),
                                        range=[price_min - y_padding, price_max + y_padding],
                                        fixedrange=False
                                    ),
                                    showlegend=False,
                                    hovermode="x unified",
                                    font=dict(size=10, color='#fff'),
                                    hoverlabel=dict(
                                        bgcolor='rgba(30,30,30,0.95)',
                                        font_size=11,
                                        font_color='white'
                                    )
                                )
                                
                                # 반응형 설정
                                config = {
                                    'displayModeBar': False,
                                    'responsive': True
                                }
                                
                                st.plotly_chart(fig, use_container_width=True, config=config)
                                
                                # 상세 데이터 테이블
                                with st.expander("📋 상세 가격 데이터"):
                                    trend_df = pd.DataFrame(trend_data)
                                    trend_df['price_formatted'] = trend_df['price'].apply(lambda x: f"{x:,}원")
                                    
                                    # 전일 대비 변동 계산
                                    trend_df['change'] = trend_df['price'].diff()
                                    trend_df['change_pct'] = (trend_df['price'].pct_change() * 100).round(2)
                                    trend_df['change_formatted'] = trend_df.apply(
                                        lambda row: f"{row['change']:+,.0f}원 ({row['change_pct']:+.2f}%)" 
                                        if pd.notna(row['change']) else "-",
                                        axis=1
                                    )
                                    
                                    st.dataframe(
                                        trend_df[['date', 'price_formatted', 'change_formatted']].rename(columns={
                                            'date': '날짜',
                                            'price_formatted': '가격',
                                            'change_formatted': '전일 대비'
                                        }),
                                        hide_index=True,
                                        use_container_width=True
                                    )
                            else:
                                st.info("📈 히스토리 데이터가 충분하지 않습니다. (최소 2일 이상의 데이터 필요)")
        else:
            st.warning("⚠️ 아직 등록된 가격 정보가 없습니다.")
            if st.session_state.admin_authenticated:
                st.info("💡 위의 '가격 정보 업데이트' 섹션에서 가격을 입력해주세요.")
            else:
                st.info("💡 관리자가 가격 정보를 업데이트하면 여기에 표시됩니다.")

    with tab5:
        col_kr, col_us = st.columns(2)
        with col_kr:
            st.markdown("##### 🇰🇷 한국 국채")
            draw_card("한국 3년 국채", "IRr_GOV03Y", is_korea_bond=True, etf_code="114260.KS")
            draw_card("한국 10년 국채", "IRr_GOV10Y", is_korea_bond=True, etf_code="148070.KS")
        with col_us:
            st.markdown("##### 🇺🇸 미국 국채")
            draw_card("미국 2년 금리 (선물)", "ZT=F")
            draw_card("미국 10년 금리 (지수)", "^TNX")
