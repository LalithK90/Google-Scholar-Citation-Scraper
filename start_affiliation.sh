#!/bin/bash
# Google Scholar Affiliation Scraper - Launcher
# Runs the university_reseachers package CLI

echo "=========================================="
echo "Affiliation Scraper - Starting..."
echo "=========================================="
echo ""

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PKG_DIR="$ROOT_DIR/university_reseachers"

# Activate conda environment
echo "🔧 Activating conda environment 'mri_data'..."
if command -v conda &> /dev/null; then
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

# Check if dependencies are installed
echo "Checking dependencies..."
if ! ${PYTHON_CMD} -c "import selenium" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    ${PYTHON_CMD} -m pip install -r "$ROOT_DIR/requirements.txt"
fi

echo ""
echo "✅ Starting affiliation scraper..."
echo ""
# Change to root dir so the package can be imported via -m
cd "$ROOT_DIR"
# Example usage: pass through args, e.g.
#   ./start_affiliation.sh --mode google-two-phase --universities "University of Colombo"
${PYTHON_CMD} -m university_reseachers.scholar_affiliation_scrapers "$@"

status=$?
echo ""
echo "Application closed (exit: $status)."
read -p "Press Enter to exit..."
