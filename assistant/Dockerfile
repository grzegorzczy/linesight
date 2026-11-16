# E5-08: usługa asystenta (FastAPI) na laptopie, w compose obok bazy.
# Build z głównego folderu repo (context: ..), bo do obrazu trafia też instrukcja docs/kb (indeksowanie z kontenera).
FROM mirror.gcr.io/library/python:3.12-slim
WORKDIR /app
COPY assistant/requirements.txt .
# PyTorch w wersji CPU (ok. 200 MB zamiast ok. 2,5 GB z CUDA): w kontenerze liczymy tylko embeddingi pytań e5-small,
# LLM działa w Ollamie na hoście (GPU) albo w Gemini
RUN pip install --no-cache-dir torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt
COPY assistant/*.py ./
COPY docs/kb /docs/kb
# model embeddingów w wolumenie hf-cache: pobierany raz (ok. 470 MB), nie przy każdym buildzie
ENV HF_HOME=/hf
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
