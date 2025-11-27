#!/bin/bash
# Google Scholar Scraper - Command Line Launcher
# Double-click this file to start the scraper

echo "=========================================="
echo "Google Scholar Scraper - Starting..."
echo "=========================================="
echo ""

# Get the directory of this script
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$ROOT_DIR"

APP_DIR="$ROOT_DIR/google_scholar_detail"
cd "$APP_DIR"

# Activate conda environment
echo "🔧 Activating conda environment 'mri_data'..."
if command -v conda &> /dev/null; then
    # Initialize conda for bash
    eval "$(conda shell.bash hook)"
    conda activate mri_data
    if [ $? -eq 0 ]; then
        echo "✅ Conda environment 'mri_data' activated"
    else
        echo "⚠️  Could not activate conda environment 'mri_data'"
        echo "Continuing with current Python environment..."
    fi
else
    echo "⚠️  Conda not found, using system Python"
fi
echo ""

# Use the Python from the activated environment
PYTHON_CMD="/opt/homebrew/anaconda3/envs/mri_data/bin/python"
if [ ! -f "$PYTHON_CMD" ]; then
    # Fallback to any available Python
    if command -v python &> /dev/null; then
        PYTHON_CMD="python"
    elif command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    else
        echo "❌ Python is not installed!"
        echo "Please install Python 3.8 or higher from python.org"
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

echo "Using: $PYTHON_CMD ($(${PYTHON_CMD} --version))"
echo ""

# Check if dependencies are installed
echo "Checking dependencies..."
if ! ${PYTHON_CMD} -c "import selenium" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    ${PYTHON_CMD} -m pip install -r "$ROOT_DIR/requirements.txt"
fi

echo ""
echo "✅ Starting scraper..."
echo ""

# Run the scraper CLI from app directory so outputs stay grouped
${PYTHON_CMD} "$APP_DIR/run_scraper.py" "$@"

echo ""
echo "Application closed."
read -p "Press Enter to exit..."
