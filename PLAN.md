# 작업 계획서 (PLAN)

> 다른 AI 도구에서 이어서 작업할 때: **"PLAN.md 읽고 진행 상황 체크리스트에서 아직 안 한 단계부터 진행해줘"** 라고 요청하세요.
> 과제 원문: `docs/클라우드MLOps_대체실습과제_안내문과_평가기준.pdf`

## 0. 작업 규칙
- **git commit/push는 사용자가 직접 한다.** AI는 파일만 수정하고, 단계가 끝날 때마다 커밋 메시지를 제안한다.
- AWS 키, 토큰, 계정 ID 같은 비밀 값은 코드, 로그, 캡처, Git 이력에 절대 넣지 않는다.
- 로그는 사람이 손으로 쓰지 않고 **스크립트가 자동으로 남긴다.**
- README의 "참고 자료와 본인 구현 부분"에 AI 도구를 사용한 범위를 적는다.
- **커밋 메시지 컨벤션**: `feat` / `fix` / `docs` / `chore` / `test` / `refactor`

## 1. 과제 요약
주제를 정해 ML 서비스를 만들고, AWS에서 실제로 실행한 결과를 공개 GitHub 저장소(main 브랜치)로 제출한다.
평가는 성능이나 디자인이 아니라 **실행 증거, 기록, 재현성** 위주로 한다.

| 항목 | 배점 |
|---|---|
| 목적과 데이터 및 모델 | 15 |
| 클라우드 구현과 실행 | 25 |
| 결과 평가 | 20 |
| 실행 및 버전 관리 | 10 |
| 오류 조사와 복구 | 15 |
| 재실행과 인계 | 10 |
| 권한과 비용 및 자원 | 5 |

## 2. 주제: 날씨에 따른 시간당 자전거 대여량 예측
- **사용자/목적**: 자전거 대여소 운영자가 시간대와 날씨 예보를 보고 필요한 자전거 대수를 미리 준비한다.
- **입력**: `season`, `mnth`, `hr`, `holiday`, `weekday`, `workingday`, `weathersit`, `temp`, `atemp`, `hum`, `windspeed`
- **출력**: 해당 시간의 예상 대여 대수 (`cnt`, 단위: 대/시간)
- **데이터**: UCI Bike Sharing Dataset `hour.csv` (17,379행, 2011~2012 Washington D.C.)
- **모델**: scikit-learn `RandomForestRegressor` (n_estimators=200, random_state=42)
- **분할**: yr=0(2011) → 학습 8,645행 / yr=1(2012) → 평가 8,734행

## 3. 환경 정보
- **OS**: macOS (Apple Silicon)
- **Python**: 3.14.5 (가상환경: `.venv/`)
- **AWS CLI**: 2.34.48
- **Docker**: 29.1.3
- **AWS 계정**: 학교 계정 (일반 AWS, Learner Lab 아님)
- **AWS 리전**: `ap-northeast-2` (서울)
- **GitHub**: https://github.com/fnzn-02/cloud-mlops-assignment (Public, main 브랜치)
- **IAM 사용자**: `2022100185`

## 4. AWS 구성
```
[로컬] 데이터 다운로드 → 검증/전처리 → 학습 → 평가 → model.joblib
   │ 업로드 (모델 버전 = 파일 SHA256 앞 12자리)
   ▼
[S3] s3://<버킷>/models/<버전>/model.joblib
     s3://<버킷>/runs/<run_id>/... (클라우드 실행 입력/결과)
   │
   ▼
[Lambda, 컨테이너 이미지 (ECR)] 환경변수 MODEL_S3_URI로 모델 로드
   입력 JSON → 입력 검증 → 예측 → 결과 JSON (+ S3에 결과 저장)
   │
   ▼
[로컬 스크립트] aws lambda invoke로 실제 요청 → 응답을 runs/에 기록
```
- **Lambda 설정**: 메모리 1024MB, 타임아웃 30초, x86_64
- **이미지 빌드**: `docker build --platform linux/amd64` (Apple Silicon Mac이므로)
- **실행 역할**: IAM에서 직접 생성 (학교 계정이므로 LabRole 불필요)

