# 작업 계획서 (PLAN)

> 다른 AI 도구에서 이어서 작업할 때: "PLAN.md 읽고 진행 상황 체크리스트에서 아직 안 한 단계부터 진행해줘"라고 요청하세요.
> 과제 원문: `docs/클라우드MLOps_대체실습과제_안내문과_평가기준.pdf`

## 0. 작업 규칙
- **git commit/push는 사용자가 직접 한다.** AI는 파일만 수정하고, 단계가 끝날 때마다 커밋 메시지를 제안한다.
- AWS 키, 토큰, 계정 ID 같은 비밀 값은 코드, 로그, 캡처, Git 이력에 절대 넣지 않는다. 로그에 남기기 전에 계정 ID는 `XXXX`로 가린다.
- 로그는 사람이 손으로 쓰지 않고 **스크립트가 자동으로 남긴다.** 과제에 "설명만 작성한 부분은 실행으로 인정하지 않음"이라고 되어 있기 때문이다.
- README의 "참고 자료와 본인 구현 부분"에 AI 도구를 사용한 범위를 적는다.

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
- **입력**: 날짜/시간 정보(`season`, `yr`, `mnth`, `hr`, `holiday`, `weekday`, `workingday`)와 날씨 정보(`weathersit`, `temp`, `atemp`, `hum`, `windspeed`)
- **출력**: 해당 시간의 예상 대여 대수 (`cnt`, 단위: 대/시간)
- **데이터**: UCI Bike Sharing Dataset `hour.csv` (17,379행, 2011~2012 Washington D.C. Capital Bikeshare)
  - 출처: https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset
  - 라이선스: CC BY 4.0 (재배포 가능하지만 출처 표기 필요)
- **누수 방지**: `casual`과 `registered`는 더하면 정답(`cnt`)이 되므로 입력에서 제외한다. `instant`(행 번호)와 `dteday`(날짜 문자열)도 제외한다.
- **분할 기준**: 시간 순서로 나눈다. 2011년(`yr=0`)은 학습용, 2012년(`yr=1`)은 평가용이다. 무작위 분할을 쓰지 않는 이유는 미래 데이터가 학습에 섞이는 것을 막기 위해서다.
  - 참고: 평가 데이터에는 학습 데이터에 없는 `yr=1`만 있으므로, `yr`을 입력에 넣을지는 실험해 보고 결정한 뒤 이유를 기록한다.
- **데이터 정규화 주의**: `temp`, `atemp`, `hum`, `windspeed`는 원본에서 이미 0~1로 정규화된 값이다(temp는 ÷41°C, atemp는 ÷50°C, hum는 ÷100, windspeed는 ÷67). 문서에 단위 변환식을 적는다.
- **잘못된 값 처리**: 결측치와 범위 밖 값(예: hum이 0~1을 벗어남)을 확인하고, 학습 시에는 제거하고 서비스에서는 400 에러로 거부한다. 처리 건수를 기록한다.
- **모델**: scikit-learn `RandomForestRegressor` 또는 `HistGradientBoostingRegressor` (`random_state` 고정)
- **베이스라인**: 학습 데이터의 `cnt` 평균값으로 예측. 추가로 "시간대(hr)별 평균"도 비교하면 해석이 더 좋아진다.
- **지표**: MAE(대/시간), RMSE(대/시간). 같은 평가 데이터로 모델과 베이스라인을 비교한다.

## 3. AWS 구성
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
- **리전**: `us-east-1` (AWS Academy Learner Lab은 보통 이 리전만 허용됨)
- **선택 이유**: 요청이 있을 때만 예측하면 되는 서비스라 상시 서버가 필요 없다. Lambda는 호출한 만큼만 과금되어 비용이 거의 0이다. scikit-learn 패키지가 zip 배포 한도(250MB)를 넘을 수 있어서 컨테이너 이미지를 쓴다.
- **AWS Academy일 경우**: IAM 역할을 직접 만들 수 없으므로 Lambda 실행 역할로 기존 `LabRole`을 사용한다. 세션이 약 4시간마다 끝나므로 `~/.aws/credentials`의 임시 키를 다시 붙여 넣어야 한다.
- **Lambda 설정 예시**: 메모리 1024MB, 타임아웃 30초, 아키텍처 x86_64 (Apple Silicon Mac이면 `docker build --platform linux/amd64` 사용)
- **사용 확인 필요**: `aws --version`, `docker --version`, `aws sts get-caller-identity`

