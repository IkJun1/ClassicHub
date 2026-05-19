import schedule
import time
from datetime import datetime, timedelta
import os
# python-dotenv 라이브러리에서 필요한 함수를 가져옵니다.
from dotenv import load_dotenv 

# 기존 작성한 크롤러와 ETL 모듈 임포트
from 클래식_크롤링_리팩토링 import KopisCrawler
from etl_loader import run_etl_process

# 스크립트 실행 시 현재 경로의 .env 파일을 자동으로 로드합니다.
load_dotenv()

def daily_batch_job():
    print(f"\n{'='*50}")
    print(f"[일일 배치 작업 시작] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    try:
        # 1. 수집 날짜 범위 설정 (어제부터 ~ 6개월 뒤까지의 공연 데이터를 동기화)
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        six_months_later = today + timedelta(days=180)
        
        stdate_str = yesterday.strftime('%Y%m%d')
        eddate_str = six_months_later.strftime('%Y%m%d')
        print(f"수집 기간: {stdate_str} ~ {eddate_str}")

        api_key = os.getenv("KOPIS_API_KEY")
        if not api_key:
            raise ValueError(".env 파일에서 KOPIS_API_KEY를 찾을 수 없습니다.")

        # 2. 크롤링 파이프라인 가동 (API -> CSV 임시 저장)
        crawler = KopisCrawler(api_key=api_key) 
        
        # 3. 임시 파일명 설정 (etl_loader.py가 읽을 수 있는 이름으로)
        temp_csv = 'kopis_classic_data.csv' 
        
        print("1단계: KOPIS API에서 신규/변경 데이터 크롤링 중...")
        
        # 4. 베이스 파일 없이 신규 기간에 대해서만 수집하여 덮어쓰기
        crawler.run(stdate=stdate_str, eddate=eddate_str, output_filename=temp_csv)
        
        # 5. ETL 파이프라인 가동 (CSV -> DB 적재 및 정제)
        print("2단계: 크롤링된 데이터를 정제하여 DB에 UPSERT 중...")
        run_etl_process()
        
        print(f"✅ [일일 배치 작업 완료] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
    except Exception as e:
        print(f"❌ [배치 작업 실패] {e}")

# 매일 새벽 2시에 daily_batch_job 함수를 실행하도록 스케줄 등록
schedule.every().day.at("02:00").do(daily_batch_job)

if __name__ == "__main__":
    print("🕒 KOPIS 자동화 스케줄러가 가동되었습니다. (매일 새벽 2시 실행 대기 중...)")
    
    # [테스트용] 스케줄을 기다리지 않고 지금 당장 1회 강제 실행해보고 싶다면 아래 주석을 푸세요.
    daily_batch_job() 
    
    # 무한 루프를 돌며 예약된 시간이 되었는지 검사
    while True:
        schedule.run_pending()
        time.sleep(60) # 60초마다 시간 확인 (CPU 점유율 방지)