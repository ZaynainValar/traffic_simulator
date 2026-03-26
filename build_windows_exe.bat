@echo off
setlocal

where py >nul 2>nul
if %errorlevel% neq 0 (
    echo Python launcher 'py' was not found.
    echo Install Python from python.org and enable Add python.exe to PATH.
    pause
    exit /b 1
)

py -m pip install --upgrade pip
if %errorlevel% neq 0 goto :fail

py -m pip install pyinstaller numpy matplotlib pillow imageio imageio-ffmpeg
if %errorlevel% neq 0 goto :fail

py -m PyInstaller --noconfirm --clean --onefile --windowed --name TrafficSimulatorUI traffic_simulator_app.py
if %errorlevel% neq 0 goto :fail

echo.
echo Build complete. Your executable should be in the dist folder.
pause
exit /b 0

:fail
echo.
echo Build failed.
pause
exit /b 1
