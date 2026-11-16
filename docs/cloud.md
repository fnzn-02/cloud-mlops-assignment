# 클라우드 구성과 실행 기록

## 1. 구성

```
[로컬 Mac]  make all → data/model.joblib (26MB, 버전 = SHA256 앞 12자리)
    │
    │  make deploy (scripts/deploy.sh)
    ├──→ [S3] s3://bike-demand-2022100185/models/<버전>/model.joblib     모델 보관본
    ├──→ [ECR] bike-demand-2022100185:<모델버전>-<git커밋>              모델 포함 이미지
    │        └──→ [Lambda] bike-demand-2022100185                       예측 서비스
    │
    │  make invoke (scripts/invoke.sh)
    └──→ Lambda 실제 호출 → 응답·CloudWatch 로그
            ├──→ runs/<시각>_invoke/  (로컬, Git에 커밋)
            └──→ s3://bike-demand-2022100185/runs/<시각>_invoke/          결과 사본
```

| 항목 | 값 |
|---|---|
| 클라우드 / 리전 | AWS / `ap-northeast-2` (서울) |
| 실행 서비스 | AWS Lambda, 컨테이너 이미지 방식 |
| 런타임 이미지 | `public.ecr.aws/lambda/python:3.14` (로컬 학습 환경과 같은 Python 3.14) |
| 아키텍처 / 메모리 / 타임아웃 | `x86_64` / 1024 MB / 30초 |
| 환경변수 | `MODEL_PATH=/var/task/model/model.joblib` |
| 실행 역할 | `yeonsung-lambda-basic-role` (학교 제공, CloudWatch Logs 권한만 있음) |
| 이미지 저장소 | Amazon ECR `bike-demand-2022100185` |
| 모델·결과 저장 | Amazon S3 `bike-demand-2022100185` (퍼블릭 접근 차단) |
| 로그 | CloudWatch Logs `/aws/lambda/bike-demand-2022100185` |
| 태그 | `owner=2022100185`, `project=cloud-mlops-assignment` (버킷, ECR, Lambda) |

## 2. 구성을 선택한 이유

| 선택 | 이유 |
|---|---|
| **Lambda (서버리스)** | 대여소 운영자가 예보를 보고 가끔 조회하는 용도라 상시 서버가 필요 없다. 요청이 있을 때만 실행되고 요금도 실행 시간만큼만 낸다. 서버 관리와 정리가 간단하다 |
| **컨테이너 이미지 방식** | scikit-learn, scipy, pandas, numpy를 합치면 zip 배포 한도(압축 해제 250MB)를 넘는다. 이미지 방식은 10GB까지 가능하고, 로컬에서 같은 이미지로 미리 테스트할 수 있다 |
| **모델을 이미지에 포함** | 학교 계정은 IAM 역할을 만들 수 없어 학교가 제공한 기본 역할을 써야 한다. 이 역할로는 Lambda가 S3를 읽을 수 없어(아래 4절) 모델을 이미지에 넣었다. 이미지 태그에 모델 버전과 Git 커밋이 함께 들어가 버전 추적도 쉽다 |
| **S3** | 모델 보관본과 호출 결과 사본을 클라우드에 남긴다. 업로드는 Lambda가 아니라 CLI(본인 권한)로 한다 |
| **서울 리전** | 학교 정책(`StudentGuardrails`)이 서울 리전만 허용한다. us-east-1 조회는 거부되는 것을 확인했다 |
| **API Gateway 미사용** | 과제 범위에서는 CLI `aws lambda invoke`로 실제 입력을 넣고 결과를 받는 것으로 충분하다. 공개 엔드포인트를 만들지 않아 외부 접근과 비용 위험이 없다 |

## 3. 실행 절차
```bash
bash scripts/mfa_session.sh <MFA 6자리 코드>   # 임시 자격 증명 (아래 4절)
make all       # 데이터 → 학습 → 평가 (로컬)
make test      # 핸들러 로컬 테스트 9건
make deploy    # S3 업로드 → 이미지 빌드·검사·push → Lambda 생성/업데이트 → smoke test
make invoke    # 테스트 입력 9건으로 실제 호출, 결과 기록
```
- `deploy.sh`는 어느 단계에서든 실패하면 `runs/<시각>_deploy.json`에 실패 단계와 함께 `failed`를 기록하고 중단한다.
- `invoke.sh`는 기대와 다른 응답이 하나라도 있으면 `failed`를 기록하고 종료 코드 1을 반환한다.

## 4. 권한 문제와 해결 (실행한 내용)

