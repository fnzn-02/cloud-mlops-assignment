"""
pipeline.py — 단계별 실행. 실패 시 다음 단계 중단.

사용:
  python3 src/pipeline.py --stage data
  python3 src/pipeline.py --stage train
  python3 src/pipeline.py --stage evaluate
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import run_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

STAGES = ["data", "train", "evaluate"]


def load_cfg():
    cfg_path = Path("config/config.yaml")
    if not cfg_path.exists():
        log.error("config/config.yaml 없음")
        sys.exit(1)
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def run_stage(stage: str, cfg: dict):
    log.info("=== 단계 시작: %s ===", stage)
    try:
        if stage == "data":
            import data as data_mod
            data_mod.run(cfg)
            run_log.save("data", "success")

        elif stage == "train":
            import train as train_mod
            train_mod.train(cfg)

        elif stage == "evaluate":
            import evaluate as eval_mod
            eval_mod.evaluate(cfg)

        else:
            log.error("알 수 없는 단계: %s (가능: %s)", stage, STAGES)
            sys.exit(1)

        log.info("=== 단계 완료: %s ===", stage)

    except Exception as e:
        log.error("=== 단계 실패: %s — %s ===", stage, e)
        run_log.save(stage, "failed", error=str(e))
        sys.exit(1)  # 다음 단계 중단


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=STAGES)
    args = parser.parse_args()

    cfg = load_cfg()
    run_stage(args.stage, cfg)
