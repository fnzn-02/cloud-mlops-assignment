# 새 폴더 재실행 기록

GitHub 저장소를 새 폴더에 clone해서 README 절차대로 설치하고, 핵심 기능(데이터 → 학습 → 평가 → 테스트 → 클라우드 배포 → 호출)을 다시 실행했다.
원래 작업 폴더의 `.venv`, `data/`, `.env`는 쓰지 않았다.

- 콘솔 전체 출력: [`runs/rerun_20261117/rerun_console.txt`](../runs/rerun_20261117/rerun_console.txt)
- 재실행 중 생긴 실행 기록: [`runs/rerun_20261117/`](../runs/rerun_20261117/) (clone 폴더의 `runs/`에서 복사)

## 환경
| 항목 | 값 |
|---|---|
| 일시 | 2026-11-16 16:46~16:49 UTC (2026-11-17 01:46~01:49 KST) |
| OS | macOS 26.5.2 (arm64, Apple Silicon) |
| Python | 3.14.5 (Homebrew) |
| AWS CLI | 2.34.48 |
| Docker | 29.1.3 (Docker Desktop) |
| Git | 2.50.1 |
| 대상 커밋 | `fa1316d` (clone 직후 `main`) |
| 설치된 라이브러리 | pandas 2.3.3, numpy 2.3.5, scikit-learn 1.7.2, scipy 1.16.3, joblib 1.5.2, PyYAML 6.0.3 (`requirements.txt`와 일치) |

## 실행한 명령
```bash
git clone https://github.com/fnzn-02/cloud-mlops-assignment.git
cd cloud-mlops-assignment
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env && sed -i '' 's/<학번>/2022100185/g' .env
make all
make test
make deploy
make invoke
```

## 결과
| 단계 | 결과 | 기록 |
|---|---|---|
| 데이터 | UCI에서 새로 다운로드했다. SHA256 `e03de4ee…504f` 검증을 통과했고, 17,379행, 제거 0행, 학습 8,645 / 평가 8,734 | `20261116T164700Z_data.json` |
| 학습 | 모델 버전 **`0e16c92e1dd6`**. 원본 작업 폴더와 같다 | `20261116T164712Z_train.json` |
| 평가 | MAE 88.78 / RMSE 125.22. `results/metrics.json`, `results/error_analysis.md`가 저장소에 커밋된 파일과 **diff 없이 동일** | `20261116T164800Z_evaluate.json` |
| 로컬 테스트 | 9/9 통과 | 콘솔 출력 |
| 배포 | 성공. 이미지 내 모델 경로 검사 통과, smoke test 200 (5초). 이미지 태그 `0e16c92e1dd6-fa1316d` | `20261116T164813Z_deploy.json` |
| 실제 호출 | **9/9 기대와 일치**. 예측값 597.83 / 358.09 / 155.19가 원본 실행과 같다 | `20261116T164846Z_invoke.json` |

모든 기록이 `git_commit: fa1316d`, `git_dirty: false`다.

## 재실행으로 확인한 것
- `random_state` 고정과 라이브러리 버전 고정 덕분에 새 환경에서도 **모델 파일이 바이트 단위로 같고**(SHA256 동일) 평가 결과도 같다.
- 새 폴더에서 빌드한 이미지 digest(`sha256:2c1395075792…`)가 이전 배포와 같았다.
  - 다만 같은 Mac에서 빌드해 Docker 레이어 캐시가 쓰였을 수 있다.
  - 그래서 다른 컴퓨터에서도 digest가 같다고는 보장하지 않는다.

## 재실행 중 발견한 README 문제와 조치
| 문제 | 영향 | 조치 |
|---|---|---|
| MFA 임시 자격 증명 단계(`scripts/mfa_session.sh`)가 README에 없음 | 학교 계정에서는 `make deploy`가 `AccessDenied`로 실패한다. 이번에는 같은 날 발급해 둔 `mfa` 프로필이 남아 있어 진행됐다 | README "AWS 접속" 절에 추가 |
| `.env`의 `<학번>`을 채우는 방법이 "BUCKET_NAME 등을 채운다"로만 적혀 있음 | 무엇을 바꿔야 하는지 불명확 | README에 `sed` 명령과 각 값의 의미 추가 |
| `make test`가 README 실행 명령 목록에 없음 | 로컬 검증 방법을 찾기 어려움 | README에 추가 |
| Docker Desktop을 **실행 중**이어야 한다는 안내 없음 | `make deploy`가 사전 확인에서 중단된다 | README 환경 요구사항에 명시 |

## 확인하지 못한 것
- **다른 컴퓨터, 다른 OS**: 같은 Mac의 새 폴더에서만 실행했다. Linux나 Windows에서는 확인하지 않았다(`invoke.sh`의 `date -r`, `sed -i ''`는 macOS 문법이다).
- **다른 AWS 계정**: 같은 학교 계정과 같은 자원 이름으로 배포했다(기존 Lambda를 업데이트). 빈 계정에서 처음 생성하는 경로는 최초 배포(`runs/20261116T161852Z_deploy.json`) 때 한 번 실행됐다.
