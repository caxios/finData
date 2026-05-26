import urllib.request
import json
from bs4 import BeautifulSoup
import time
import os

output_path = os.path.join(os.path.dirname(__file__), 'docs', 'opendarts', 'main_info.txt')

# 오픈다트 각 API들의 가이드 가져오기
# First, read lines 1 to 41 and overwrite the file with just those lines
with open(output_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

with open(output_path, 'w', encoding='utf-8') as f:
    f.writelines(lines[:41])
    f.write("\n\n")

api_ids = list(range(2020018, 2020054))

output_lines = []

for idx, api_id in enumerate(api_ids):
    url = f"https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId={api_id}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        html = urllib.request.urlopen(req).read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        time.sleep(1)
        continue
        
    soup = BeautifulSoup(html, 'html.parser')
    
    # Get Title
    title_div = soup.find('div', class_='leftWrap')
    title = title_div.text.strip().replace(' 개발가이드', '') if title_div else str(api_id)
    
    output_lines.append(f"## {title}")
    
    # Get API URL (json)
    api_url = ""
    basic_info_tb = soup.find('caption', string='기본 정보')
    if basic_info_tb:
        basic_table = basic_info_tb.find_parent('table')
        rows = basic_table.find('tbody').find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 4 and 'JSON' in cols[3].text:
                api_url = cols[1].text.strip()
                break
    
    output_lines.append(f"> api : {api_url}")
    
    # Get Request Params
    req_desc_tb = soup.find('caption', string='요청 인자')
    req_params_list = []
    if req_desc_tb:
        req_table = req_desc_tb.find_parent('table')
        # headers
        headers = [th.text.strip() for th in req_table.find('thead').find_all('th')]
        req_params_list.append("\t".join(headers))
        
        rows = req_table.find('tbody').find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            col_texts = [col.text.strip().replace('\n', ' ').replace('\r', '') for col in cols]
            req_params_list.append("\t".join(col_texts))
            
    # Example Request URL construction
    example_url = api_url + "?crtfc_key=<API KEY>"
    for row in req_params_list[1:]:
        parts = row.split('\t')
        if len(parts) > 0:
            key = parts[0]
            if key != 'crtfc_key':
                example_url += f"&{key}="
                
    output_lines.append(f"> example of api request url : {example_url}")
    
    output_lines.append("> request description : ")
    output_lines.append("[")
    for r in req_params_list:
        output_lines.append(r)
    output_lines.append("]")
    
    # Get Response Result
    res_desc_tb = soup.find('caption', string='응답 결과')
    res_params_list = []
    if res_desc_tb:
        res_table = res_desc_tb.find_parent('table')
        headers = [th.text.strip() for th in res_table.find('thead').find_all('th')]
        res_params_list.append("\t".join(headers))
        
        rows = res_table.find('tbody').find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            col_texts = [col.text.strip().replace('\n', ' ').replace('\r', '') for col in cols]
            res_params_list.append("\t".join(col_texts))
            
    output_lines.append("> response description : ")
    output_lines.append("[")
    for r in res_params_list:
        output_lines.append(r)
    output_lines.append("]")
    output_lines.append("\n")
    
    print(f"Processed {title} ({api_id})")
    time.sleep(0.5)

with open(output_path, 'a', encoding='utf-8') as f:
    f.write("\n".join(output_lines) + "\n")

print(f"Data appended to {output_path}")
