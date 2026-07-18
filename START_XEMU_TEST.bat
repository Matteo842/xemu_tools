@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"

where py >nul 2>&1
if errorlevel 1 goto try_python
py -3 -c "import sys" >nul 2>&1
if errorlevel 1 goto try_python
py -3 "%~dp0xemu_test_lab.py" %*
exit /b %errorlevel%

:try_python
where python >nul 2>&1
if errorlevel 1 goto no_python
python "%~dp0xemu_test_lab.py" %*
exit /b %errorlevel%

:no_python
echo ERRORE: Python 3 non trovato.
pause
exit /b 1
