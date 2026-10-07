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
    
    # 한국 시간 기준 오늘 자정부터 현재까지의 기간 설정 추가
    today = datetime.now(KST)
    bgn_dt = today.strftime('%Y%m%d0000')  # 오늘 자정 시작
    end_dt = today.strftime('%Y%m%d%H%M')  # 현재 시간
    
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": "1",
        "numOfRows": "300",
        "inqryDiv": "1",
        "inqryBgnDt": bgn_dt,  # 조회 시작일 추가
        "inqryEndDt": end_dt,  # 조회 종료일 추가
        "type": "json"
    }
    
    try:
        res = requests.get(url, params=params, timeout=30)
        if res.status_code != 200:
            print("API 오류 상태코드:", res.status_code)
            return []
        
        data = res.json()
        body = data.get("response", {}).get("body", {})
        items = body.get("items", [])
        
        if not isinstance(items, list):
            items = [items] if items else []
            
        return items
    except Exception as e:
        print("API 호출 오류:", e)
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
# 봇 활성화 체크 (스케줄러 갱신)
