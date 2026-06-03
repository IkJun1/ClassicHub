import schedule
import time
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv 

# 루트 디렉토리의 .env 파일을 명시적으로 로드
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=ENV_PATH)

from 클래식_크롤링_리팩토링 import KopisCrawler
from etl_loader import run_etl_process

def daily_batch_job():
    print(f"\n{'='*50}")
    print(f"[INFO] 일일 배치 작업 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    try:
        # 1. 수집 날짜 범위 설정 (어제 ~ 6개월 뒤)
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        six_months_later = today + timedelta(days=180)
        
        stdate_str = yesterday.strftime('%Y%m%d')
        eddate_str = six_months_later.strftime('%Y%m%d')
        print(f"[INFO] 수집 기간: {stdate_str} ~ {eddate_str}")

        api_key = os.getenv("KOPIS_API_KEY")
        if not api_key:
            raise ValueError("시스템 환경변수 누락: KOPIS_API_KEY를 찾을 수 없습니다.")

        # 2. 크롤링 파이프라인 가동
        crawler = KopisCrawler(api_key=api_key) 
        temp_csv = 'kopis_classic_data.csv' 
        
        print("[INFO] Step 1: KOPIS API 신규/변경 데이터 수집 진행 중...")
        crawler.run(stdate=stdate_str, eddate=eddate_str, output_filename=temp_csv)
        
        # 3. ETL 파이프라인 가동
        print("[INFO] Step 2: 수집 데이터 정제 및 DB UPSERT 진행 중...")
        run_etl_process()
        
        print(f"[INFO] 일일 배치 작업 정상 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
    except Exception as e:
        print(f"[ERROR] 배치 작업 실패: {e}")

def run_production_scheduler():
    """운영 환경 스케줄러: 매일 02:00 실행"""
    schedule.every().day.at("02:00").do(daily_batch_job)
    print("[SYSTEM] KOPIS 자동화 스케줄러 가동 (운영 모드: 매일 02:00 대기 중)")
    
    # 프로세스 점유율 최소화를 위해 60초 주기로 스케줄 확인
    while True:
        schedule.run_pending()
        time.sleep(60)

def run_test_scheduler():
    """테스트 환경 스케줄러: 1분 주기 실행"""
    schedule.every(1).minutes.do(daily_batch_job)
    print("[SYSTEM] KOPIS 자동화 스케줄러 가동 (테스트 모드: 1분 주기 대기 중)")
    
    # 1분 단위 스케줄이므로 검사 주기를 1초로 단축
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    # 1. 운영 환경 가동 (기본값)
    run_production_scheduler()
    
    # 2. 테스트 환경 가동 (필요 시 위의 운영 환경 함수를 주석 처리하고 아래 주석 해제)
    # run_test_scheduler()