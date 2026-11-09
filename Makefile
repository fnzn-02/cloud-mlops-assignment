.PHONY: all data train evaluate deploy invoke clean-cloud help

# .env 로드 (파일 있을 때만)
-include .env
export

help:
	@echo "사용 가능한 명령:"
	@echo "  make data         데이터 다운로드, 검증, 분할"
	@echo "  make train        모델 학습 및 저장"
	@echo "  make evaluate     평가 지표 계산 및 저장"
	@echo "  make deploy       S3 업로드 + ECR push + Lambda 배포"
	@echo "  make invoke       Lambda 실제 호출 테스트"
	@echo "  make all          data → train → evaluate"
	@echo "  make clean-cloud  클라우드 자원 삭제"

all: data train evaluate

data:
	python3 src/pipeline.py --stage data

train:
	python3 src/pipeline.py --stage train

evaluate:
	python3 src/pipeline.py --stage evaluate

deploy:
	bash scripts/deploy.sh

invoke:
	bash scripts/invoke.sh

clean-cloud:
	bash scripts/cleanup.sh
