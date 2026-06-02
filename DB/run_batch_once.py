import os
import sys
from daily_scheduler import daily_batch_job

if __name__ == "__main__":
    print("🚀 [GitHub Actions] 1회성 일일 KOPIS 배치 작업을 시작합니다.")
    try:
        daily_batch_job()
        print("✅ 배치 작업이 성공적으로 종료되었습니다.")
        sys.exit(0) # 정상 종료 신호
    except Exception as e:
        print(f"❌ 배치 작업 중 치명적 오류 발생: {e}")
        sys.exit(1) # 에러 발생 신호 (깃허브 액션에 실패를 알림)