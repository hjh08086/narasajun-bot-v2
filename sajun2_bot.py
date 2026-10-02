import os
import requests
import json
import time
from datetime import datetime, timedelta, timezone

# ========== 설정 (사전규격 전용) ==========
SERVICE_KEY = os.environ.get("SERVICE_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

KEYWORDS = ["도시", "설계", "타당성", "개발", "조성", "산단", "계획"]
CACHE_FILE = "sent_sajun_ids.json"

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

def fetch_sajun_plans():
    base_url = "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServcPPSSrch"
    
    # 한국 시간 기준 현재 시각 적용
    today = datetime.now(KST)
    bgn_dt = (today - timedelta(days=2)).strftime('%Y%m%d0000') # 최근 2일 집중 조회
    end_dt = today.strftime('%Y%m%d%H%M')
    
    all_items = []
    page_no = 1
    num_of_rows = 100  # 한 번에 100개씩 페이지별 호출
    
    for attempt in range(3):
        try:
            while True:
                params = {
                    'serviceKey': SERVICE_KEY,
                    'pageNo': str(page_no),
                    'numOfRows': str(num_of_rows),
                    'type': 'json',
                    'inqryBgnDt': bgn_dt,
                    'inqryEndDt': end_dt,
                    'inqryDiv': '1'
                }
                
                res = requests.get(base_url, params=params, timeout=30)
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
                
                # 가져온 개수가 전체 개수(totalCount)에 도달했거나 더 이상 없으면 반복 탈출
                if len(all_items) >= total_count or len(items) < num_of_rows:
                    break
                page_no += 1
            
            print(f"API 수집 완료: 총 {len(all_items)}개 공고 확인")
            return all_items
            
        except Exception as e:
            print(f"통신 오류 발생 (시도 {attempt + 1}/3): {e}")
            time.sleep(5)
            
    return []

def main_once():
    # 한국 시간 기준 로그 출력
    print(f"\n[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] 실시간 사전규격 확인 중...")
    
    sent_ids = load_sent_ids()
    items = fetch_sajun_plans()
    print(f"최종 파싱된 공고 건수: {len(items)}")
    
    new_count = 0
    
    for item in items:
        # 실제 공고명/제목이 담긴 필드 우선순위 반영
        title = (
            item.get("bfSpecNm") or
            item.get("prdctClsfcNoNm") or 
            item.get("bidNtceNm") or 
            item.get("bfSpecRgstNoNm") or 
            item.get("prcurePrnmntNoNm") or 
            item.get("ntceNm") or 
            item.get("cnstwkNm") or 
            ""
        )
        
        org = item.get("rlDminsttNm") or item.get("orderInsttNm") or item.get("ntceInsttNm") or "기관정보 없음"
        bid_no = item.get("bfSpecRgstNo") or item.get("bidNtceNo", "")
        bid_ord = item.get("bidNtceOrd", "1")
        
        unique_id = f"{bid_no}_{bid_ord}"
        
        if not title:
            continue
            
        if unique_id in sent_ids:
            continue
        
        # 1. 기술용역 필터
        if "기술" not in title and "용역" not in title:
            if not any(kw in title for kw in KEYWORDS):
                continue
        
        # 2. 키워드 필터
        matched = [kw for kw in KEYWORDS if kw in title]
        if not matched:
            continue
            
        print(f" → 조건 일치! 알림 대상: {title}")
        
        # 신규 공고 알림 전송
        msg = f"""🔍 <b>신규 기술용역 사전규격 알림</b>

📌 <b>{title}</b>
🏛 발주기관: {org}
🔍 키워드: {', '.join(matched)}"""
        
        send_telegram(msg)
        sent_ids.add(unique_id)
        new_count += 1
        time.sleep(3)
    
    save_sent_ids(sent_ids)
    
    if new_count == 0:
        print("새로운 사전규격 공고 없음 (정상 대기 중)")
    else:
        print(f"신규 사전규격 알림 {new_count}건 전송 완료")

if __name__ == "__main__":
    # GitHub Actions에서 한 번만 깔끔하게 실행되도록 단발성 구조 유지
    main_once()
# 봇 활성화 체크 (스케줄러 갱신)
