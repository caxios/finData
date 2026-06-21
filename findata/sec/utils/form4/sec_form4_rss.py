import requests
from bs4 import BeautifulSoup
import time

from findata.sec.const import SEC_USER_AGENT

def fetch_form4():
    # 1. SEC Atom Feed URL (type=4로 일차적으로 걸러서 가져옵니다)
    url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&owner=include&count=100&output=atom"

    # 2. 필수 헤더 설정 (SEC 규정: 이름과 이메일 필수)
    # User-Agent는 findata.sec.const.SEC_USER_AGENT에서 가져옵니다
    # (FINDATA_SEC_USER_AGENT 환경변수로 재정의 가능).
    headers = {
        "User-Agent": SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    try:
        # Append a timestamp to defeat any intermediary cache on the Atom feed.
        response = requests.get(f"{url}&_={int(time.time())}", headers=headers)
        response.raise_for_status() # HTTP 에러 발생 시 예외 처리

        # 3. XML 파싱
        soup = BeautifulSoup(response.content, 'xml')
        entries = soup.find_all('entry')
        
        form4_data = []

        for entry in entries:
            # 4. 폼 타입 추출
            # SEC Atom 피드에서 <category term="4" scheme="http://www.sec.gov/"/> 형태로 제공됨
            category_tag = entry.find('category')
            if not category_tag:
                continue
                
            form_type = category_tag.get('term', '')

            # 5. 정확히 '4' 또는 '4/A'만 필터링 (이상한 파일 제외)
            if form_type in ['4', '4/A']:
                title = entry.title.text if entry.title else "No Title"
                link = entry.link['href'] if entry.link else "No Link"
                updated = entry.updated.text if entry.updated else "No Date"
                
                form4_data.append({
                    'title': title,
                    'form_type': form_type,
                    'link': link,
                    'updated': updated
                })
        
        # 결과 출력 (이 부분을 데이터베이스 저장이나 텔레그램 알림 등으로 변경하시면 됩니다)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {len(form4_data)}개의 Form 4 문서를 수집했습니다.")
        for item in form4_data[:50]: # 너무 길어질 수 있으니 최근 5개만 출력해 봅니다
            print(f"- {item['form_type']} | {item['title']} | {item['link']}")
            
        return form4_data

    except Exception as e:
        print(f"데이터를 가져오는 중 오류가 발생했습니다: {e}")
        return []
