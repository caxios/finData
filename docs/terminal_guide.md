# 터미널 명령어 가이드

프로젝트 루트 디렉토리(`finData/`)에서 실행하는 것을 기준으로 합니다.

---

## 1. 다중회사 주요계정 (Multi-Company Accounts)

`data/multi_company_accounts/` 폴더에 CSV가 생성됩니다.

```powershell
# 자동차 섹터 (기본값)
python application.py --only accounts

# 반도체 섹터
python application.py --only accounts -w semi_companies.json

# 조선 섹터
python application.py --only accounts -w ship_companies.json
```

---

## 2. 다중회사 주요 재무지표 (Multi-Company Indicators)

`data/multi_company_indicators/` 폴더에 CSV가 생성됩니다.

```powershell
# 자동차 섹터 (기본값)
python application.py --only indicators

# 반도체 섹터
python application.py --only indicators -w semi_companies.json

# 조선 섹터
python application.py --only indicators -w ship_companies.json
```

---

## 3. 단일회사 전체 재무제표 (Single Company Statements)

`data/single_company_statements/` 폴더에 기업별 CSV가 생성됩니다.

```powershell
# 자동차 섹터 전체 기업
python application.py --only statements

# 반도체 섹터 전체 기업
python application.py --only statements -w semi_companies.json

# 특정 기업 하나만
python application.py --only statements -c 삼성전자
```

---

## 4. 정기보고서 주요정보 (Report Main Info)

`data/report_main_info/` 폴더에 기업별 CSV가 생성됩니다.

```powershell
# 자동차 섹터 전체 기업
python application.py --only reports

# 특정 기업 하나만
python application.py --only reports -c 삼성전자
```

---

## 5. 여러 모듈 동시 실행

```powershell
# accounts + indicators 동시 실행
python application.py --only accounts,indicators

# 모든 모듈 실행 (기본값)
python application.py

# 특정 기업에 대해 모든 모듈 실행
python application.py -c 삼성전자
```

---

## 6. 분기별 주식 수익률 (Quarterly Stock Returns)

프로젝트 루트에 `quarterly_returns_{sector}.csv`가 생성됩니다.

> **사전 조건**: `data/multi_company_indicators/` 폴더에 각 섹터별 지표 CSV가 먼저 존재해야 합니다 (위 2번 참조).

```powershell
python fetch_quarterly_returns.py
```

이 명령은 3개 섹터(car, semi, ship)를 한꺼번에 처리하며 별도의 인자가 없습니다.

---

## 7. 재무 비율 계산 (Financial Ratios)

`data/company_ratios/` 폴더에 섹터별 비율 CSV가 생성됩니다.

> **사전 조건**: `data/company_accounts_filled/` 폴더에 결측치가 보완된 재무 계정 CSV(`car_acnt_filled.csv`, `semi_acnt_filled.csv`, `ship_acnt_filled.csv`)가 먼저 존재해야 합니다.

```powershell
python OpenDart/utils/calculate_ratios.py
```

---

## 8. 기업 고유번호 매핑 (Corp Code Build)

`companies_json/` 폴더에 `*_corp_code.json` 파일들이 생성됩니다.

> **사전 조건**: `companies_json/auto_corp_cache.json` 캐시 파일이 존재해야 합니다.

```powershell
python OpenDart/utils/build_corp_codes.py
```

---

## 옵션 요약

| 옵션 | 축약 | 설명 |
|---|---|---|
| `--only` | `-o` | 실행할 모듈 선택 (`accounts`, `indicators`, `statements`, `reports`) |
| `--whitelist` | `-w` | 기업 목록 파일 (`car_companies.json`, `semi_companies.json`, `ship_companies.json`) |
| `--company` | `-c` | 단일 기업명 지정 (예: `삼성전자`) |

## 데이터 수집 순서 (권장)

전체 파이프라인을 처음부터 돌릴 경우 아래 순서를 따르세요:

```
1. python application.py --only accounts -w car_companies.json
2. python application.py --only accounts -w semi_companies.json
3. python application.py --only accounts -w ship_companies.json
4. python application.py --only indicators -w car_companies.json
5. python application.py --only indicators -w semi_companies.json
6. python application.py --only indicators -w ship_companies.json
7. (결측치 보완 작업 수행)
8. python OpenDart/utils/calculate_ratios.py
9. python fetch_quarterly_returns.py
```
