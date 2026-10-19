@echo off
rem Startet Bildermacher 1.0 und oeffnet den Browser.
rem
rem   start.bat               -> http://127.0.0.1:7860
rem   start.bat 8080          -> anderer Port
rem   set QWEN_HOST=0.0.0.0 ^& start.bat   -> auch aus dem LAN erreichbar
rem
rem Eingerichtet wird vorher mit einrichten.bat (portabel, empfohlen) oder
rem installieren.bat (virtuelle Umgebung fuer die Entwicklung).
rem Beenden: Strg+C in diesem Fenster oder "Programm beenden" in der Oberflaeche.
setlocal
cd /d "%~dp0"

rem Portabel: eingebettetes Python im Ordner, Modelle unter daten\hf. Ohne
rem "einrichten.bat lokal" rechnet das Bildmodell nie auf der eigenen Karte --
rem Qwen-Image braucht rund 17 GB, eine kleine Karte liefe voll.
if exist "%~dp0python\python.exe" goto portabel
if exist "%~dp0qwen_bild\Scripts\python.exe" goto umgebung
echo Noch nicht eingerichtet - bitte zuerst einrichten.bat ausfuehren.
pause
exit /b 1

:portabel
set "PY=%~dp0python\python.exe"
set "HF_HOME=%~dp0daten\hf"
set "PYTHONNOUSERSITE=1"
if exist "%~dp0daten\bildmodell_lokal.txt" (
  set "QWEN_IMAGE_REVISION=790c92633540aa0cb11d9abf19eb46d861714758"
) else (
  set "QWEN_NUR_CLOUD=1"
)
goto weiter

:umgebung
set "PY=%~dp0qwen_bild\Scripts\python.exe"

:weiter
rem Eigene Einstellungen dieses Rechners (QWEN_IMAGE_REVISION, QWEN_HOST ...)
rem stehen in lokal.bat -- nicht im Repository.
if exist "%~dp0lokal.bat" call "%~dp0lokal.bat"
if not "%~1"=="" set "QWEN_PORT=%~1"
if not defined QWEN_PORT set "QWEN_PORT=7860"
if not defined QWEN_HOST set "QWEN_HOST=127.0.0.1"
rem YOLO26: Gewichte und Einstellungen beim Programm, nicht in %APPDATA%.
set "YOLO_CONFIG_DIR=%~dp0modelle\yolo\einstellungen"
rem Modelle ueber normales HTTP laden. Der Xet-Weg von Hugging Face blieb
rem hier gemessen bei 0 Byte haengen, HTTP lief mit 6,5 MB/s.
set "HF_HUB_DISABLE_XET=1"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
rem Umlaute in Meldungen und Dateien: Python ueberall in UTF-8.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem Browser oeffnen, sobald der Server antwortet -- im Hintergrund.
start "" /b "%PY%" "%~dp0webui\browser_oeffnen.py"
"%PY%" "%~dp0webui\server.py"
if errorlevel 1 pause
