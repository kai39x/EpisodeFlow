@echo off
chcp 65001 >nul
cd /d "%~dp0"
title EpisodeFlow - build
rem Builds release\EpisodeFlow.exe, and release\EpisodeFlow-Setup.exe when NSIS is installed.
rem The build tools go into a .venv folder here,
rem not into your own Python.
rem   build.bat            build, then wait for a key
rem   build.bat nopause    build and exit (GitHub Actions uses this)

set "NOPAUSE="
if /i "%~1"=="nopause" set "NOPAUSE=1"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto no_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto old_python

set "VPY=.venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo Making .venv for the build tools...
  %PY% -m venv .venv
  if errorlevel 1 goto failed
)

for /f "delims=" %%v in ('%VPY% -c "import re;s=open('src/episodeflow.py',encoding='utf-8').read();print(re.search('VERSION = .([0-9.]+)',s).group(1))"') do set "VER=%%v"
echo Building EpisodeFlow %VER%
echo.

echo [1/4] Build tools from requirements-build.txt (needs internet the first time)...
%VPY% -m pip install --quiet --disable-pip-version-check -r requirements-build.txt
if errorlevel 1 goto failed

echo [2/4] Building release\EpisodeFlow.exe ...
if not exist "release" mkdir "release"
%VPY% -m PyInstaller --noconfirm --clean --log-level ERROR --onefile --windowed --name EpisodeFlow ^
  --distpath "%~dp0release" --workpath "%~dp0build" --specpath "%~dp0build" ^
  --icon "%~dp0assets\EpisodeFlow.ico" --add-data "%~dp0src\episodeflow_ui.html;." --collect-all webview ^
  "%~dp0src\episodeflow_gui.py"
if errorlevel 1 goto failed

echo [3/4] Cleaning up...
rmdir /s /q "%~dp0build" >nul 2>nul

echo [4/4] Installer (release\EpisodeFlow-Setup.exe)...
set "NSIS="
where makensis >nul 2>nul && set "NSIS=makensis"
if not defined NSIS if exist "%ProgramFiles(x86)%\NSIS\makensis.exe" set "NSIS=%ProgramFiles(x86)%\NSIS\makensis.exe"
if not defined NSIS if exist "%ProgramFiles%\NSIS\makensis.exe" set "NSIS=%ProgramFiles%\NSIS\makensis.exe"
if defined NSIS (
  "%NSIS%" /V2 /DVERSION=%VER% "%~dp0installer\EpisodeFlow.nsi"
  if errorlevel 1 goto failed
) else (
  echo     NSIS isn't installed, so only the portable EpisodeFlow.exe was made. Get it from https://nsis.sourceforge.io
)

echo.
echo Done: release\EpisodeFlow.exe
if defined NSIS echo       release\EpisodeFlow-Setup.exe
echo.
if not defined NOPAUSE pause
exit /b 0

:no_python
echo Python 3.10 or newer is needed to build EpisodeFlow (not to run it): https://www.python.org/downloads/
if not defined NOPAUSE pause
exit /b 1

:old_python
echo EpisodeFlow needs Python 3.10 or newer to build. Get it from https://www.python.org/downloads/
if not defined NOPAUSE pause
exit /b 1

:failed
echo.
echo The build stopped because of an error, see the text above.
if not defined NOPAUSE pause
exit /b 1
