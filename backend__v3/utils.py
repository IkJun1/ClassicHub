import re
from typing import Tuple

def parse_ticket_price(price_str: str) -> int:
    """
    문자열 형태의 티켓 가격("R석 100,000원, S석 80,000원")에서 정규식을 이용해 
    가장 낮은 가격(최저가)을 추출하여 int로 반환합니다.
    가격이 없거나 무료인 경우 0을 반환합니다.
    """
    if not price_str:
        return 0
    
    # "전석 무료" 등의 키워드 감지
    if "무료" in price_str:
        return 0
        
    # \d{1,3}(?:,\d{3})* 패턴으로 모든 가격 숫자 추출
    matches = re.findall(r'\d{1,3}(?:,\d{3})*', price_str)
    if not matches:
        return 0
        
    prices = [int(m.replace(',', '')) for m in matches]
    return min(prices) if prices else 0


def parse_runtime(runtime_str: str) -> Tuple[int, int]:
    """
    "1시간 30분(인터미션 15분)" 형태의 문자열에서 
    (총 시간, 인터미션)을 분 단위 정수로 추출하여 반환합니다.
    매칭되지 않을 경우 (0, 0)을 반환합니다.
    """
    if not runtime_str:
        return 0, 0
        
    total_time = 0
    intermission = 0
    
    # 시간 추출 (예: "1시간", "2시간")
    hour_match = re.search(r'(\d+)시간', runtime_str)
    if hour_match:
        total_time += int(hour_match.group(1)) * 60
        
    # 분 추출 (예: "30분", "100분") - 주의: 인터미션의 "15분"과 헷갈리지 않도록 
    # 인터미션이 아닌 일반 분 단위를 찾거나, 단순하게 모든 분 앞의 숫자를 찾되
    # 인터미션 키워드 뒤에 오는 분은 별도로 처리
    
    # 인터미션 처리
    intermission_match = re.search(r'인터미션\s*(\d+)분', runtime_str)
    if intermission_match:
        intermission = int(intermission_match.group(1))
        
    # 시간 표현이 아예 "100분" 형태로만 되어있을 경우
    # "100분 (인터미션 15분)"을 파싱하기 위해, 모든 '숫자+분' 조합을 찾음
    minute_matches = re.finditer(r'(\d+)분', runtime_str)
    for m in minute_matches:
        val = int(m.group(1))
        # 방금 찾은 인터미션의 값이면 skip (중복 합산 방지)
        # 하지만 인터미션이 15분이고 연주시간도 15분일 확률이 희박하고, 
        # 보통 가장 큰 숫자가 총 시간, 아니면 1시간 30분의 30분이 됨.
        # 보다 정확한 것은 "시간" 앞의 숫자를 처리했고, "인터미션" 뒤의 분을 처리했으니,
        # 시간 앞이 아닌 숫자+분을 찾는 것임.
        if intermission_match and m.start() == intermission_match.start(1):
            continue
        total_time += val
        
    return total_time, intermission
