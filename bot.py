import os
import requests
import json
import time
from datetime import datetime, timedelta, timezone

# ========== 설정 (발주계획 전용) ==========
SERVICE_KEY = os.environ.get("SERVICE_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

KEYWORDS = ["도시", "설계", "타당성", "개발", "조성", "산단", "계획"]
CACHE_FILE = "sent_ids.json"

# 한국 시간(KST, UTC+9) 정의
KST = timezone(timedelta(hours=9))

# 이미 보낸 공고 기록 불러오기 (기억 유지용)
def load_sent_ids():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

# 보낸 공고 기록 저장하기
def save_sent_ids(sent_ids):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(sent_ids), f, ensure_ascii=False)
    except Exception as e:
        print("기록 저장 오류:", e)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        res = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=10)
        print("텔레그램 전송:", res.status_code)
    except Exception as e:
        print("텔레그램 오류:", e)

def fetch_order_plans():
    url = "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService/getOrderPlanSttusListServcPPSSrch"
    
    # 사전규격과 완전히 똑같이 오늘 자정부터 현재까지 실시간 조회 적용
    today = datetime.now(KST)
    bgn_dt = today.strftime('%Y%m%d0000')  # 오늘 자정 이후 공고만 조회
    end_dt = today.strftime('%Y%m%d%H%M')
    
    all_items = []
    page_no = 1
    num_of_rows = 100  # 한 번에 100개씩 페이지별 호출
    
    for attempt in range(3):
        try:
            while True:
                params = {
                    "serviceKey": SERVICE_KEY,
                    "pageNo": str(page_no),
                    "numOfRows": str(num_of_rows),
                    "inqryDiv": "1",
                    "inqryBgnDt": bgn_dt,
                    "inqryEndDt": end_dt,
                    "type": "json"
                }
                
                res = requests.get(url, params=params, timeout=30)
                if res.status_code != 200:
                    print(f"API 오류 상태코드: {res.status_code}")
                    break
                
                data = res.json()
                body = data.get("response", {}).get("body", {})
                total_count = body.get("totalCount", 0)
                
                items_data = body.get("items", [])
                if isinstance(items_data, dict):
                    items = items_data.get("item", [])
                else:
                    items = items_data
                if not isinstance(items, list):
                    items = [items] if items else []
                    
                if not items:
                    break
                    
                all_items.extend(items)
                
                # 전체 개수에 도달했거나 더 이상 없으면 탈출
                if len(all_items) >= total_count or len(items) < num_of_rows:
                    break
                page_no += 1
            
            print(f"API 수집 완료: 총 {len(all_items)}개 발주계획 확인")
            return all_items
            
        except Exception as e:
            print(f"통신 오류 발생 (시도 {attempt + 1}/3): {e}")
            time.sleep(5)
            
    return []

def main_once():
    # 한국 시간(KST) 기준 로그 출력
    print(f"\n[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] 실시간 발주계획 확인 중...")
    
    sent_ids = load_sent_ids()
    items = fetch_order_plans()
    print(f"조회된 전체 건수: {len(items)}")
    
    new_count = 0
    
    for item in items:
        title = item.get("bizNm") or ""
        org = item.get("orderInsttNm") or "기관정보 없음"
        div_name = item.get("bsnsDivNm") or ""
        amount = item.get("sumOrderAmt") or ""
        year = item.get("orderYear") or ""
        month = item.get("orderMnth") or ""
        
        # 고유 ID 생성
        unique_id = f"{org}_{title}_{year}{month}"
        
        if not title or unique_id in sent_ids:
            continue
        
        # 1. 기술용역 필터
        if "기술" not in div_name and "기술용역" not in title:
            if not any(kw in title for kw in ["설계", "타당성", "계획"]):
                continue
        
        # 2. 키워드 필터
        matched = [kw for kw in KEYWORDS if kw in title]
        if not matched:
            continue
        
        # 신규 공고 알림 전송
        msg = f"""📋 <b>신규 기술용역 발주계획 알림</b>

📌 <b>{title}</b>
🏛 발주기관: {org}
🏷 구분: {div_name}
📅 발주시점: {year}년 {month}월
💰 금액: {amount}원
🔍 키워드: {', '.join(matched)}"""
        
        send_telegram(msg)
        sent_ids.add(unique_id)
        new_count += 1
        print("→ 신규 알림 전송:", title)
        time.sleep(3)
    
    # 기억한 목록을 파일에 다시 저장
    save_sent_ids(sent_ids)
    
    if new_count == 0:
        print("새로운 발주계획 공고 없음 (정상 완료)")
    else:
        print(f"신규 발주계획 알림 {new_count}건 전송 완료")

if __name__ == "__main__":
    main_once()
