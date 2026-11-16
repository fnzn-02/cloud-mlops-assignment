"""
app.py — Lambda 핸들러

모델은 컨테이너 이미지 안에 포함된다 (service/Dockerfile).
  학교 계정의 Lambda 실행 역할(yeonsung-lambda-basic-role)은 CloudWatch Logs 권한만 있어
  Lambda가 S3를 읽을 수 없으므로, 모델을 이미지에 넣는 방식을 선택했다.
  S3에는 CLI로 모델 보관본(models/<버전>/)과 호출 결과(runs/)를 올린다.

환경변수:
  MODEL_PATH  이미지 안 모델 경로 (기본: /var/task/model/model.joblib)

입력 (JSON):
  {
    "season": 2, "mnth": 6, "hr": 17, "holiday": 0,
    "weekday": 3, "workingday": 1, "weathersit": 1,
    "temp": 0.72, "atemp": 0.6515, "hum": 0.42, "windspeed": 0.1642
  }

출력 (JSON):
  {
    "predicted_cnt": 348.1,
    "unit": "대/시간",
    "model_version": "f9a91eb09c39",
    "run_id": "20261116T..._<요청ID 앞 8자리>",
    "request_id": "<Lambda 요청 ID — CloudWatch 로그 검색용>"
  }

에러:
  400 — 입력 검증 실패 (필드 누락, 범위 밖, 타입 오류)
  500 — 서버 내부 오류 (모델 로드 실패 등)
"""

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
# Lambda 런타임은 루트 로거를 WARNING으로 미리 설정해 basicConfig가 무시된다.
# 모델 버전·예측 완료 같은 INFO 로그가 CloudWatch에 남도록 직접 지정한다.
log.setLevel(logging.INFO)

# ── 필수 입력 필드와 허용 범위 ──────────────────────────────────────────────
FIELDS = {
    "season":     {"type": int,   "min": 1,   "max": 4},
    "mnth":       {"type": int,   "min": 1,   "max": 12},
    "hr":         {"type": int,   "min": 0,   "max": 23},
    "holiday":    {"type": int,   "min": 0,   "max": 1},
    "weekday":    {"type": int,   "min": 0,   "max": 6},
    "workingday": {"type": int,   "min": 0,   "max": 1},
    "weathersit": {"type": int,   "min": 1,   "max": 4},
    "temp":       {"type": float, "min": 0.0, "max": 1.0},
    "atemp":      {"type": float, "min": 0.0, "max": 1.0},
    "hum":        {"type": float, "min": 0.0, "max": 1.0},
    "windspeed":  {"type": float, "min": 0.0, "max": 1.0},
}

FEATURE_ORDER = list(FIELDS.keys())

# ── 모델 캐시 (Lambda 컨테이너 재사용 시 재로드 방지) ────────────────────────
_cache = {}


DEFAULT_MODEL_PATH = "/var/task/model/model.joblib"


def _load_model():
    """이미지 안의 model.joblib 를 로드해 캐시한다 (컨테이너 재사용 시 재로드 안 함)."""
    if _cache:
        return _cache

    model_path = Path(os.environ.get("MODEL_PATH", DEFAULT_MODEL_PATH))
    if not model_path.is_file():
        raise RuntimeError(f"모델 파일을 찾을 수 없음: {model_path} (MODEL_PATH 환경변수 확인)")

    # 모델 버전 = 파일 SHA256 앞 12자리 (src/train.py, scripts/deploy.sh와 동일한 방식)
    h = hashlib.sha256()
    with open(model_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    version = h.hexdigest()[:12]

    payload = joblib.load(model_path)

    _cache["model"]   = payload["model"]
    _cache["features"] = payload["features"]
    _cache["version"] = version
    _cache["baseline_mean"] = payload["baseline_mean"]

    log.info("모델 로드 완료 — 버전: %s, 경로: %s", version, model_path)
    return _cache


def _coerce(raw, expected: type):
    """
    값을 기대 타입으로 변환. 허용하지 않는 입력이면 None 반환.
    - 문자열, bool은 숫자로 인정하지 않음 ("17", true 등)
    - int 필드: 정수 또는 소수점 아래가 0인 실수(17.0)만 허용, 17.5는 거부
    - float 필드: int/float 허용
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if expected is int:
        if isinstance(raw, float) and not raw.is_integer():
            return None
        return int(raw)
    return float(raw)


def _validate(body) -> tuple[list, dict]:
    """
    입력 검증.
    반환: (errors, cleaned_values)
    errors가 비어있으면 통과.
    """
    if not isinstance(body, dict):
        return [f"입력은 JSON 객체여야 함, 받은 타입: {type(body).__name__}"], {}

    errors = []
    cleaned = {}

    # 정의되지 않은 필드 거부 (cnt, casual, registered 등 정답·누수 컬럼 유입 방지)
    unknown = sorted(set(body) - set(FIELDS))
    if unknown:
        errors.append(f"허용되지 않은 필드: {unknown}")

    for field, rule in FIELDS.items():
        if field not in body:
            errors.append(f"필수 필드 누락: '{field}'")
            continue

        raw = body[field]
        val = _coerce(raw, rule["type"])
        if val is None:
            errors.append(
                f"타입 오류: '{field}' — {rule['type'].__name__} 필요, 받은 값: {repr(raw)}"
            )
            continue

        # 범위 확인
        if not (rule["min"] <= val <= rule["max"]):
            errors.append(
                f"범위 오류: '{field}' = {val} — 허용 범위 [{rule['min']}, {rule['max']}]"
            )
            continue

        cleaned[field] = val

    return errors, cleaned


def handler(event, context):
    """Lambda 핸들러 진입점."""
    # 요청마다 고유한 run_id — Lambda에서는 요청 ID(CloudWatch 로그와 연결), 로컬에서는 uuid
    request_id = getattr(context, "aws_request_id", None) or uuid.uuid4().hex
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + request_id[:8]

    # ── body 파싱 ────────────────────────────────────────────────────────────
    if isinstance(event, dict) and "body" in event:
        # API Gateway 형식
        try:
            body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
        except (json.JSONDecodeError, TypeError):
            return {"statusCode": 400, "body": json.dumps({"error": "body가 유효한 JSON이 아님"})}
    else:
        # aws lambda invoke 직접 호출 형식
        body = event

    # ── 입력 검증 ─────────────────────────────────────────────────────────────
    errors, cleaned = _validate(body)
    if errors:
        resp = {"statusCode": 400, "errors": errors}
        log.warning("입력 검증 실패: %s", errors)
        return resp

    # ── 모델 로드 및 예측 ─────────────────────────────────────────────────────
    try:
        cache = _load_model()
    except RuntimeError as e:
        log.error("모델 로드 실패: %s", e)
        return {"statusCode": 500, "error": str(e)}

    features = cache["features"]
    X = pd.DataFrame([[cleaned[f] for f in features]], columns=features)
    predicted = float(cache["model"].predict(X)[0])
    predicted = round(max(0.0, predicted), 2)  # 음수 방지

    # ── 응답 구성 ─────────────────────────────────────────────────────────────
    result = {
        "statusCode": 200,
        "run_id": run_id,
        "request_id": request_id,
        "predicted_cnt": predicted,
        "unit": "대/시간",
        "model_version": cache["version"],
        "input": cleaned,
    }

    log.info("예측 완료 — run_id: %s, predicted: %.2f", run_id, predicted)
    return result
