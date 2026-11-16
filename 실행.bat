@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 혼디
if not exist ".venv\Scripts\python.exe" (
  echo 먼저 "설치.bat"을 실행해 주세요.
  pause
  exit /b 1
)
echo 혼디를 시작합니다. 잠시 뒤 브라우저가 열립니다.
echo 이 창을 닫으면 혼디가 종료되고 이번 세션 자료가 삭제됩니다(못 지운 자료는 다음 실행 때 정리).
".venv\Scripts\python.exe" -m app.server
pause
