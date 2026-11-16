# 자전거 대여량 예측 ML 서비스 (Cloud MLOps 과제)

## 목적
- **사용자**: 자전거 대여소 운영자
- **목적**: 시간대와 날씨 예보를 보고, 그 시간에 필요한 자전거 대수를 미리 준비한다.
- **입력**: 계절, 월, 시간, 공휴일·요일·근무일 여부, 날씨 상태, 기온, 체감 기온, 습도, 풍속 (11개, 정의는 [`docs/data.md`](docs/data.md))
- **출력**: 해당 시간의 예상 대여 대수 `predicted_cnt` (단위: 대/시간), 모델 버전, 요청 ID
- **데이터**: UCI Bike Sharing Dataset `hour.csv` (17,379행, 2011~2012 Washington D.C., CC BY 4.0)
- **모델**: scikit-learn `RandomForestRegressor` (직접 학습). 2011년으로 학습하고 2012년으로 평가했다.
- **평가**: MAE 88.78 대/시간. 시간대별 평균 베이스라인(118.16)보다 25% 낮다 ([`results/metrics.json`](results/metrics.json))

입력 예시와 응답:
```json
{"season": 2, "mnth": 6, "hr": 17, "holiday": 0, "weekday": 3, "workingday": 1,
 "weathersit": 1, "temp": 0.72, "atemp": 0.6515, "hum": 0.42, "windspeed": 0.1642}
→ {"statusCode": 200, "predicted_cnt": 597.83, "unit": "대/시간", "model_version": "0e16c92e1dd6", ...}
```
잘못된 입력(필드 누락, 범위 밖, 타입 오류, 정답 컬럼 포함 등)은 `statusCode: 400`과 오류 목록을 반환한다.

## 구성
```
로컬: make all (데이터 → 학습 → 평가) → data/model.joblib
  └─ make deploy → S3 (모델 보관본) + ECR (모델 포함 이미지) → Lambda (예측)
  └─ make invoke → Lambda 실제 호출 → runs/ 와 S3 에 결과 기록
```
- AWS `ap-northeast-2`(서울), Lambda 컨테이너 이미지(Python 3.14, x86_64, 1024MB, 30초)
- 구성 선택 이유와 실행 결과: [`docs/cloud.md`](docs/cloud.md)

## 필요한 환경
| 항목 | 버전 (확인한 버전) |
|---|---|
| Python | **3.14** (3.14.5). 로컬 학습과 Lambda 런타임을 같은 버전으로 맞췄다 |
| 라이브러리 | `requirements.txt`에 버전 고정 |
| AWS CLI | v2 (2.34.48) |
| Docker | Docker Desktop **실행 중**이어야 함 (29.1.3). `make deploy`에서 이미지를 빌드한다 |
| OS | macOS (Apple Silicon)에서 확인. 스크립트가 macOS의 `date -r`, `sed -i ''`를 쓴다 |

## 필요한 권한 (AWS)
| 대상 | 권한 |
|---|---|
| S3 버킷 1개 | 생성·삭제, 퍼블릭 접근 차단, 태그, 객체 업로드·삭제 |
| ECR 저장소 1개 | 생성·삭제, 로그인 토큰, 이미지 push·조회 |
| Lambda 함수 1개 | 생성·수정·호출·삭제, 실행 역할 전달(`iam:PassRole`) |
| CloudWatch Logs | 로그 그룹 조회·검색·삭제 |
| Lambda 실행 역할 | CloudWatch Logs 쓰기만 있으면 된다 (모델이 이미지 안에 있어 S3 읽기 불필요) |

학교 계정에서의 제약과 해결(MFA 필수, 역할 생성 불가, 서울 리전만 허용)은 [`docs/cloud.md`](docs/cloud.md) 4절, 비용은 [`docs/cost_and_cleanup.md`](docs/cost_and_cleanup.md)에 있다.

## 설치부터 검증까지

