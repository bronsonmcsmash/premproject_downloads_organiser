@echo off
cd /d "%~dp0"
.venv\Scripts\pyinstaller.exe --onefile --windowed --clean --icon assets\icon.ico --name ProjectOrganizer --add-data "assets;assets" main.py
echo.
echo Done. Press any key...
pause
