@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title 혼디 설치
echo ============================================
echo  혼디 설치 - 제주빅데이터센터 동행 Agent
echo ============================================
echo.
set "PY="
set "PYEXE="
call :findpy
if not defined PY (
  echo [1/4] 파이썬 3.11~3.13을 찾지 못했습니다. winget으로 Python 3.12 설치를 시도합니다...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  call :findpy
)
if not defined PY (
  echo.
  echo [오류] 파이썬을 설치하지 못했습니다.
  echo   https://www.python.org/downloads/ 에서 Python 3.12를 내려받아 설치한 뒤
  echo   이 파일^(설치.bat^)을 다시 실행해 주세요. 설치 화면에서 "Add python.exe to PATH"를 체크하세요.
  pause
  exit /b 1
)
echo [1/4] 파이썬: %PY%
if not exist ".venv\Scripts\python.exe" (
  echo [2/4] 가상환경^(.venv^)을 만듭니다...
  if defined PYEXE ( "%PYEXE%" -m venv .venv ) else ( %PY% -m venv .venv )
  if errorlevel 1 ( echo [오류] 가상환경을 만들지 못했습니다. & pause & exit /b 1 )
) else (
  echo [2/4] 기존 가상환경을 사용합니다.
)
echo [3/4] 필요한 패키지^(duckdb, matplotlib^)를 설치합니다...
if exist "wheels\" (
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheels -r requirements.txt
) else (
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
)
if errorlevel 1 ( echo [오류] 패키지 설치에 실패했습니다. 인터넷 연결 또는 보안 프로그램을 확인해 주세요. & pause & exit /b 1 )
if not exist "config.ini" copy /y "config.example.ini" "config.ini" >nul
echo [4/4] 설치 점검...
".venv\Scripts\python.exe" -m app.selfcheck_cli
".venv\Scripts\python.exe" tools\list_ext_modules.py > "확장모듈_목록.txt"
echo.
echo 센터 PC 보안정책으로 실행이 막히면 "확장모듈_목록.txt"의 폴더를 허용 등록해 달라고 센터 운영자에게 요청하세요.
echo.
echo 설치가 끝났습니다. 이제 "실행.bat"을 두 번 클릭하세요.
pause
exit /b 0

:findpy
if defined HONDI_PYTHON if exist "%HONDI_PYTHON%" ( set "PY=%HONDI_PYTHON%" & set "PYEXE=%HONDI_PYTHON%" & exit /b 0 )
for %%V in (3.12 3.13 3.11) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  for %%P in ("%LocalAppData%\Programs\Python\Python312\python.exe" "%LocalAppData%\Programs\Python\Python313\python.exe" "%LocalAppData%\Programs\Python\Python311\python.exe" "%ProgramFiles%\Python312\python.exe") do (
    if not defined PY if exist %%P ( set "PY=%%~P" & set "PYEXE=%%~P" )
  )
)
exit /b 0
