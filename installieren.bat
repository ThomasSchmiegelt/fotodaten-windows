@echo off
rem Einrichtung unter Windows: virtuelle Umgebung qwen_bild, PyTorch mit CUDA,
rem dann requirements.txt. Einmal ausfuehren, danach start.bat.
rem
rem   installieren.bat            CUDA 13.0 (RTX 20xx und neuer, Treiber ab 580)
rem   installieren.bat cu126      CUDA 12.6 (auch GTX 10xx / Pascal)
rem   installieren.bat yolo       zusaetzlich Ultralytics fuer YOLO26
rem
rem pip wird immer als "python -m pip" aufgerufen: auf Rechnern mit
rem Anwendungssteuerung (Smart App Control, WDAC) ist pip.exe oft gesperrt,
rem python.exe dagegen nicht.
setlocal
cd /d "%~dp0"

set "CUDA=cu130"
set "MIT_YOLO="
for %%A in (%*) do (
  if /i "%%A"=="cu126" set "CUDA=cu126"
  if /i "%%A"=="cu128" set "CUDA=cu128"
  if /i "%%A"=="yolo" set "MIT_YOLO=1"
)

where py >nul 2>nul && (set "BASIS=py -3.12") || (set "BASIS=python")
if not exist "qwen_bild\Scripts\python.exe" (
  echo Lege die virtuelle Umgebung qwen_bild an ...
  %BASIS% -m venv qwen_bild || goto fehler
)
set "PY=%~dp0qwen_bild\Scripts\python.exe"

"%PY%" -m pip install --upgrade pip || goto fehler
echo PyTorch mit %CUDA% ...
"%PY%" -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/%CUDA% || goto fehler
"%PY%" -m pip install -r requirements.txt || goto fehler
if defined MIT_YOLO (
  "%PY%" -m pip install -r requirements-yolo.txt || goto fehler
)

"%PY%" -c "import torch; print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
echo.
echo Fertig. Starten mit start.bat
exit /b 0

:fehler
echo.
echo Die Einrichtung ist fehlgeschlagen. Die Meldung steht oben.
exit /b 1
