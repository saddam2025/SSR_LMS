FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 lms
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=lms:lms . .
RUN chmod 755 /app/container-start.sh
USER lms
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 CMD python -c "import os,urllib.request; p=os.getenv('PORT','8000'); r=urllib.request.Request('http://127.0.0.1:'+p+'/ready',headers={'Host':'healthcheck.railway.app'}); resp=urllib.request.urlopen(r, timeout=3); raise SystemExit(0 if resp.status==200 else 1)" || exit 1
CMD ["/app/container-start.sh"]
