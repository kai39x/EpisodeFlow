@echo off
chcp 65001 >nul
cd /d "%~dp0"
title EpisodeFlow - build
rem Builds release\EpisodeFlow.exe

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto no_python

for /f "delims=" %%v in ('%PY% -c "import re;s=open('src/episodeflow.py',encoding='utf-8').read();print(re.search('VERSION = .([0-9.]+)',s).group(1))"') do set "VER=%%v"
echo Building EpisodeFlow %VER%
echo.

echo [1/3] Build tools (needs internet the first time)...
%PY% -m pip install --upgrade --quiet pyinstaller pywebview
if errorlevel 1 goto failed
set "WEBVIEW=--collect-all webview"
%PY% -c "import webview" >nul 2>nul
if errorlevel 1 (
  set "WEBVIEW="
  echo     Note: pywebview isn't available, so the app will open in an Edge window without drag and drop.
)

echo [2/3] Building release\EpisodeFlow.exe ...
if not exist "release" mkdir "release"
%PY% -m PyInstaller --noconfirm --clean --log-level ERROR --onefile --windowed --name EpisodeFlow ^
  --distpath "%~dp0release" --workpath "%~dp0build" --specpath "%~dp0build" ^
  --icon "%~dp0assets\EpisodeFlow.ico" --add-data "%~dp0src\episodeflow_ui.html;." %WEBVIEW% ^
  "%~dp0src\episodeflow_gui.py"
if errorlevel 1 goto failed

echo [3/3] Cleaning up...
rmdir /s /q "%~dp0build" >nul 2>nul

echo.
echo Done: release\EpisodeFlow.exe
echo.
pause
exit /b

:no_python
echo Python 3 is needed to build EpisodeFlow (not to run it): https://www.python.org/downloads/
pause
exit /b

:failed
echo.
echo The build stopped because of an error, see the text above.
pause
