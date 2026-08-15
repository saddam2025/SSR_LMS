FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 lms

COPY requirements.txt .

RUN pip install --no-cache-dir --timeout=300 --retries=10 -r requirements.txt

COPY --chown=lms:lms . .

RUN chmod 755 /app/container-start.sh

USER lms

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3).read()" || exit 1

CMD ["/app/container-start.sh"]