### 1. 설치
```bash
git clone https://github.com/fnzn-02/cloud-mlops-assignment.git
cd cloud-mlops-assignment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 로컬 실행과 검증 (AWS 불필요)
```bash
make all     # 데이터 다운로드·SHA256 검증 → 학습 → 평가 (실패 시 다음 단계 중단)
make test    # Lambda 핸들러 로컬 테스트 9건 (정상 3, 오류 6)
```
- 데이터는 UCI에서 자동으로 내려받는다. 저장소에는 포함하지 않는다.
- 모델 버전 `0e16c92e1dd6`, MAE 88.78이 나오면 정상이다 (재현 확인: [`docs/rerun.md`](docs/rerun.md)).

### 3. 클라우드 자원 설정
```bash
cp .env.example .env
sed -i '' 's/<학번>/본인학번/g' .env     # 자원 이름(버킷·함수·ECR)과 owner 태그
```
| `.env` 값 | 의미 |
|---|---|
| `AWS_PROFILE=mfa` | 아래 MFA 단계에서 만드는 임시 자격 증명 프로필 |
| `AWS_REGION` | `ap-northeast-2` |
| `BUCKET_NAME`, `FUNCTION_NAME`, `ECR_REPO_NAME` | 만들 자원 이름. 공용 계정이므로 학번을 붙인다. S3 버킷 이름은 전 세계에서 고유해야 한다 |
| `LAMBDA_ROLE_NAME` | Lambda 실행 역할 (학교 제공 `yeonsung-lambda-basic-role`) |

AWS 접속 (학교 계정은 MFA 없이 CLI 요청이 거부된다):
```bash
aws configure                              # 최초 1회: 본인 액세스 키 (default 프로필)
bash scripts/mfa_session.sh <MFA 6자리>    # 12시간짜리 임시 자격 증명 → [mfa] 프로필
```

### 4. 배포와 실제 호출
```bash
make deploy   # S3 버킷·모델 업로드 → 이미지 빌드·모델 경로 검사·ECR push → Lambda 생성/업데이트 → smoke test
make invoke   # tests/test_inputs/ 9건으로 실제 호출, 기대(정상 200 / 오류 400)와 비교
```
- 어느 단계에서든 실패하면 `runs/`에 `failed`로 기록하고 중단한다.

### 5. 자원 정리
```bash
make clean-cloud   # 확인 질문 후 Lambda·로그 그룹·ECR·S3 삭제, 삭제 후 재조회 결과 기록
```

## 결과 파일 위치
| 위치 | 내용 |
|---|---|
| [`results/metrics.json`](results/metrics.json) | 모델과 베이스라인 2종의 MAE·RMSE (평가 8,734건) |
| [`results/error_analysis.md`](results/error_analysis.md), [`error_analysis_notes.md`](results/error_analysis_notes.md) | 오차가 가장 큰 1건 (자동 생성)과 원인 분석 |
| `runs/<UTC시각>_<단계>.json` | 실행마다 자동 기록: 시각, 성공 여부, Git 커밋, 모델 버전, 입력(데이터 SHA256), 설정, 결과 위치 |
| `runs/<시각>_invoke/` | 클라우드 호출별 요청, 응답, CloudWatch 로그 |
| [`runs/incident_model_path/`](runs/incident_model_path/) | 오류 재현·조사·복구 콘솔 출력 |
| [`runs/rerun_20261117/`](runs/rerun_20261117/) | 새 폴더 재실행 출력과 기록 |
| `runs/<시각>_cleanup/` | 자원 정리 전후 조회 결과 |

| 문서 | 내용 |
|---|---|
| [`docs/data.md`](docs/data.md) | 데이터·모델 출처와 사용 조건, 피처 정의와 단위, 분할 기준, 누수 방지, 평가, 한계 |
| [`docs/cloud.md`](docs/cloud.md) | 클라우드 구성과 선택 이유, 권한 문제 해결, 실행 결과, 지연 시간 |
| [`docs/incident.md`](docs/incident.md) | 오류 2건(잘못된 모델 경로, 콜드 스타트 타임아웃)의 재현, 조사, 수정, 재검사 |
| [`docs/rerun.md`](docs/rerun.md) | 새 폴더 재실행 환경과 결과 |
| [`docs/cost_and_cleanup.md`](docs/cost_and_cleanup.md) | 권한 범위, 비용, 자원 정리 후 상태, 보관 자료 |

## 저장소 구성
```
config/config.yaml     경로, 분할 기준, 피처, 모델 하이퍼파라미터, 모델 저장 압축 수준
src/                   data.py(다운로드·검증·분할) train.py evaluate.py pipeline.py(단계 실행·실패 중단) run_log.py(실행 기록)
service/               app.py(Lambda 핸들러·입력 검증) Dockerfile
scripts/               mfa_session.sh deploy.sh invoke.sh cleanup.sh
tests/                 test_service.py, test_inputs/(정상 3, 오류 6)
```

## 참고 자료와 본인 구현 부분
**참고 자료**
- 데이터: [UCI Bike Sharing Dataset](https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset) (Fanaee-T, H. 2013), CC BY 4.0. 저장소에 포함하지 않고 실행 시 내려받는다.
- 라이브러리: scikit-learn, pandas, numpy, scipy, joblib, PyYAML (`requirements.txt`)
- AWS 공식 Lambda 베이스 이미지 `public.ecr.aws/lambda/python:3.14`
- AWS 문서: Lambda 컨테이너 이미지, MFA 임시 자격 증명(`sts get-session-token`), 서울 리전 요금표

**이 저장소에서 구현한 부분**
- 데이터 다운로드·검증·분할, 학습, 평가, 실행 기록, 단계 실행 (`src/`)
- Lambda 핸들러와 입력 검증, 컨테이너 이미지 (`service/`)
- 배포, 호출, MFA 자격 증명, 자원 정리 스크립트 (`scripts/`)
- 로컬 테스트와 테스트 입력 (`tests/`)
- 사전학습 모델은 쓰지 않았고, 모델은 위 데이터로 직접 학습했다.
