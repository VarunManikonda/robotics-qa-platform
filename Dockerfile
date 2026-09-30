FROM python:3.12-slim
WORKDIR /srv
COPY dashboard/ ./dashboard/
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.29"
ENV QA_DB_PATH=/data/qa_runs.sqlite3
VOLUME /data
EXPOSE 8000
WORKDIR /srv/dashboard
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
