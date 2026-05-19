import requests
import xml.etree.ElementTree as ET
import pandas as pd
import time
import re
import os
from dotenv import load_dotenv

class KopisCrawler:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "http://www.kopis.or.kr/openApi/restful"
        self.venue_cache = {}

    def merge_base_data(self, main_excel, append_excel):
        """
        [0단계] 지정된 두 엑셀 파일을 읽어 병합(concat)하고 영문 스키마로 매핑합니다.
        """
        print("\n=== [0단계] 베이스 데이터(Excel) 병합 및 컬럼 표준화 시작 ===")
        if not os.path.exists(main_excel) or not os.path.exists(append_excel):
            print(f"오류: {main_excel} 또는 {append_excel} 파일이 존재하지 않습니다.")
            return None
            
        try:
            df_main = pd.read_excel(main_excel)
            df_append = pd.read_excel(append_excel)
            merged_df = pd.concat([df_main, df_append], ignore_index=True)
            
            # 한글 컬럼명을 DB 스키마(영문)로 완벽 매핑
            column_mapping = {
                '공연ID': 'kopis_id', '공연명': 'title', '시작일': 'start_date',
                '종료일': 'end_date', '공연장소': 'venue', '지역': 'region',
                '장르': 'genre', '출연진': 'artists', '런타임': 'runtime',
                '관람연령': 'age_rating', '티켓가격': 'ticket_price',
                '소개글_프로그램': 'raw_program_info', '상세이미지_URL': 'detail_image_url',
                '포스터': 'poster_url', '예매처_링크': 'reservation_url', '상태': 'status'
            }
            merged_df.rename(columns=column_mapping, inplace=True)
            
            # 날짜 형식 표준화
            if 'start_date' in merged_df.columns:
                merged_df['start_date'] = merged_df['start_date'].apply(self._format_date)
            if 'end_date' in merged_df.columns:
                merged_df['end_date'] = merged_df['end_date'].apply(self._format_date)
            
            if 'kopis_id' in merged_df.columns:
                before_len = len(merged_df)
                merged_df.drop_duplicates(subset=['kopis_id'], keep='last', inplace=True)
                print(f"중복 제거: {before_len}건 -> {len(merged_df)}건")
                
            print("베이스 데이터 병합 및 스키마 변환 완료!")
            return merged_df
        except Exception as e:
            print(f"병합 중 오류 발생: {e}")
            return None

    def _get_with_retry(self, url, params, max_retries=3, backoff_factor=2):
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=35)
                if response.status_code == 200:
                    return response
                else:
                    print(f"  [API 상태 오류] 코드: {response.status_code} (시도: {attempt+1}/{max_retries})")
            except requests.exceptions.RequestException as e:
                print(f"  [네트워크/타임아웃 오류] (시도: {attempt+1}/{max_retries})")
                
            if attempt < max_retries - 1:
                sleep_time = backoff_factor * (attempt + 1)
                print(f"  ... {sleep_time}초 대기 후 재시도합니다.")
                time.sleep(sleep_time)
        return None

    def _clean_text(self, text):
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _format_date(self, date_str):
        if pd.isna(date_str) or not str(date_str).strip():
            return ""
        # YYYY.MM.DD 또는 타임스탬프를 YYYY-MM-DD 형태로 변환
        date_str = str(date_str).split(' ')[0]
        return date_str.replace('.', '-').strip()

    def get_simple_region(self, address):
        if not address or not str(address).strip():
            return "기타"
        sido = str(address).split()[0]
        mapping = {
            "서울특별시": "서울", "서울시": "서울", "서울": "서울",
            "경기도": "경기", "경기": "경기", "인천광역시": "인천", "인천시": "인천",
            "부산광역시": "부산", "부산시": "부산", "대구광역시": "대구", "대구시": "대구",
            "광주광역시": "광주", "광주시": "광주", "대전광역시": "대전", "대전시": "대전",
            "울산광역시": "울산", "울산시": "울산", "세종특별자치시": "세종", "세종시": "세종",
            "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남",
            "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남", "경상북도": "경북",
            "경상남도": "경남", "제주특별자치도": "제주", "제주도": "제주"
        }
        return mapping.get(sido, sido[:2] if len(sido) >= 2 else sido)

    def fetch_performances(self, stdate, eddate, shcate='CCCA'):
        print("\n=== [1단계] 전체 클래식 공연 목록 수집 시작 ===")
        url = f"{self.base_url}/pblprfr"
        performance_list = []
        page = 1
        
        while True:
            params = {
                'service': self.api_key, 'stdate': stdate, 'eddate': eddate,
                'cpage': str(page), 'rows': '100', 'shcate': shcate
            }
            response = self._get_with_retry(url, params=params)
            if not response:
                print("목록 수집 중 최대 재시도 횟수 초과. 중단합니다.")
                break
            
            root = ET.fromstring(response.content)
            db_elements = root.findall('db')
            if not db_elements:
                break
            
            for db in db_elements:
                performance_list.append({
                    'kopis_id': db.findtext('mt20id'),
                    'title': self._clean_text(db.findtext('prfnm')),
                    'start_date': self._format_date(db.findtext('prfpdfrom')),
                    'end_date': self._format_date(db.findtext('prfpdto')),
                    'venue': self._clean_text(db.findtext('fcltynm')),
                    'genre': db.findtext('genrenm'),
                    'poster_url': db.findtext('poster').replace('http://', 'https://') if db.findtext('poster') else '',
                    'status': db.findtext('prfstate')
                })
            
            print(f"목록 수집 중... {page}페이지 완료 (누적: {len(performance_list)}건)")
            page += 1
            time.sleep(0.5)
            
        return pd.DataFrame(performance_list)

    def fetch_venue_region(self, mt10id):
        if not mt10id: return "지역미상"
        if mt10id in self.venue_cache: return self.venue_cache[mt10id]
        
        url = f"{self.base_url}/prfplc/{mt10id}"
        res = self._get_with_retry(url, params={'service': self.api_key})
        if res is not None:
            root = ET.fromstring(res.content)
            db = root.find('db')
            if db is not None:
                region = self.get_simple_region(db.findtext('adres'))
                self.venue_cache[mt10id] = region
                time.sleep(0.1)
                return region
                
        self.venue_cache[mt10id] = "지역미상"
        return "지역미상"

    def fetch_performance_details(self, id_list):
        total = len(id_list)
        print(f"\n=== [2단계] 총 {total}개 공연 상세 정보 수집 시작 ===")
        detail_list = []
        
        for i, mt20id in enumerate(id_list):
            url = f"{self.base_url}/pblprfr/{mt20id}"
            response = self._get_with_retry(url, params={'service': self.api_key})
            if response is not None:
                root = ET.fromstring(response.content)
                db = root.find('db')
                if db is not None:
                    mt10id = db.findtext('mt10id')
                    region = self.fetch_venue_region(mt10id)
                    
                    sty_text = self._clean_text(db.findtext('sty'))
                    if not sty_text: sty_text = "상세 프로그램은 하단 상세 이미지를 참조해주세요."
                        
                    image_urls = [styurl.text.replace('http://', 'https://') 
                                  for styurl in db.findall('styurls/styurl') if styurl.text]
                    booking_links = [f"{relate.findtext('relatenm')}({relate.findtext('relateurl')})" 
                                     for relate in db.findall('relates/relate') 
                                     if relate.findtext('relatenm') and relate.findtext('relateurl')]
                    
                    detail_list.append({
                        'kopis_id': mt20id,
                        'artists': self._clean_text(db.findtext('prfcast')),
                        'runtime': self._clean_text(db.findtext('prfruntime')),
                        'age_rating': self._clean_text(db.findtext('prfage')),
                        'ticket_price': self._clean_text(db.findtext('pcseguidance')),
                        'raw_program_info': sty_text,
                        'detail_image_url': ", ".join(image_urls),
                        'reservation_url': ", ".join(booking_links) if booking_links else "예매처 정보 없음",
                        'region': region
                    })
            
            time.sleep(0.3)
            if (i + 1) % 50 == 0 or (i + 1) == total:
                print(f"상세 정보 수집 진행률: {i + 1} / {total} 완료")
                
        return pd.DataFrame(detail_list)

    def run(self, stdate, eddate, base_df=None, output_filename='kopis_unified_dataset.csv'):
        list_df = self.fetch_performances(stdate, eddate)
        if list_df.empty:
            print("수집된 데이터가 없습니다. 베이스 데이터만 저장합니다.")
            final_df = base_df if base_df is not None else pd.DataFrame()
        else:
            detail_df = self.fetch_performance_details(list_df['kopis_id'].tolist())
            print("\n=== [3단계] 데이터 병합 및 CSV 저장 ===")
            crawled_df = pd.merge(list_df, detail_df, on='kopis_id', how='left')
            
            if base_df is not None and not base_df.empty:
                final_df = pd.concat([base_df, crawled_df], ignore_index=True)
                final_df.drop_duplicates(subset=['kopis_id'], keep='last', inplace=True)
            else:
                final_df = crawled_df
        
        if not final_df.empty:
            final_df.to_csv(output_filename, index=False, encoding='utf-8-sig')
            print(f"최종 통합 수집 완료! 총 {len(final_df)}건 -> '{output_filename}'")

if __name__ == "__main__":
    load_dotenv()

    api_key = os.getenv("KOPIS_API_KEY")
    if not api_key:
        raise ValueError(".env 파일에서 KOPIS_API_KEY를 찾을 수 없습니다.")

    crawler = KopisCrawler(api_key=api_key)