| 시점 | 문제 | 원인 확인 | 해결 |
|---|---|---|---|
| 최초 | S3, ECR, Lambda, EC2 등 모든 CLI 요청이 `AccessDenied` | 오류 메시지가 `explicit deny ... policy/StudentSelfManagement`였다. `iam get-user`, MFA 장치 조회, 세션 토큰 발급만 허용됐고, 계정에 MFA 장치가 등록돼 있었다 → **MFA 미인증 요청을 거부하는 정책**으로 판단 | `scripts/mfa_session.sh`로 MFA 임시 자격 증명(12시간)을 발급해 `AWS_PROFILE=mfa`로 사용했다. 이후 S3, ECR, Lambda, CloudWatch Logs가 허용됐다 |
| 역할 생성 | `iam:CreateRole` 거부 | `explicit deny ... policy/StudentGuardrails` → 학생 역할 생성 금지 | 학교가 만든 `yeonsung-lambda-basic-role`을 사용했다. 테스트용 Lambda를 만들어 확인 후 즉시 삭제했다 |
| 역할 권한 | Lambda 안에서 `s3:ListBuckets` 거부 | 위 테스트 Lambda에서 확인 | 모델을 이미지에 포함하는 구조로 변경했다 |

- 공용 계정이므로 다른 사용자의 자원은 조회만 하고 변경하지 않았다. 내 자원에는 모두 학번을 붙였다.
- 비밀 값(액세스 키, 세션 토큰)은 `~/.aws/credentials`에만 있고 저장소에는 없다. 실행 기록의 계정 ID는 `<ACCOUNT_ID>`로 가렸다.

## 5. 클라우드 실행 결과

### 최종 배포 ([`runs/20261116T164136Z_deploy.json`](../runs/20261116T164136Z_deploy.json))
버전이 코드부터 실행 중인 함수까지 하나로 이어진다.

| 단계 | 값 |
|---|---|
| Git 커밋 | `db5a898` (`git_dirty: false`) |
| 모델 버전 (파일 SHA256 앞 12자리) | `0e16c92e1dd6` |
| 모델 보관본 | `s3://bike-demand-2022100185/models/0e16c92e1dd6/model.joblib` |
| 이미지 태그 | `bike-demand-2022100185:0e16c92e1dd6-db5a898` |
| 이미지 digest = Lambda `CodeSha256` | `sha256:2c1395075792c084f9...dcb1375c` |
| 배포 후 smoke test | normal_01 → 200 (첫 호출 포함 7초) |

### 실제 호출 ([`runs/20261116T164334Z_invoke.json`](../runs/20261116T164334Z_invoke.json))
| 입력 | 기대 | 응답 | 예측 (대/시간) | 응답의 모델 버전 |
|---|---|---|---|---|
| normal_01 (6월 수 17시, 맑음, 29.5°C) | 200 | 200 | 597.83 | 0e16c92e1dd6 |
| normal_02 (12월 월 8시, 흐림, 9.8°C) | 200 | 200 | 358.09 | 0e16c92e1dd6 |
| normal_03 (3월 일·공휴일 12시, 맑음, 17.2°C) | 200 | 200 | 155.19 | 0e16c92e1dd6 |
| error_missing (`hum` 누락) | 400 | 400 | - | - |
| error_range (`hum`=1.5) | 400 | 400 | - | - |
| error_type (`season`="여름") | 400 | 400 | - | - |
| error_float_int (`hr`=17.5) | 400 | 400 | - | - |
| error_extra_field (정답 `cnt` 포함) | 400 | 400 | - | - |
| error_not_object (리스트 입력) | 400 | 400 | - | - |

- **9/9 기대와 일치**했다.
- 클라우드 예측값은 로컬 핸들러 테스트와 같다.
- 응답의 `model_version`이 배포 기록, 학습 기록과 같다.
- 요청별 입력, 응답, CloudWatch 로그 끝부분이 `runs/20261116T164334Z_invoke/`에 있다. 같은 내용이 `s3://bike-demand-2022100185/runs/20261116T164334Z_invoke/`에도 있다.

CloudWatch 로그 예시 (normal_01):
```
[INFO] ... 모델 로드 완료 — 버전: 0e16c92e1dd6, 경로: /var/task/model/model.joblib
[INFO] ... 예측 완료 — run_id: ..., predicted: 597.83
```

### 지연 시간 (측정값)
| 구분 | 시간 | 근거 |
|---|---|---|
| 콜드 스타트 첫 예측 | Init 0.75~2.4초 + 처리 3.2~3.8초 (5회) | [`9_cold_start_measure.txt`](../runs/incident_model_path/9_cold_start_measure.txt) |
| 실행 환경 재사용 시 예측 | 13~20 ms | `runs/*_invoke/normal_0[23].log.txt` |
| 입력 검증 오류 응답 | 약 2 ms | `runs/*_invoke/error_*.log.txt` |

## 6. 측정하지 못한 부분
- 동시 요청 부하와 동시 실행 수 한도: 단건 순차 호출만 했다.
- 장시간 운영 중 콜드 스타트 빈도: 강제 측정 5회뿐이다.
- 실제 날씨 "예보" 입력에서의 정확도: 평가 데이터는 관측값이다(`docs/data.md` 한계 참고).
