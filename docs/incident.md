# 오류 재현과 복구

클라우드(AWS Lambda, `ap-northeast-2`)에서 일어난 오류 2건을 기록한다.

| # | 오류 | 성격 | 영향 | 결과 |
|---|---|---|---|---|
| 1 | 잘못된 모델 경로 (`MODEL_PATH`) | **의도적으로 재현** | 정상 입력이 전부 500 | 수정, 재발 방지 검사 추가 |
| 2 | 콜드 스타트 30초 타임아웃 | **복구 중에 실제로 발생** | 새 실행 환경의 첫 요청 실패 | 원인 제거(모델 압축), 반복 측정으로 확인 |

모든 콘솔 출력은 [`runs/incident_model_path/`](../runs/incident_model_path/)에 단계별로 저장했다. 계정 ID는 `<ACCOUNT_ID>`로 가렸다.
실행 기록(`runs/*.json`)은 모두 스크립트가 자동으로 남겼고, 시각은 UTC다(한국 시간 = UTC+9).

---

## 오류 1: 잘못된 모델 경로

### 시나리오
S3의 모델 보관 경로는 `models/<버전>/model.joblib`(복수형)이고, 이미지 안의 경로는 `/var/task/model/model.joblib`(단수형)이다.
두 경로를 혼동해 Lambda 환경변수를 `MODEL_PATH=/var/task/models/model.joblib`로 배포한 상황을 재현했다.

### 1) 실패한 명령과 결과
```bash
LAMBDA_MODEL_PATH=/var/task/models/model.joblib make deploy   # 배포 자체는 "성공"으로 끝남
make invoke
```
| 기록 | 내용 |
|---|---|
| [`runs/20261116T162216Z_deploy.json`](../runs/20261116T162216Z_deploy.json) | status `success`, `environment.MODEL_PATH = /var/task/models/model.joblib` |
| [`runs/20261116T162244Z_invoke.json`](../runs/20261116T162244Z_invoke.json) | status **`failed`**, 9건 중 6건만 기대와 일치 |
| [`2_invoke_failed.txt`](../runs/incident_model_path/2_invoke_failed.txt) | 콘솔 출력, `make: *** [invoke] Error 1`로 중단 |

오류 메시지 (Lambda 응답):
```json
{"statusCode": 500, "error": "모델 파일을 찾을 수 없음: /var/task/models/model.joblib (MODEL_PATH 환경변수 확인)"}
```

**영향**
- 정상 입력 3건(normal_01~03)이 모두 500을 반환했다. 예측 서비스가 완전히 멈춘 상태다.
- 입력 검증은 모델 로드 전에 수행되므로, 오류 입력 6건은 그대로 400을 반환했다.
- `invoke.sh`는 기대와 다른 응답을 `failed`로 기록하고 종료 코드 1로 다음 처리를 중단했다. 실패 결과는 `runs/20261116T162244Z_invoke/`에 정상 결과와 분리되어 남아 있다.

### 2) 원인 조사 ([`3_investigation.txt`](../runs/incident_model_path/3_investigation.txt))
| 확인 방법 | 결과 |
|---|---|
| CloudWatch 로그 ERROR 검색 (`aws logs filter-log-events --filter-pattern ERROR`) | `모델 로드 실패: 모델 파일을 찾을 수 없음: /var/task/models/model.joblib` |
| 배포된 함수 설정 (`aws lambda get-function-configuration`) | `MODEL_PATH = /var/task/models/model.joblib` |
| 배포된 이미지와 같은 digest를 받아 내부 파일 확인 (`docker run --entrypoint ls`) | 모델은 `/var/task/model/model.joblib`에 있고, `/var/task/models`는 존재하지 않음 |
| S3 보관 경로 (`aws s3 ls`) | `models/f9a91eb09c39/model.joblib` — 복수형 `models`가 혼동의 출처 |

**원인**: 환경변수의 경로(`models`)와 이미지 안의 실제 경로(`model`)가 다르다.
`deploy.sh`는 설정이 맞는지 검사하지 않아서, 잘못된 배포도 성공으로 기록됐다.

### 3) 수정
1. **즉시 복구**: 기본 경로로 다시 배포했다 (`make deploy`, 기록 [`20261116T162328Z_deploy.json`](../runs/20261116T162328Z_deploy.json)).
2. **재발 방지** (커밋 `db5a898`, `scripts/deploy.sh`):
   - push 전 검사: 빌드한 이미지 안에 `MODEL_PATH` 파일이 실제로 있는지 `docker run --entrypoint test -f`로 확인하고, 없으면 배포를 중단한다.
   - 배포 후 검사(smoke test): 정상 입력 1건을 실제로 호출해서 200이 아니면 배포를 `failed`로 기록한다.

### 4) 재검사
| 실행 | 기록 | 결과 |
|---|---|---|
| 같은 실수로 다시 배포 시도 | [`20261116T164116Z_deploy.json`](../runs/20261116T164116Z_deploy.json), [`7_deploy_wrong_path_blocked.txt`](../runs/incident_model_path/7_deploy_wrong_path_blocked.txt) | **push 전에 차단**(`failed`, 단계 "이미지 내 MODEL_PATH 확인"). Lambda 설정은 바뀌지 않음 |
| 실패했던 요청(normal_01) 재실행 | [`20261116T162357Z_invoke.json`](../runs/20261116T162357Z_invoke.json) | 이번에는 경로가 아니라 **타임아웃**으로 실패 → 오류 2 |
| 정상·오류 입력 전체 | [`20261116T162436Z_invoke.json`](../runs/20261116T162436Z_invoke.json) | 9/9 기대와 일치 |