## 4. 폴더 구조 (목표)
```
cloud-mlops-assignment/
├── README.md              # 목적, 구성, 환경, 권한, 설치~검증 명령, 결과 위치, 참고/본인 구현
├── PLAN.md                # 이 파일
├── Makefile               # make data / train / evaluate / deploy / invoke / all / clean-cloud
├── requirements.txt       # 버전 고정 (pandas, scikit-learn, joblib, boto3 등)
├── .gitignore             # .venv, __pycache__, .env, data/raw 등
├── config/config.yaml     # 경로, 분할 기준, 하이퍼파라미터, 버킷, 리전, 함수 이름
├── src/
│   ├── data.py            # 다운로드, SHA256 확인, 검증, 분할
│   ├── train.py           # 학습, 모델 저장, 모델 버전(해시) 계산
│   ├── evaluate.py        # 모델 vs 베이스라인, 오답 분석용 상위 오차 추출
│   ├── run_log.py         # 실행 기록 공통 함수
│   └── pipeline.py        # 단계별 실행. 실패 시 다음 단계 중단
├── service/
│   ├── app.py             # Lambda handler (입력 검증 → 예측)
│   └── Dockerfile
├── scripts/
│   ├── deploy.sh          # S3 업로드, ECR push, Lambda 생성/업데이트
│   ├── invoke.sh          # 정상/비정상 입력으로 실제 호출하고 결과 저장
│   └── cleanup.sh         # 자원 삭제 후 조회 결과 저장
├── tests/
│   ├── test_inputs/       # 정상 입력 3건 이상, 비정상 입력(필드 누락, 범위 밖, 타입 오류)
│   └── test_service.py    # 로컬 handler 테스트
├── results/
│   ├── metrics.json       # MAE/RMSE (모델, 베이스라인)
│   └── error_analysis.md  # 오답 1건 분석
├── runs/                  # 실행 기록 (자동 생성, Git에 포함)
└── docs/
    ├── data.md            # 데이터와 모델 설명
    ├── cloud.md           # 클라우드 구성, 설정, 실행 기록 요약
    ├── incident.md        # 오류 재현과 복구
    ├── rerun.md           # 새 폴더 재실행 기록
    └── cost_and_cleanup.md
```

## 5. 실행 기록 형식 (`runs/<UTC시각>_<단계>.json`)
```json
{
  "run_id": "20261110T013000Z_invoke",
  "stage": "invoke",
  "started_at": "2026-11-10T01:30:00Z",
  "finished_at": "2026-11-10T01:30:03Z",
  "status": "success",
  "git_commit": "abc1234",
  "git_dirty": false,
  "model_version": "3f9a1c2e7b10",
  "data_sha256": "...",
  "input": "tests/test_inputs/normal_01.json",
  "config": {"region": "us-east-1", "function": "bike-demand", "image_tag": "..."},
  "output_location": "s3://<버킷>/runs/<run_id>/output.json",
  "error": null
}
```
- 실패한 실행은 `"status": "failed"`와 에러 메시지를 남기고, 파이프라인은 다음 단계를 진행하지 않는다.
- Lambda 응답에도 `model_version`을 포함해서, 클라우드에서 어떤 모델이 실행됐는지 확인할 수 있게 한다.

