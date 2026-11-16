# Apple Silicon Mac에서 빌드할 때 반드시 --platform linux/amd64 사용
# 저장소 루트에서 실행 (requirements.txt, data/model.joblib 를 COPY하므로 빌드 컨텍스트는 루트):
# docker build --platform linux/amd64 -f service/Dockerfile -t bike-demand .

# 로컬 학습 환경과 같은 Python 3.14 (모델 파일 호환성)
FROM public.ecr.aws/lambda/python:3.14

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 모델 포함 (Lambda 실행 역할에 S3 읽기 권한이 없어 이미지에 넣는다 — service/app.py 참고)
COPY data/model.joblib ${LAMBDA_TASK_ROOT}/model/model.joblib
ENV MODEL_PATH=${LAMBDA_TASK_ROOT}/model/model.joblib

# 서비스 코드 복사
COPY service/app.py ${LAMBDA_TASK_ROOT}/app.py

# Lambda 핸들러 지정
CMD ["app.handler"]
