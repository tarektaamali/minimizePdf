@echo off
chcp 65001 >nul
rem Sizes are displayed with U+202F, which cp1252 cannot encode:
rem without this, printing a size raises UnicodeEncodeError.
set "PYTHONUTF8=1"
start "" "%~dp0.venv\Scripts\pythonw.exe" -m pdfshrink.web
