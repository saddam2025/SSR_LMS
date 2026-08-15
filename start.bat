@echo off
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --host 127.0.0.1 --port 8000
