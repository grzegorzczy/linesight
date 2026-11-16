# E6-03: broker tokenów GCP (impersonation jetson-edge) dla Jetsona.
FROM mirror.gcr.io/library/python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY token_broker.py .
EXPOSE 8010
CMD ["python", "-u", "token_broker.py"]
