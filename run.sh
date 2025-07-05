#!/bin/bash

# Terabox Download Bot Startup Script

echo "🚀 Starting Terabox Download Bot..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}$1${NC}"
}

# Check if .env file exists
if [ ! -f .env ]; then
    print_warning ".env file not found!"
    print_status "Creating .env template..."
    python3 config.py
    print_error "Please configure your .env file with bot token and admin ID"
    exit 1
fi

# Load environment variables
if [ -f .env ]; then
    print_status "Loading environment variables..."
    set -a
    source .env
    set +a
fi

# Check required environment variables
if [ -z "$BOT_TOKEN" ] || [ "$BOT_TOKEN" = "YOUR_BOT_TOKEN_HERE" ]; then
    print_error "BOT_TOKEN is not set in .env file!"
    exit 1
fi

if [ -z "$ADMIN_ID" ] || [ "$ADMIN_ID" = "123456789" ]; then
    print_error "ADMIN_ID is not set in .env file!"
    exit 1
fi

# Create downloads directory
print_status "Creating downloads directory..."
mkdir -p downloads

# Check if MongoDB is running
print_status "Checking MongoDB connection..."
if ! python3 -c "
import pymongo
try:
    client = pymongo.MongoClient('$MONGO_URI', serverSelectionTimeoutMS=2000)
    client.server_info()
    print('MongoDB connection successful')
except Exception as e:
    print(f'MongoDB connection failed: {e}')
    exit(1)
" 2>/dev/null; then
    print_warning "MongoDB connection failed. Make sure MongoDB is running."
    print_status "Starting MongoDB..."
    
    # Try to start MongoDB
    if command -v systemctl &> /dev/null; then
        sudo systemctl start mongodb || sudo systemctl start mongod
    elif command -v service &> /dev/null; then
        sudo service mongodb start || sudo service mongod start
    else
        print_error "Cannot start MongoDB. Please start it manually."
        exit 1
    fi
    
    # Wait for MongoDB to start
    sleep 5
fi

# Install dependencies if needed
if [ ! -d "venv" ]; then
    print_status "Creating virtual environment..."
    python3 -m venv venv
fi

print_status "Activating virtual environment..."
source venv/bin/activate

print_status "Installing/updating dependencies..."
pip install -r requirements.txt

# Check if all dependencies are installed
print_status "Checking dependencies..."
python3 -c "
import sys
required_packages = [
    'telegram', 'aiohttp', 'motor', 'flask', 'requests', 'aiofiles'
]
for package in required_packages:
    try:
        __import__(package)
    except ImportError:
        print(f'Missing package: {package}')
        sys.exit(1)
print('All dependencies are installed')
"

if [ $? -ne 0 ]; then
    print_error "Some dependencies are missing. Please run: pip install -r requirements.txt"
    exit 1
fi

# Check bot token validity
print_status "Validating bot token..."
if ! python3 -c "
import requests
import sys
import os

token = os.environ.get('BOT_TOKEN')
if not token:
    print('Bot token not found')
    sys.exit(1)

try:
    response = requests.get(f'https://api.telegram.org/bot{token}/getMe', timeout=10)
    if response.status_code == 200:
        bot_info = response.json()
        if bot_info['ok']:
            print(f'Bot token is valid. Bot name: {bot_info[\"result\"][\"first_name\"]}')
        else:
            print('Invalid bot token')
            sys.exit(1)
    else:
        print('Failed to validate bot token')
        sys.exit(1)
except Exception as e:
    print(f'Error validating bot token: {e}')
    sys.exit(1)
"; then
    print_error "Bot token validation failed!"
    exit 1
fi

# Display configuration
print_header "🤖 Bot Configuration"
echo "Bot Token: ${BOT_TOKEN:0:10}...${BOT_TOKEN: -10}"
echo "Admin ID: $ADMIN_ID"
echo "MongoDB URI: $MONGO_URI"
echo "Download Path: ${DOWNLOAD_PATH:-./downloads/}"
echo "Max File Size: ${MAX_FILE_SIZE:-2147483648} bytes"
echo "Port: ${PORT:-8080}"
echo ""

# Function to cleanup on exit
cleanup() {
    print_status "Shutting down bot..."
    kill $BOT_PID 2>/dev/null
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Start the bot
print_header "🚀 Starting Terabox Download Bot"
print_status "Bot is starting up..."
print_status "Press Ctrl+C to stop"
print_status "Health check available at: http://localhost:${PORT:-8080}/"
echo ""

# Run the bot
python3 bot.py &
BOT_PID=$!

# Wait for the bot process
wait $BOT_PID
