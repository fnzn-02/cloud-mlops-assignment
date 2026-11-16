# 권한, 비용, 자원 정리

## 1. 접근 권한과 대상

| 주체 | 사용한 권한 | 대상 |
|---|---|---|
| IAM 사용자 `2022100185` (학교 계정, CLI) | MFA 임시 자격 증명으로만 사용 (`scripts/mfa_session.sh`, 12시간) | 아래 자원 |
| 〃 | S3: 버킷 생성·삭제, 퍼블릭 접근 차단 설정, 태그, 객체 업로드·삭제 | `bike-demand-2022100185` |
| 〃 | ECR: 저장소 생성·삭제, 로그인 토큰, 이미지 push·조회 | `bike-demand-2022100185` |
| 〃 | Lambda: 함수 생성·수정·호출·삭제, 설정 조회 | `bike-demand-2022100185` (확인용 `bike-demand-2022100185-probe`는 생성 직후 삭제) |
| 〃 | CloudWatch Logs: 로그 조회·검색·삭제 | `/aws/lambda/bike-demand-2022100185` |
| 〃 | IAM: 역할 목록 조회만 가능. 역할 생성·상세 조회는 거부됨 | - |
| Lambda 실행 역할 `yeonsung-lambda-basic-role` (학교 제공) | CloudWatch Logs 쓰기. S3 접근 거부를 확인함 | Lambda 실행 중 로그 |

- 계정 정책 때문에 MFA 없는 CLI 요청은 모두 거부된다(`StudentSelfManagement`). 학생 IAM 역할 생성과 서울 외 리전 사용도 거부된다(`StudentGuardrails`). 자세한 경위는 [`docs/cloud.md`](cloud.md) 4절에 있다.
- 공용 계정이므로 다른 사용자의 자원과 학교 역할은 조회만 하고 변경하지 않았다.
- 비밀 값(액세스 키, 세션 토큰)은 `~/.aws/credentials`에만 있고, 코드, 로그, Git 이력에는 없다. 실행 기록의 계정 ID는 `<ACCOUNT_ID>`로 가렸다.

## 2. 비용이 발생한 자원과 추정 비용

비용 조회 API(Cost Explorer)는 학교 조직 정책(SCP)이 거부해서 실제 청구액을 확인할 수 없었다.
아래 금액은 기록된 사용량에 서울 리전 공개 요금을 곱한 **추정치**다.

| 자원 | 사용량 (근거) | 단가 (서울, 공개 요금) | 추정 비용 |
|---|---|---|---|
| Lambda 실행 시간 | 약 149 GB-초. 호출 로그 55건의 Billed Duration 합 94.1초 + 콜드 스타트 측정 22.9초 + smoke test, 확인용 함수 상한 32초, 메모리 1GB | $0.0000166667 / GB-초 | 약 $0.003 |
| Lambda 요청 | 약 64건 | $0.20 / 100만 건 | $0.00001 미만 |
| ECR 저장 | 이미지 3개 × 약 343MB(레이어 공유로 실제는 더 작음), 약 1.5시간 보관 | $0.10 / GB-월 | $0.001 미만 |
| S3 저장 | 객체 236개, 174MB, 약 1.5시간 보관 (`before.txt`) | $0.025 / GB-월 | $0.001 미만 |
| S3 요청 | 업로드 약 240건 | $0.0045 / 1,000건 | 약 $0.001 |
| CloudWatch Logs | 수십 KB | $0.76 / GB 수집 | $0.001 미만 |
| 데이터 전송 | ECR push(인바운드)와 같은 리전 내 Lambda 이미지 수신 | 무료 | $0 |
| **합계** | | | **약 $0.01 미만** |

사용량 근거: `runs/*_invoke/*.log.txt`, [`runs/incident_model_path/9_cold_start_measure.txt`](../runs/incident_model_path/9_cold_start_measure.txt), [`runs/20261116T165037Z_cleanup/before.txt`](../runs/20261116T165037Z_cleanup/before.txt).

## 3. 비용 제한 방법

| 방법 | 내용 |
|---|---|
| 상시 실행 자원 없음 | Lambda는 호출될 때만 과금된다. EC2, 컨테이너 서비스처럼 켜져 있는 동안 계속 과금되는 자원은 쓰지 않았다 |
| 공개 엔드포인트 없음 | API Gateway나 함수 URL을 만들지 않았다. 권한이 있는 CLI로만 호출할 수 있어 외부 요청으로 비용이 생길 수 없다 |
| 실행 상한 | 타임아웃 30초, 메모리 1024MB로 요청 1건의 최대 비용이 정해져 있다 |
| 작업 직후 삭제 | 모든 자원을 같은 날 삭제했다 (아래 4절) |
| 계정 예산 (학교 설정, 조회만 가능) | `aws budgets describe-budgets` 조회 결과 계정 전체에 일일 $100, 월 $2,000 예산이 설정되어 있다. 공용 계정 전체 금액이라 본인 사용분과는 다르다 |
| 본인 예산 알림 | 설정하지 않았다. 학생 권한으로 예산 생성 가능 여부는 확인하지 않았다 |

## 4. 자원 정리와 정리 후 상태

```bash
bash scripts/cleanup.sh --yes      # 또는 make clean-cloud (확인 질문 후 진행)
```
기록: [`runs/20261116T165037Z_cleanup.json`](../runs/20261116T165037Z_cleanup.json) (status `success`)

| 자원 | 삭제 전 ([before.txt](../runs/20261116T165037Z_cleanup/before.txt)) | 삭제 후 재조회 ([after.txt](../runs/20261116T165037Z_cleanup/after.txt)) |
|---|---|---|
| Lambda `bike-demand-2022100185` | Active, 1024MB, 30초 | `ResourceNotFoundException` → 삭제됨 |
| CloudWatch 로그 그룹 | 1개 | 조회 결과 0개 → 삭제됨 |
| ECR `bike-demand-2022100185` | 이미지 3개 (각 약 343MB) | `RepositoryNotFoundException` → 삭제됨 |
| S3 `bike-demand-2022100185` | 객체 236개, 174MB | `404` → 삭제됨 |
| 이름에 학번이 들어간 Lambda, ECR, S3, 로그 그룹 검색 | - | 결과 없음 |

정리 시각: 2026-11-16 16:50 UTC (2026-11-17 01:50 KST)

## 5. 보관한 자료와 남은 자원

| 항목 | 위치 | 이유 | 정리 계획 |
|---|---|---|---|
| 실행 기록 (배포, 호출, 오류 재현, 재실행, 정리) | Git 저장소 `runs/` | 과제 평가 증거. S3 사본은 삭제했지만 같은 내용이 Git에 있다 | 보관 |
| 모델 파일 `data/model.joblib`, 데이터 `data/hour.csv` | 로컬 (Git 제외) | `make all`로 언제든 같은 파일(SHA256 동일)을 다시 만들 수 있다 (`docs/rerun.md`) | 필요 없으면 로컬에서 삭제 |
| 로컬 Docker 이미지 | 로컬 Docker Desktop | 빌드 캐시 | `docker image prune`으로 정리 가능, 비용 없음 |
| MFA 임시 자격 증명 `[mfa]` 프로필 | `~/.aws/credentials` | 발급 후 12시간이 지나면 자동 만료 | 만료 후 그대로 둬도 사용 불가 |
| IAM 사용자 `2022100185`, 학교 역할 | AWS 계정 | 학교가 관리하는 자원 | 학생이 정리할 대상 아님 |

**클라우드에 남은 본인 자원은 없다.** 재배포가 필요하면 `make deploy`로 같은 구성을 다시 만들 수 있다.
