FROM python:3.12-slim
# Non-root user with a writable app folder (required by Hugging Face Spaces, fine everywhere else)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY --chown=user . .
# PORT being set makes app.py listen on 0.0.0.0; most hosts override it with their own
ENV PORT=8000
EXPOSE 8000
CMD ["python", "app.py"]
