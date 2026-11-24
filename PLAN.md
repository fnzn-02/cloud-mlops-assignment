# 작업 계획서 (PLAN)

> 과제 원문: 클라우드 MLOps 대체 실습과제 안내문과 평가기준 (PDF, 저장소에 미포함)

## 0. 작업 규칙
- 단계가 끝날 때마다 커밋한다.
- AWS 키, 토큰, 계정 ID 같은 비밀 값은 코드, 로그, 캡처, Git 이력에 절대 넣지 않는다.
- 로그는 사람이 손으로 쓰지 않고 **스크립트가 자동으로 남긴다.**
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
- **모델**: scikit-learn `RandomForestRegressor` (n_estimators=200, random_state=42, joblib 압축 3으로 저장 26MB)
- **분할**: yr=0(2011) → 학습 8,645행 / yr=1(2012) → 평가 8,734행

## 3. 환경 정보
- **OS**: macOS (Apple Silicon)
- **Python**: 3.14.5 (가상환경: `.venv/`)
- **AWS CLI**: 2.34.48
- **Docker**: 29.1.3
- **AWS 계정**: 학교 계정 (일반 AWS, Learner Lab 아님)
- **AWS 리전**: `ap-northeast-2` (서울)
- **GitHub**: https://github.com/fnzn-02/cloud-mlops-assignment (Public, main 브랜치)
- **IAM 사용자**: `<학번>`

## 4. AWS 구성 (최종)
```
[로컬] make all → data/model.joblib (버전 = SHA256 앞 12자리)
   │ make deploy
   ├─→ [S3] s3://bike-demand-<학번>/models/<버전>/model.joblib (보관본)
   └─→ [ECR] 모델 포함 이미지 → [Lambda] bike-demand-<학번> (MODEL_PATH=/var/task/model/model.joblib)
[로컬] make invoke → 실제 호출 → runs/ + s3://.../runs/
```
- Lambda: Python 3.14 컨테이너, x86_64, 1024MB, 30초, 실행 역할 `yeonsung-lambda-basic-role`(학교 제공)
- 학교 계정 제약: CLI는 MFA 필수(`scripts/mfa_session.sh`), IAM 역할 생성 불가, 서울 리전만 허용
  → 역할이 S3를 못 읽어 모델을 이미지에 포함 (자세한 내용 `docs/cloud.md`)

## 5. 진행 상황 체크리스트
- [x] 1. 환경: Python 3.14.5, AWS CLI 2.34.48, Docker 29.1.3
- [x] 2. 저장소 초기화
- [x] 3. 데이터: 다운로드, SHA256 고정·검증, 분할, `docs/data.md` (season 표기 실제 데이터 기준으로 수정)
- [x] 4. 학습·평가: 베이스라인 2종 비교, 오답 분석 자동 생성 + `results/error_analysis_notes.md`
- [x] 5. 실행 기록: 입력·설정·모델 버전·결과 위치 자동 기록, 실패 시 중단
- [x] 6. 서비스: 입력 검증 강화, 로컬 테스트 9/9
- [x] 7. 클라우드 배포·호출: 9/9, `docs/cloud.md`
- [x] 8. 오류 재현·복구: 잘못된 MODEL_PATH(재현) + 콜드 스타트 타임아웃(실제 발생), `docs/incident.md`
- [x] 9. 새 폴더 재실행: 결과 완전 재현, `docs/rerun.md`
- [x] 10. 자원 정리: 4종 삭제 후 재조회 확인, `docs/cost_and_cleanup.md`
- [ ] 11. 최종 점검 (사용자): 로그아웃 상태에서 저장소 열림 확인

## 6. 다시 배포해야 할 때
```bash
bash scripts/mfa_session.sh <MFA 코드>
make all && make test && make deploy && make invoke
make clean-cloud   # 끝나면 정리
```
