FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# PORT being set makes app.py listen on 0.0.0.0; most hosts override it with their own
ENV PORT=8000
EXPOSE 8000
CMD ["python", "app.py"]
