@echo off
rem Start Mashwright on Windows (needs Python 3.9+ from python.org or the Microsoft Store).
cd /d "%~dp0\.."
where py >nul 2>nul && (py -3 mashwright.py %*) || (python mashwright.py %*)
