@echo off
title TRAFFIC CONTROL SYSTEM - COMPLETE SETUP

echo ==========================================
echo TRAFFIC CONTROL SYSTEM - COMPLETE SETUP
echo ==========================================
echo.

REM Check current directory
echo Current directory: %cd%
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python 3.8 or higher from python.org
    pause
    exit /b 1
)

echo Python found.
echo.

REM Create virtual environment
if exist "traffic_env" (
    echo Virtual environment already exists.
    set /p recreate="Recreate? (y/n): "
    if /i "%recreate%"=="y" (
        rmdir /s /q traffic_env
        echo Old environment removed.
    )
)

if not exist "traffic_env" (
    echo Creating virtual environment...
    python -m venv traffic_env
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment!
        echo Make sure Python is installed correctly.
        pause
        exit /b 1
    )
    echo Virtual environment created.
)

REM Activate environment
echo Activating environment...
call traffic_env\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install packages
echo Installing packages from requirements.txt...
if exist "requirements.txt" (
    python -m pip install -r requirements.txt
) else (
    echo requirements.txt not found, installing default packages...
    python -m pip install flask streamlit requests plotly numpy pyserial stable-baselines3 gymnasium torch colorama pandas matplotlib seaborn werkzeug jinja2 altair tqdm tensorboard opencv-python scikit-learn
)

if errorlevel 1 (
    echo ERROR: Failed to install packages!
    echo Check your internet connection and try again.
    pause
    exit /b 1
)

echo Packages installed successfully.
echo.

REM Create directories if they don't exist
if not exist "models" mkdir models
if not exist "logs" mkdir logs
if not exist "data" mkdir data

echo Created required directories: models, logs, data
echo.

REM Check if model exists
if not exist "models\ppo_sumo_final.zip" (
    echo ⚠️ Model not found: models\ppo_sumo_final.zip
    set /p train_model="Do you want to train the model now? (y/n): "
    if /i "%train_model%"=="y" (
        echo 🎓 Starting RL Training...
        python train_rl.py
        if errorlevel 1 (
            echo ERROR: Training failed!
        ) else (
            echo ✅ Training completed successfully!
        )
    ) else (
        echo Note: Place your trained model in models\ directory
        echo You can also run: python train_rl.py later
    )
)

echo.
echo ==========================================
echo SETUP COMPLETE!
echo ==========================================
echo.
echo To run the system, use run_system.bat or:
echo 1. traffic_env\Scripts\activate
echo 2. python backend.py
echo 3. streamlit run dashboard.py
echo.
echo Available batch files:
echo - run_system.bat: Run complete system
echo - start_backend.bat: Start backend only
echo - start_dashboard.bat: Start dashboard only
echo - start_controller.bat: Start AI controller only
echo.
pause