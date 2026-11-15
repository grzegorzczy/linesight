# Kontekst budowania: główny folder repo (docker-compose: context ..), żeby skopiować wspólny kod z anomaly/.
FROM mirror.gcr.io/library/python:3.12-slim
WORKDIR /app
COPY diag/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# E4-08: te same funkcje cech co w treningu (anomaly/data.py, anomaly/features.py) – bez rozjazdu trening/produkcja
COPY anomaly/data.py anomaly/features.py ./
COPY diag/stops.py diag/rules.py diag/drive_health.py diag/diag.py ./
CMD ["python", "-u", "diag.py"]