---

## 오류 2: 콜드 스타트 타임아웃 (실제 발생)

### 1) 실패한 요청
오류 1을 고친 직후, 새 실행 환경에서 보낸 첫 요청(normal_01)이 실패했다 ([`5_rerun_failed_request.txt`](../runs/incident_model_path/5_rerun_failed_request.txt)).
```json
{"errorType": "Sandbox.Timedout", "errorMessage": "RequestId: 44db582d-... Error: Task timed out after 30.00 seconds"}
```
CloudWatch 로그(`runs/20261116T162357Z_invoke/normal_01.log.txt`):
```
REPORT ... Duration: 30000.00 ms  Max Memory Used: 319 MB  Init Duration: 7613.83 ms  Status: timeout
```
**영향**: 배포 직후나 오랫동안 호출이 없던 뒤의 첫 요청이 실패한다. 이후 요청은 실행 환경이 재사용되어 13~20ms 안에 처리됐다.

### 2) 원인 조사
같은 코드인데 첫 예측 요청의 처리 시간이 배포마다 크게 달랐다. 아래는 각 `runs/*_invoke/normal_01.log.txt`의 REPORT 줄이다.

| 배포 | 첫 예측 요청 Duration |
|---|---|
| 첫 배포 (3ff34e3) | 19.5초 |
| 로그 수정 후 (f7697dc) | 4.1초 |
| 경로 수정 직후 (f7697dc) | **30초 초과 (timeout)**, 이때 메모리 319MB로 모델을 아직 다 읽지 못함 |
| 그 직후 재호출 | 11.9초 |

- 모델 파일이 **148MB**였다. `RandomForestRegressor` 트리 200개를 깊이 제한 없이 학습해 압축 없이 저장했기 때문이다.
- 로컬에서 같은 파일은 0.06초 만에 로드된다. 즉 파일을 해석하는 시간이 아니라, Lambda가 새 실행 환경에서 이미지 파일을 처음 읽는 시간이 문제다.
- Lambda 컨테이너 이미지는 새 실행 환경에서 파일을 처음 읽을 때 저장소에서 가져온다. 그래서 큰 파일 하나를 처음 읽는 시간이 길고 들쭉날쭉하다고 판단했다.
- 이 마지막 판단은 측정 결과로 뒷받침되는 추정이며, AWS 내부 동작을 직접 확인한 것은 아니다.

### 3) 수정 (커밋 `db5a898`)
모델 크기를 줄이는 방법을 로컬에서 비교했다. 평가 데이터는 2012년 8,734건이다.

| 방법 | 파일 크기 | MAE (대/시간) |
|---|---|---|
| 기존 (압축 없음) | 148.3 MB | 88.78 |
| **압축 저장 (`joblib compress=3`)** | **26.1 MB** | **88.78 (동일 모델)** |
| `min_samples_leaf=2` | 68.1 MB | 88.89 |
| `min_samples_leaf=5` | 25.1 MB | 89.40 |
| `max_depth=15` | 95.2 MB | 88.96 |

정확도 손실이 없는 **압축 저장**을 선택했다.
- `config/config.yaml`에 `model.save_compress: 3`을 추가했고, `src/train.py`가 이 설정으로 저장한다.
- 재학습 결과 모델 버전은 `0e16c92e1dd6`으로 바뀌었고, 평가 지표는 같다 (기록 [`20261116T164109Z_evaluate.json`](../runs/20261116T164109Z_evaluate.json)).

### 4) 재검사
- 배포: [`20261116T164136Z_deploy.json`](../runs/20261116T164136Z_deploy.json). 배포 후 smoke test가 200을 반환했고, 첫 호출 포함 7초가 걸렸다.
- **콜드 스타트 5회 강제 측정** ([`9_cold_start_measure.txt`](../runs/incident_model_path/9_cold_start_measure.txt)): 함수 description을 바꿔 매번 새 실행 환경을 띄웠다.

| 회차 | 상태 | Init Duration | Duration (모델 로드 + 예측) |
|---|---|---|---|
| 1 | 200 | 0.80초 | 3.57초 |
| 2 | 200 | 0.78초 | 3.20초 |
| 3 | 200 | 0.75초 | 3.84초 |
| 4 | 200 | 2.40초 | 3.26초 |
| 5 | 200 | 0.92초 | 3.34초 |

- 정상·오류 입력 전체: [`20261116T164334Z_invoke.json`](../runs/20261116T164334Z_invoke.json), **9/9 기대와 일치** ([`10_invoke_all_final.txt`](../runs/incident_model_path/10_invoke_all_final.txt)).

### 남은 한계
- 콜드 스타트 첫 요청은 여전히 약 4~6초 걸린다. 5회 측정에서는 모두 30초 타임아웃의 1/5 이하였다.
- 측정 횟수가 5회뿐이어서, 드물게 더 느린 경우가 없다고 보장하지는 못한다.
- 더 줄이려면 메모리를 늘리거나(CPU도 비례해 증가) 트리 수를 줄이는 방법이 있지만 적용하지 않았다.