## 6. 오류 재현 시나리오 (하나 선택)
**추천: 잘못된 모델 경로**
1. Lambda 환경변수 `MODEL_S3_URI`를 존재하지 않는 경로로 설정해 배포한다.
2. 정상 입력으로 호출하면 실패한다. 응답과 CloudWatch 로그(`NoSuchKey` 등)를 저장한다.
3. 원인을 확인한다: `aws s3 ls`로 실제 경로와 비교한다.
4. 수정한다: 올바른 경로로 고치고, 시작 시 모델 경로를 확인해 명확한 에러를 내도록 코드를 개선한다.
5. **같은 요청을 다시 실행**하고, 정상 입력도 다시 실행해 성공 로그를 남긴다.
6. `docs/incident.md`에 실패 명령, 에러 원문, 영향, 원인, 수정 내용(커밋), 재실행 결과를 적는다.

(대안: 필수 입력값 누락 시 500 에러가 나는 것을 400 에러와 명확한 메시지로 바꾸는 시나리오)

## 7. 평가 항목
- **품질**: 평가용 2012년 데이터 전체(약 8,700건)로 모델과 베이스라인의 MAE/RMSE를 비교한다. 단위는 대/시간이다.
- **정상 동작 검사**: 정상 입력 N건은 200 응답과 숫자 예측값이 나오는지, 비정상 입력은 400 응답과 에러 메시지가 나오는지 확인한다. 로컬과 Lambda 모두 검사한다.
- **오답 분석**: 오차가 가장 큰 1건의 입력, 예측, 정답을 보고 원인을 추정한다. (예: 이벤트, 급격한 날씨 변화, 2012년 이용자 증가 추세)
- **한계**: 2년치·한 도시 데이터, 실제 날씨 "예보"가 아닌 관측값 사용, 연도별 증가 추세 반영 한계, 측정하지 못한 것(지연시간 분포, 동시 요청 부하 등)
- **규칙**: 평가 데이터로 학습하거나 전처리 기준(정규화, 이상값 기준 등)을 정하지 않는다.

## 8. 권한, 비용, 정리
- **권한**: S3(버킷 생성, 읽기, 쓰기), ECR(저장소, push), Lambda(생성, 수정, 호출), CloudWatch Logs(조회), 실행 역할(`LabRole`)
- **비용 자원**: S3 저장 용량, ECR 이미지 저장 용량, Lambda 호출, CloudWatch 로그 → 모두 소량이므로 거의 0원. Learner Lab은 크레딧 한도가 있으므로 남은 크레딧을 확인한다.
- **비용 제한**: 상시 서버 없이 Lambda만 사용, Function URL 같은 공개 엔드포인트를 만들지 않고 CLI 호출만 사용, 작업 후 즉시 삭제
- **정리**: `cleanup.sh`로 Lambda, ECR 저장소, S3 객체와 버킷, 로그 그룹을 삭제한 뒤 `list`/`describe` 조회 결과를 `docs/cost_and_cleanup.md`에 저장한다.
- 남겨 두는 자원이 있다면 이유와 삭제 예정일을 적는다.

## 9. 진행 상황 체크리스트
- [ ] 1. 환경 확인: `aws --version`, `docker --version`, `aws sts get-caller-identity`, Python 버전
- [ ] 2. 저장소 초기화: `git init`, `.gitignore`, `requirements.txt`, `README.md` 뼈대 (커밋은 사용자가)
- [ ] 3. 데이터: 다운로드 스크립트, 해시 확인, 검증, 2011/2012 분할, `docs/data.md`
- [ ] 4. 학습과 평가: 모델 vs 베이스라인, `results/metrics.json`, 오답 분석
- [ ] 5. 실행 기록: `run_log.py`, `pipeline.py`, `Makefile` (실패 시 중단)
- [ ] 6. 서비스: Lambda handler, 입력 검증, 로컬 테스트
- [ ] 7. 클라우드 배포: S3 업로드, ECR push, Lambda 생성, 실제 호출 기록, `docs/cloud.md`
- [ ] 8. 오류 재현과 복구: `docs/incident.md`
- [ ] 9. 새 폴더 재실행: clone → README대로 실행 → `docs/rerun.md`
- [ ] 10. 자원 정리와 조회: `docs/cost_and_cleanup.md`
- [ ] 11. 최종 점검: 비밀 값 검색(`git log -p | grep -i key` 등), 로그아웃 상태에서 저장소가 열리는지 확인, main 브랜치 확인
