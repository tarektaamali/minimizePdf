@echo off
chcp 65001 >nul
start "" "%~dp0.venv\Scripts\pythonw.exe" -m pdfshrink.web
