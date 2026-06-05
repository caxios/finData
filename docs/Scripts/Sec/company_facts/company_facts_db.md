# `company_facts_db.py`

## 개요
SEC EDGAR CompanyFacts JSON 데이터를 SQLite 데이터베이스에 저장하고 관리하는 DB 레이어 모듈입니다.

## 주요 기능
1. **`init_db(db_path)`**: 데이터베이스 스키마를 초기화합니다.
   - `companies` 테이블: `cik`(PK), `ticker`, `entity_name`.
   - `company_facts` 테이블: XBRL 팩트를 평탄화(Flatten)하여 저장. 각 행은 하나의 관측값(taxonomy, concept, unit, period_end, val 등).
   - `UNIQUE(cik, taxonomy, concept, unit, period_end, accn)` 제약으로 중복 삽입 방지.
   - `idx_facts_lookup` 인덱스로 조회 성능 최적화.

2. **`save_company_facts(facts_data, db_path, ticker)`**: CompanyFacts JSON을 평탄화하여 SQLite에 삽입.
   - SEC JSON의 중첩 구조(`facts → taxonomy → concept → units → observations`)를 1차원 행으로 변환.
   - `INSERT OR IGNORE`로 기존 데이터와 충돌 시 건너뜀.
   - `(inserted, skipped)` 튜플을 반환.

## 역할
XBRL 재무 팩트의 영속 저장소(Persistence Layer)로서, 한 번 SEC에서 가져온 데이터를 로컬에 캐싱하여 반복적인 API 호출 없이 빠르게 조회할 수 있게 합니다.
