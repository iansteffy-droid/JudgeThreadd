@echo off
start cmd /k "poetry run uvicorn app.main:app --reload"
start cmd /k "cd /d frontend && npm run dev"
