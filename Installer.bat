@echo off
chcp 65001 >nul
rem Sizes are displayed with U+202F, which cp1252 cannot encode:
rem without this, printing a size raises UnicodeEncodeError.
set "PYTHONUTF8=1"
setlocal EnableDelayedExpansion

set "APP=%~dp0"
set "UV_VERSION=0.11.19"
set "UV_SHA256=1665fc8e37b5d70a134820d6d7891747471a2ac8bc940ee7af0b69fd03b28d61"
set "UV_URL=https://github.com/astral-sh/uv/releases/download/%UV_VERSION%/uv-x86_64-pc-windows-msvc.zip"
set "UV=%APP%uv.exe"

echo.
echo   Installation de IntactPDF
echo   ---------------------------
echo.

if not exist "%UV%" (
  echo   Telechargement des outils...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "Invoke-WebRequest -Uri '%UV_URL%' -OutFile '%APP%uv.zip';" ^
    "$h=(Get-FileHash '%APP%uv.zip' -Algorithm SHA256).Hash.ToLower();" ^
    "if ($h -ne '%UV_SHA256%') { Remove-Item '%APP%uv.zip'; throw 'somme de controle incorrecte' };" ^
    "Expand-Archive -Path '%APP%uv.zip' -DestinationPath '%APP%' -Force;" ^
    "Remove-Item '%APP%uv.zip'"
  if errorlevel 1 goto failed
)

echo   Preparation de Python...
"%UV%" venv --python 3.12 "%APP%.venv"
if errorlevel 1 goto failed

echo   Installation des composants...
"%UV%" pip install --python "%APP%.venv\Scripts\python.exe" -r "%APP%requirements.txt"
if errorlevel 1 goto failed

echo   Installation du compresseur JBIG2...
rem Optional by design: without it long scans are refused rather than
rem badly compressed, so a failure here warns and carries on.
".venv\Scripts\python.exe" "%APP%scripts\fetch_jbig2.py" "%APP%jbig2"
if errorlevel 1 (
  echo.
  echo   ATTENTION : le compresseur JBIG2 n a pas pu etre installe.
  echo   Le programme fonctionnera, mais les documents longs ne
  echo   pourront pas etre reduits autant.
  echo.
)

echo   Verification...
pushd "%APP%"
".venv\Scripts\python.exe" verify_install.py
set "RC=%errorlevel%"
popd
if not "%RC%"=="0" goto failed

echo   Creation du raccourci...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$desk=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desk 'IntactPDF.lnk'));" ^
  "$s.TargetPath='%APP%IntactPDF.bat';" ^
  "$s.WorkingDirectory='%APP%';" ^
  "$s.IconLocation='%APP%.venv\Scripts\pythonw.exe,0';" ^
  "$s.Description='Réduire la taille d''un PDF';" ^
  "$s.Save()"
if errorlevel 1 goto failed

echo.
echo   Installation terminee.
echo.
pause
exit /b 0

:failed
echo.
echo   L'installation a echoue. Envoyez cette fenetre a votre contact.
echo.
pause
exit /b 1
