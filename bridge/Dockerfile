# Obraz z kopii Docker Hub u Google (mirror.gcr.io): pobieranie z Docker Hub (CloudFront)
# zrywało się na laptopie – patrz docs/backlog.md, E3-01.
FROM mirror.gcr.io/library/python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY opcua_mqtt_bridge.py .
# -u: wyjście bez buforowania, żeby logi od razu były w `docker logs`
CMD ["python", "-u", "opcua_mqtt_bridge.py"]
