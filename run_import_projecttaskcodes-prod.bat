@echo off

REM Change directory to your project folder
cd /d "E:\WWW\sspps\"

REM Activate the virtual environment
call venv\Scripts\activate.bat

REM Run the Python script
REM python ics.py

REM Optional: log output for debugging
python import_projecttaskcodes.py >> app/logs/import_projecttaskcodes.log 2>&1