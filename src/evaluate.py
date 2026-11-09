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


def evaluate(cfg: dict):
    # 데이터 로드
    _, test_df = data_mod.run(cfg)
    features, target = data_mod.get_features(cfg)

    X_test = test_df[features]
    y_test = test_df[target].values

    # 모델 로드
    model_path = Path(cfg["paths"]["model"])
    if not model_path.exists():
        log.error("모델 파일 없음: %s — 먼저 make train 실행", model_path)
        sys.exit(1)

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

    analysis_lines = [
        "# 오답 분석 (오차 최대 1건)\n",
        f"- **인덱스**: {worst_idx}",
        f"- **입력**:",
        f"  ```",
    ]
    for col in features:
        analysis_lines.append(f"  {col}: {worst_row[col]}")
    analysis_lines += [
        f"  ```",
        f"- **정답(cnt)**: {int(y_test[worst_idx])} 대/시간",
        f"- **예측값**: {y_pred[worst_idx]:.1f} 대/시간",
        f"- **오차**: {errors[worst_idx]:.1f} 대/시간",
        "",
        "## 원인 추정",
        "- 2012년에는 2011년 대비 이용자 수가 크게 증가(yr 피처 미사용으로 반영 어려움)",
        "- 특수 이벤트·공휴일 조합, 또는 급격한 날씨 변화로 대여량이 비정상적으로 높았을 가능성",
        "- 모델이 학습하지 못한 극단적 수요 패턴",
    ]

    error_path = Path("results/error_analysis.md")
    error_path.parent.mkdir(parents=True, exist_ok=True)
    with open(error_path, "w") as f:
        f.write("\n".join(analysis_lines))
    log.info("오답 분석 저장: %s", error_path)

    run_log.save(
        stage="evaluate",
        status="success",
        extra={"metrics": metrics},
    )
    return metrics


if __name__ == "__main__":
    cfg_path = Path("config/config.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    evaluate(cfg)
