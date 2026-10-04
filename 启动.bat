@echo off
chcp 65001 >nul
cd /d %~dp0
"C:\Users\lyj\.workbuddy\binaries\python\envs\snapvid\Scripts\python.exe" main.py
pause
