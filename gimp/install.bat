@echo off
rem Kopiert das Qwen-Plugin in GIMPs Plugin-Verzeichnis (Windows).
rem
rem Unter Windows liegt es in %APPDATA%\GIMP\<Version>\plug-ins. Kopiert statt
rem verknuepft: eine symbolische Verknuepfung braucht dort Adminrechte oder den
rem Entwicklermodus. Nach einer Aenderung am Plugin dieses Skript neu ausfuehren.
setlocal enabledelayedexpansion
set "HIER=%~dp0"
set "BASIS=%APPDATA%\GIMP"
set "VERSION="
if exist "%BASIS%" (
  for /f "delims=" %%V in ('dir /b /ad /on "%BASIS%" 2^>nul') do set "VERSION=%%V"
)
rem GIMP noch nie gestartet: das Verzeichnis der installierten Fassung anlegen.
if not defined VERSION set "VERSION=3.2"
set "ZIEL=%BASIS%\%VERSION%\plug-ins\qwen-image"

if exist "%ZIEL%" rmdir /s /q "%ZIEL%"
mkdir "%ZIEL%" || exit /b 1
copy /y "%HIER%qwen-image\qwen-image.py" "%ZIEL%\" >nul || exit /b 1
echo Kopiert nach: %ZIEL%
echo GIMP neu starten, dann unter Filter ^> Qwen.