## 5. 현재 폴더 구조
```
cloud-mlops-assignment/
├── README.md              ✅ 완성
├── PLAN.md                ✅ 이 파일
├── Makefile               ✅ 완성
├── requirements.txt       ✅ 완성 (버전 고정)
├── .gitignore             ✅ 완성
├── .env.example           ✅ 완성
├── config/config.yaml     ✅ 완성
├── src/
│   ├── data.py            ✅ 완성 (다운로드, SHA256, 검증, 분할)
│   ├── train.py           ✅ 완성 (학습, 모델 저장, 버전 계산)
│   ├── evaluate.py        ✅ 완성 (MAE/RMSE, 오답 분석)
│   ├── run_log.py         ✅ 완성 (실행 기록 공통 함수)
│   └── pipeline.py        ✅ 완성 (단계별 실행, 실패 시 중단)
├── service/
│   ├── app.py             ❌ 미완성 ← 다음 작업
│   └── Dockerfile         ❌ 미완성 ← 다음 작업
├── scripts/
│   ├── deploy.sh          ❌ 미완성
│   ├── invoke.sh          ❌ 미완성
│   └── cleanup.sh         ❌ 미완성
├── tests/
│   ├── test_inputs/       ❌ 미완성
│   └── test_service.py    ❌ 미완성
├── results/
│   ├── metrics.json       ✅ 자동 생성됨
│   └── error_analysis.md  ✅ 자동 생성됨
├── runs/                  ✅ 자동 생성 중 (data/train/evaluate 기록 있음)
└── docs/
    ├── data.md            ✅ 완성
    ├── cloud.md           ❌ 미완성
    ├── incident.md        ❌ 미완성
    ├── rerun.md           ❌ 미완성
    └── cost_and_cleanup.md ❌ 미완성
```

## 6. 실행 결과 (오늘 완료)
```
데이터: 17,379행, 결측치/이상값 0건, SHA256: e03de4ee4ef4dc376ac6e04bf829673c6269e8eba5c60fa121640fa2f829504f
모델 버전: 8b6cf2669bbe

평가 결과:
  모델 (RandomForest)   — MAE: 88.78,  RMSE: 125.22  ✅ 최고
  베이스라인 (hr별 평균) — MAE: 118.16, RMSE: 174.27
  베이스라인 (전체 평균) — MAE: 168.25, RMSE: 227.81
```

## 7. 앞으로 해야 할 작업 (우선순위 순)

### ❌ Step 6: Lambda 서비스 구현
**파일**: `service/app.py`, `service/Dockerfile`

`service/app.py` 구현 내용:
- Lambda handler 함수
- 시작 시 S3에서 model.joblib 로드 (환경변수 `MODEL_S3_URI` 사용)
- 입력 검증: 필수 필드 누락 → 400, 범위 밖 → 400, 타입 오류 → 400
- 예측 후 결과를 S3 `runs/<run_id>/output.json` 에 저장
- 응답에 `model_version` 포함

`service/Dockerfile` 구현 내용:
```dockerfile
FROM public.ecr.aws/lambda/python:3.11
# platform: linux/amd64 (Apple Silicon Mac에서 빌드할 때 주의)
```

**테스트 입력 파일** (`tests/test_inputs/`):
- `normal_01.json` ~ `normal_03.json`: 정상 입력 3건 이상
- `error_missing.json`: 필수 필드 누락
- `error_range.json`: 범위 밖 값 (hum > 1.0 등)
- `error_type.json`: 타입 오류 (문자열 입력)

`tests/test_service.py`: 로컬 handler 직접 호출 테스트

### ❌ Step 7: 클라우드 배포
**파일**: `scripts/deploy.sh`, `docs/cloud.md`

`scripts/deploy.sh` 순서:
1. S3 버킷 생성 (`aws s3 mb`)
2. 모델 S3 업로드 (`aws s3 cp`)
3. ECR 저장소 생성 (`aws ecr create-repository`)
4. Docker 이미지 빌드 (`--platform linux/amd64`)
5. ECR push
6. Lambda 함수 생성/업데이트 (`aws lambda create-function` 또는 `update-function-code`)
7. 환경변수 설정 (`MODEL_S3_URI`)

