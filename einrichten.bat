@echo off
rem Richtet diesen Ordner portabel ein -- ohne vorhandenes Python, ohne
rem Installation, ohne Adminrechte. Danach startet start.bat das Programm.
rem Der ganze Ordner laesst sich anschliessend kopieren (USB-Stick, anderer PC).
rem
rem   einrichten.bat              Bilder per Cloud-API, Boxen und Training
rem                               auf der eigenen Karte (ab 6 GB), ~9 GB
rem   einrichten.bat training     nur Detektor-Training (YOLO26, D-FINE) --
rem                               z. B. Notebook mit RTX 1000 Ada, ~4 GB
rem   einrichten.bat nurcloud     nur Bilder per Cloud-API, ~100 MB
rem   einrichten.bat lokal        dazu Qwen-Image auf der eigenen Karte
rem                               (braucht ~17 GB Grafikspeicher, ~40 GB)
rem   ... cu126                   PyTorch fuer GTX 10xx statt CUDA 13.0
rem   ... ohnemodelle             Modelle erst beim ersten Gebrauch laden
rem
rem Darf mehrfach laufen; was schon da ist, wird nur geprueft.
setlocal
cd /d "%~dp0"

rem Schalter einzeln einsammeln -- in einem for-Block saehe %ARGS% nur
rem seinen Startwert.
set "ARGS="
call :sammeln %*

set "PYV=3.12.10"
if not exist "python\python.exe" (
  echo Lade Python %PYV% ^(eingebettet, von python.org^) ...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12';" ^
    "Invoke-WebRequest 'https://www.python.org/ftp/python/%PYV%/python-%PYV%-embed-amd64.zip' -OutFile 'python-embed.zip';" ^
    "Expand-Archive 'python-embed.zip' 'python' -Force; Remove-Item 'python-embed.zip'" || goto fehler
)
if not exist "python\python.exe" goto fehler

"python\python.exe" "portable\bauen.py" --hier%ARGS% || goto fehler
echo.
echo Eingerichtet. Starten mit start.bat
if "%~1"=="" pause
exit /b 0

:sammeln
if "%~1"=="" exit /b 0
if /i "%~1"=="training"    set "ARGS=%ARGS% --training"
if /i "%~1"=="nurcloud"    set "ARGS=%ARGS% --nurcloud"
if /i "%~1"=="lokal"       set "ARGS=%ARGS% --lokal"
if /i "%~1"=="ohnemodelle" set "ARGS=%ARGS% --ohne-modelle"
if /i "%~1"=="cu126"       set "ARGS=%ARGS% --cuda cu126"
shift
goto sammeln

:fehler
echo.
echo Die Einrichtung ist nicht durchgelaufen -- die Meldung steht oben.
echo Haeufigste Ursache: keine Internetverbindung oder ein Virenscanner.
pause
exit /b 1
