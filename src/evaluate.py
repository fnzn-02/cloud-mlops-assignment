"""
evaluate.py — 모델 vs 베이스라인 평가

지표: MAE, RMSE (단위: 대/시간)
평가 데이터: 2012년 (yr=1) 전체 약 8,700건
오답 분석: 오차 가장 큰 1건 추출
"""

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent))
import data as data_mod
import run_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def mae(y_true, y_pred):
    return float(np.mean(np.abs(np.array(y_true) - np.array(y_pred))))


def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((np.array(y_true) - np.array(y_pred)) ** 2)))


# 사람이 읽을 수 있는 값 변환
# season: UCI Readme는 1=봄으로 적혀 있지만 실제 데이터는 1월·12월이 1, 3~6월이 2이므로
#         실제 데이터 기준(천문학적 계절, 약 3/21·6/21·9/23·12/21 경계)으로 표기한다.
SEASON   = {1: "겨울", 2: "봄", 3: "여름", 4: "가을"}
WEEKDAY  = {0: "일요일", 1: "월요일", 2: "화요일", 3: "수요일", 4: "목요일", 5: "금요일", 6: "토요일"}
WEATHER  = {1: "맑음/구름 조금", 2: "안개+흐림", 3: "약한 눈/비", 4: "폭우/폭설"}


def _describe(col: str, v) -> str:
    if col == "season":     return SEASON.get(int(v), "?")
    if col == "mnth":       return f"{int(v)}월"
    if col == "hr":         return f"{int(v)}시"
    if col == "holiday":    return "공휴일" if int(v) else "공휴일 아님"
    if col == "weekday":    return WEEKDAY.get(int(v), "?")
    if col == "workingday": return "근무일" if int(v) else "휴일/주말"
    if col == "weathersit": return WEATHER.get(int(v), "?")
    if col == "temp":       return f"기온 약 {v * 41:.1f}°C"
    if col == "atemp":      return f"체감 기온 약 {v * 50:.1f}°C"
    if col == "hum":        return f"습도 {v * 100:.0f}%"
    if col == "windspeed":  return f"풍속 약 {v * 67:.1f} km/h"
    return ""


def _write_error_analysis(row, pred, train_df, test_df, features, target) -> Path:
    """
    오차 최대 1건을 자동으로 기록한다 (재실행할 때마다 다시 생성됨).
    사람이 쓴 원인 분석은 results/error_analysis_notes.md 에 따로 둔다.
    """
    actual = int(row[target])
    hr = int(row["hr"])
    tr_hr = train_df.loc[train_df["hr"] == hr, target]
    te_hr = test_df.loc[test_df["hr"] == hr, target]

    lines = [
        "# 오답 분석 (오차 최대 1건, 자동 생성)",
        "",
        "> 이 파일은 `make evaluate` 실행 시 `src/evaluate.py`가 다시 만든다.",
        "> 원인 분석은 [error_analysis_notes.md](error_analysis_notes.md) 참고.",
        "",
        "## 대상",
        f"- 원본 행 번호(`instant`): {int(row['instant'])}",
        f"- 날짜(`dteday`): {row['dteday']}",
        "",
        "## 입력",
        "| 피처 | 값 | 의미 |",
        "|---|---|---|",
    ]
    for col in features:
        lines.append(f"| {col} | {row[col]} | {_describe(col, row[col])} |")
    lines += [
        "",
        "## 결과",
        f"- 정답(`{target}`): {actual} 대/시간",
        f"- 예측값: {pred:.1f} 대/시간",
        f"- 오차: {actual - pred:+.1f} 대/시간 (실제 대비 {abs(actual - pred) / actual * 100:.0f}%)",
        "",
        f"## 비교: 같은 시간대({hr}시) 대여량",
        "| 구분 | 평균 | 최대 |",
        "|---|---|---|",
        f"| 학습 데이터 (2011) | {tr_hr.mean():.1f} | {int(tr_hr.max())} |",
        f"| 평가 데이터 (2012) | {te_hr.mean():.1f} | {int(te_hr.max())} |",
        f"| 학습 데이터 전체 시간대 최대 | - | {int(train_df[target].max())} |",
        "",
    ]

    path = Path("results/error_analysis.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def evaluate(cfg: dict):
    # 데이터 로드
    train_df, test_df = data_mod.run(cfg)
    features, target = data_mod.get_features(cfg)

    X_test = test_df[features]
    y_test = test_df[target].values

    # 모델 로드
    model_path = Path(cfg["paths"]["model"])
    if not model_path.exists():
        # sys.exit 대신 예외 → pipeline.py가 실패 기록을 남기고 중단
        raise FileNotFoundError(f"모델 파일 없음: {model_path} — 먼저 make train 실행")

    payload  = joblib.load(model_path)
    model    = payload["model"]
    b_mean   = payload["baseline_mean"]
    b_hr     = payload["baseline_hr"]

    # 예측
    y_pred      = model.predict(X_test)
    y_base_mean = np.full_like(y_test, b_mean, dtype=float)
    y_base_hr   = test_df["hr"].map(b_hr).values

    # 지표 계산
    metrics = {
        "n_test": len(y_test),
        "model": {
            "MAE":  round(mae(y_test, y_pred), 4),
            "RMSE": round(rmse(y_test, y_pred), 4),
        },
        "baseline_mean": {
            "MAE":  round(mae(y_test, y_base_mean), 4),
            "RMSE": round(rmse(y_test, y_base_mean), 4),
        },
        "baseline_hr": {
            "MAE":  round(mae(y_test, y_base_hr), 4),
            "RMSE": round(rmse(y_test, y_base_hr), 4),
        },
        "unit": "대/시간",
    }

    log.info("=== 평가 결과 ===")
    log.info("모델        — MAE: %.2f, RMSE: %.2f", metrics["model"]["MAE"], metrics["model"]["RMSE"])
    log.info("베이스라인(평균) — MAE: %.2f, RMSE: %.2f", metrics["baseline_mean"]["MAE"], metrics["baseline_mean"]["RMSE"])
    log.info("베이스라인(hr별)  — MAE: %.2f, RMSE: %.2f", metrics["baseline_hr"]["MAE"], metrics["baseline_hr"]["RMSE"])

    # 저장
    metrics_path = Path(cfg["paths"]["metrics"])
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    log.info("지표 저장: %s", metrics_path)

    # 오답 분석 — 오차 가장 큰 1건
    errors = np.abs(y_test - y_pred)
    worst_idx = int(np.argmax(errors))
    worst_row = test_df.iloc[worst_idx]
    error_path = _write_error_analysis(
        worst_row, float(y_pred[worst_idx]), train_df, test_df, features, target
    )
    log.info("오답 분석 저장: %s", error_path)

    run_log.save(
        stage="evaluate",
        status="success",
        extra={
            "model_version": run_log.sha256_file(model_path)[:12],
            "model_path":    str(model_path),
            "n_test":        len(y_test),
            "metrics":       metrics,
            "outputs":       [str(metrics_path), str(error_path)],
        },
    )
    return metrics


if __name__ == "__main__":
    cfg_path = Path("config/config.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    evaluate(cfg)