**`.env`에 필요한 값** (사용자가 직접 채워야 함):
```
BUCKET_NAME=학생이-정할-버킷-이름
```

### ❌ Step 8: 오류 재현과 복구
**파일**: `docs/incident.md`

시나리오: **잘못된 모델 경로**
1. `MODEL_S3_URI`를 존재하지 않는 경로로 설정해 Lambda 배포
2. 정상 입력으로 호출 → 실패 확인 (CloudWatch 로그 저장)
3. 원인 확인: `aws s3 ls`로 실제 경로 비교
4. 수정: 올바른 경로로 고치고 재배포
5. 같은 요청 재실행 → 성공 로그 저장
6. `docs/incident.md`에 전 과정 기록

**`scripts/invoke.sh`도 이 단계에서 완성**:
- 정상 입력 3건 호출 → 200 응답 확인
- 비정상 입력 호출 → 400 응답 확인
- 각 결과를 `runs/`에 저장

### ❌ Step 9: 새 폴더 재실행
**파일**: `docs/rerun.md`

```bash
cd /tmp
git clone https://github.com/fnzn-02/cloud-mlops-assignment.git rerun-test
cd rerun-test
# README 절차대로 실행
make all
```
결과를 `docs/rerun.md`에 기록

### ❌ Step 10: 자원 정리
**파일**: `scripts/cleanup.sh`, `docs/cost_and_cleanup.md`

`cleanup.sh` 순서:
1. Lambda 함수 삭제
2. ECR 저장소 삭제
3. S3 객체 및 버킷 삭제
4. CloudWatch 로그 그룹 삭제
5. 각 `list`/`describe` 조회 결과 저장

### ❌ Step 11: 최종 점검
```bash
# 비밀 값 검색
git log -p | grep -iE "key|token|secret|password"

# 로그아웃 상태에서 저장소 접근 확인 (시크릿 모드 브라우저)
# https://github.com/fnzn-02/cloud-mlops-assignment

# main 브랜치 확인
git branch
```

## 8. 커밋 가이드 (남은 작업용)

| 작업 완료 후 | 커밋 메시지 |
|---|---|
| service/app.py + Dockerfile | `feat(service): add Lambda handler and Dockerfile` |
| tests/ | `test: add local service tests and test inputs` |
| scripts/deploy.sh | `feat(deploy): add S3/ECR/Lambda deploy script` |
| scripts/invoke.sh | `feat(invoke): add Lambda invoke and result logging script` |
| docs/cloud.md | `docs: add cloud configuration and execution log` |
| docs/incident.md | `docs: add error reproduction and recovery log` |
| scripts/cleanup.sh + docs/cost_and_cleanup.md | `chore: add cleanup script and cost/resource log` |
| docs/rerun.md | `docs: add rerun verification log` |

## 9. 진행 상황 체크리스트
- [x] 1. 환경 확인: Python 3.14.5, AWS CLI 2.34.48, Docker 29.1.3
- [x] 2. 저장소 초기화: git init, .gitignore, requirements.txt, README.md, Makefile
- [x] 3. 데이터: 다운로드, SHA256 확인, 검증(이상값 0건), 분할, `docs/data.md`
- [x] 4. 학습과 평가: RandomForest vs 베이스라인, `results/metrics.json`, 오답 분석
- [x] 5. 실행 기록: `run_log.py`, `pipeline.py` (실패 시 중단), `runs/*.json` 자동 생성
- [ ] 6. 서비스: Lambda handler (`service/app.py`), 입력 검증, 로컬 테스트
- [ ] 7. 클라우드 배포: S3 업로드, ECR push, Lambda 생성, 실제 호출, `docs/cloud.md`
- [ ] 8. 오류 재현과 복구: `docs/incident.md`, `scripts/invoke.sh`
- [ ] 9. 새 폴더 재실행: clone → README대로 실행 → `docs/rerun.md`
- [ ] 10. 자원 정리: `scripts/cleanup.sh`, `docs/cost_and_cleanup.md`
- [ ] 11. 최종 점검: 비밀 값 검색, 로그아웃 상태에서 저장소 확인, main 브랜치 확인
