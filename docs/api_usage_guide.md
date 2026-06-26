# 사내 비공개 API 사용 및 관리 가이드

이 문서는 RapidAPI 등 외부 서비스를 거치지 않고, 우리 팀원(혹은 나 자신)끼리만 독립적으로 API 서버를 이용하기 위한 가이드라인입니다.

## 1. 관리자(서버 주인)의 역할: API 키 발급 및 관리
새로운 팀원이 합류하거나 새로운 프로젝트를 시작할 때, API 서버에 접근할 수 있는 **전용 열쇠(API 키)** 를 발급해야 합니다.
모든 관리는 관리자 PC의 터미널(VSCode 등)에서 `key_manager.py` 스크립트를 통해 이루어집니다.

### 🔑 새로운 API 키 발급하기
```bash
.venv\Scripts\python.exe key_manager.py create "이메일주소" --label "키 이름(설명)"
```
- **예시**: `.venv\Scripts\python.exe key_manager.py create "teamA@mycompany.com" --label "팀원A 전용 키"`
- **주의**: 발급된 `fd_live_xxxx...` 형태의 키는 화면에 **단 한 번만 표시**됩니다. 즉시 복사해서 팀원에게 안전하게 전달하세요.

### 📋 특정 사용자의 API 키 목록 확인
```bash
.venv\Scripts\python.exe key_manager.py list "이메일주소"
```
- 해당 이메일로 발급된 모든 키의 ID, 라벨, 활성화 상태를 확인할 수 있습니다.

### 🚫 API 키 폐기 (권한 회수)
```bash
.venv\Scripts\python.exe key_manager.py revoke [키ID번호]
```
- 팀원이 퇴사하거나 키가 유출된 경우, 위에서 확인한 `키 ID 번호`를 입력하여 즉시 접속을 차단할 수 있습니다.

---

## 2. 팀원(클라이언트)의 역할: API 호출 및 사용
서버 관리자에게 **"서버 주소"**와 **"API 키"**를 전달받은 팀원은, 서버쪽 코드(`finData` 폴더)가 전혀 필요하지 않습니다. 
본인의 완전히 새로운 프로젝트에서 아래와 같이 호출하여 데이터를 가져다 쓰면 됩니다.

### 📍 필수 정보
- **서버 기본 주소 (Base URL)**: `http://3.107.112.100`
- **인증 방식**: HTTP Header에 `X-API-Key` 값을 넣어서 전송

### 🐍 파이썬(Python) 사용 예시
`requests` 라이브러리를 사용하여 데이터를 가져옵니다.
```python
import requests

# 1. API 엔드포인트 주소 및 파라미터 설정
url = "http://3.107.112.100/v1/api/trades"
params = {
    "ticker": "NVDA",  # 엔비디아
    "limit": 10        # 10개만
}

# 2. 관리자에게 전달받은 API 키를 헤더에 삽입
headers = {
    "X-API-Key": "여기에_발급받은_키_입력"
}

# 3. 데이터 요청 및 출력
response = requests.get(url, params=params, headers=headers)
data = response.json()

print(data)
```

### 🌐 자바스크립트(JavaScript/Node.js) 사용 예시
웹 프론트엔드(React, Vue 등)나 순수 자바스크립트에서 `fetch`를 사용합니다.
```javascript
const url = "http://3.107.112.100/v1/api/trades?ticker=NVDA&limit=10";

fetch(url, {
    method: "GET",
    headers: {
        "X-API-Key": "여기에_발급받은_키_입력"
    }
})
.then(response => response.json())
.then(data => {
    console.log("불러온 데이터:", data);
})
.catch(error => {
    console.error("데이터를 불러오는데 실패했습니다:", error);
});
```

---
💡 **기억해두세요!**
클라우드(AWS)에 띄워둔 서버는 24시간 혼자 돌아가고 있습니다. 질문자님의 관리자 PC가 꺼져 있더라도, 발급받은 API 키만 있다면 언제 어디서든 스마트폰 앱, 웹사이트, 매매 봇 등 모든 새로운 프로젝트에서 위 방식으로 데이터를 끌어다 쓸 수 있습니다!
