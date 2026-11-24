@echo off
title XiaoFan Agent
start "" http://127.0.0.1:8765
"C:\Users\18146\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" "%~dp0server.py"
pause
