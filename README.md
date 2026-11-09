# 자전거 대여량 예측 ML 서비스 (Cloud MLOps 과제)

## 목적
날씨·시간 정보를 입력받아 시간당 자전거 대여량을 예측하는 ML 서비스.
자전거 대여소 운영자가 날씨 예보를 보고 필요한 자전거 대수를 미리 준비하는 데 활용한다.

- **입력**: 계절, 월, 시간, 공휴일 여부, 날씨, 기온, 습도, 풍속 등
- **출력**: 예상 대여 대수 (대/시간)
- **데이터**: UCI Bike Sharing Dataset — hour.csv (17,379행, 2011~2012, Washington D.C.)
- **모델**: scikit-learn RandomForestRegressor

## 클라우드 구성
```
로컬 (학습/평가) → S3 (모델 저장) → ECR (컨테이너) → Lambda (예측 서비스)
```
- **리전**: ap-northeast-2 (서울)
- **선택 이유**: 요청 시에만 실행되는 서비스라 Lambda가 적합. 상시 서버 불필요, 비용 최소화.

## 환경 요구사항
- Python 3.10+
- AWS CLI 설정 완료 (`aws configure`)
- Docker 설치

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.env.example`을 복사해 `.env`를 만들고 `BUCKET_NAME` 등을 채운다:

```bash
cp .env.example .env
```

## 실행 방법

```bash
# 전체 파이프라인 (데이터 → 학습 → 평가)
make all

# 단계별 실행
make data       # 데이터 다운로드 및 검증
make train      # 모델 학습
make evaluate   # 평가 및 지표 저장
make deploy     # S3 업로드 + ECR push + Lambda 배포
make invoke     # Lambda 실제 호출 테스트
make clean-cloud  # 클라우드 자원 삭제
```

## 결과 위치
| 파일 | 내용 |
|---|---|
| `results/metrics.json` | MAE / RMSE (모델 vs 베이스라인) |
| `results/error_analysis.md` | 오답 1건 분석 |
| `runs/` | 단계별 실행 기록 (자동 생성) |
| `docs/cloud.md` | 클라우드 구성 및 실행 기록 |
| `docs/incident.md` | 오류 재현과 복구 |
| `docs/rerun.md` | 재실행 기록 |
| `docs/cost_and_cleanup.md` | 비용 및 자원 정리 |

## 데이터 정규화 단위
원본 데이터에서 이미 0~1로 정규화된 값:
- `temp`: 실제 기온 ÷ 41°C
- `atemp`: 체감 기온 ÷ 50°C
- `hum`: 습도 ÷ 100
- `windspeed`: 풍속 ÷ 67 km/h

## 권한 (AWS IAM)
필요한 최소 권한: S3(읽기/쓰기), ECR(push), Lambda(생성/수정/호출), CloudWatch Logs(조회)

## 참고 자료와 본인 구현 부분
- **데이터 출처**: [UCI Bike Sharing Dataset](https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset) — CC BY 4.0
- **AI 도구 사용 범위**: 코드 구조 설계 및 boilerplate 작성에 Antigravity(AI) 활용.
  데이터 분할 기준, 모델 선택, 오류 시나리오 설계는 직접 판단.
