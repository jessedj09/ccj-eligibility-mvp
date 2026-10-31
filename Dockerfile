# 판정 API(api/main.py) 배포 이미지 — Render(싱가포르) 기준, 같은 이미지를 어느 호스팅·AWS에서나 쓴다.
# 설정은 환경변수만: DATABASE_URL(없으면 저장 없이 동작), CCJ_AUTO_JUDGE_PUBLIC, CCJ_CORS_ORIGINS, PORT(호스팅이 정함).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt requirements-api.txt ./
RUN pip install -r requirements-api.txt

COPY . .
# 등록 공고 원문 추출 캐시를 이미지에 넣어 둔다 — 첫 업로드가 느려지지 않게(tools/warm_cache.py)
RUN python tools/warm_cache.py \
    && useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
