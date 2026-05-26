"""
# 처음 변수 선택 단계에서 라쏘나 랜덤포레스트 둘 다 해보는 것도 좋음.
일단은 라쏘로 진행

"""

import pandas as pd
import numpy as np
from sklearn.linear_model import Lasso
from sklearn.preprocessing import StandardScaler

# 1. 데이터 불러오기
df = pd.read_csv('car_companies2_indicators.csv')

# 2. 타겟 변수 설정 (예측하고자 하는 Y값 지정)
# 모델이 예측할 목적 변수를 지정합니다. (예: 'ROE', '순이익률' 등)
target_col = 'ROE' 

# X(독립변수)와 y(종속변수) 분리
# 분석에 불필요한 회사코드, 기간 등의 식별자와 종속변수를 독립변수에서 제외합니다.
X = df.drop(columns=['corp_code', 'stock_code', 'period', target_col])
y = df[target_col]

# 3. 결측치(NaN) 처리
# 3-1. 결측치가 전체 데이터의 50% 이상인 열(변수)은 모델에 악영향을 주므로 제거합니다.
threshold = len(df) * 0.5
X = X.dropna(axis=1, thresh=threshold)

# 3-2. 우리가 예측해야 할 정답(y) 자체가 비어있는 행(Row)은 학습할 수 없으므로 삭제합니다.
valid_idx = y.dropna().index
X = X.loc[valid_idx]
y = y.loc[valid_idx]

# 3-3. 남은 X 데이터의 결측치는 각 변수의 '중앙값'으로 대체하여 채워줍니다.
X = X.fillna(X.median())

# 4. 데이터 스케일링 (필수)
# 라쏘는 단위 크기에 민감하므로, 평균을 0, 분산을 1로 맞추는 표준화를 진행합니다.
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# 5. 라쏘(Lasso) 모델 적합
# alpha 값이 클수록 더 강력한 규제가 걸려 더 많은 변수의 계수가 0이 됩니다.
lasso = Lasso(alpha=0.1, random_state=42)
lasso.fit(X_scaled, y)

# 6. 선택된 변수 추출
# 모델 학습 결과, 회귀 계수(coef_)가 0이 살아남은 유의미한 변수들을 골라냅니다.
selected_features = X.columns[lasso.coef_ != 0]

print(f"전처리 후 전체 변수 개수: {len(X.columns)}개")
print(f"라쏘가 선택한 핵심 변수 개수: {len(selected_features)}개")
print("\n[선택된 변수 목록]")
print(selected_features.tolist())