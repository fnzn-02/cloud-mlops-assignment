# Apple Silicon Mac에서 빌드할 때 반드시 --platform linux/amd64 사용
# docker build --platform linux/amd64 -t bike-demand .

FROM public.ecr.aws/lambda/python:3.11

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 서비스 코드 복사
COPY service/app.py ${LAMBDA_TASK_ROOT}/app.py

# Lambda 핸들러 지정
CMD ["app.handler"]
