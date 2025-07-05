import os
from typing import Dict, Any

class Config:
    """Configuration class for Terabox Download Bot"""
    
    # Bot Configuration
    BOT_TOKEN: str = os.environ.get('BOT_TOKEN', '8037389280:AAG5WfzHcheszs-RHWL8WXszWPkrWjyulp8')
    ADMIN_ID: int = int(os.environ.get('ADMIN_ID', '7910994767'))
    
    # Database Configuration
    MONGO_URI: str = os.environ.get('MONGO_URI', 'mongodb+srv://Nischay999:Nischay999@cluster0.5kufo.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
    DB_NAME: str = os.environ.get('DB_NAME', 'terabox_bot')
    
    # File Configuration
    DOWNLOAD_PATH: str = os.environ.get('DOWNLOAD_PATH', './downloads/')
    MAX_FILE_SIZE: int = int(os.environ.get('MAX_FILE_SIZE', '2147483648'))  # 2GB in bytes
    CHUNK_SIZE: int = int(os.environ.get('CHUNK_SIZE', '8192'))  # 8KB chunks
    
    # API Configuration
    API_URL: str = "https://noor-terabox-api.woodmirror.workers.dev/api"
    PROXY_URL: str = "https://noor-terabox-api.woodmirror.workers.dev/proxy"
    
    # Server Configuration
    PORT: int = int(os.environ.get('PORT', '8080'))
    HOST: str = os.environ.get('HOST', '0.0.0.0')
    
    # Supported Domains
    SUPPORTED_DOMAINS: list = [
        'terabox.com',
        '1024terabox.com', 
        '4funbox.com',
        'mirrobox.com',
        'momerybox.com',
        'teraboxapp.com'
    ]
    
    # Message Effects
    MESSAGE_EFFECTS: Dict[str, str] = {
        'fire': '5104841245755180586',  # 🔥 Fire effect
        'heart': '5159385139981059251',  # ❤️ Heart effect
        'thumbs_up': '5107584321108051014',  # 👍 Thumbs up effect
        'party': '5046509860389126442',  # 🎉 Party effect
        'star': '5046599351589271638'   # ⭐ Star effect
    }
    
    # Progress Bar Configuration
    PROGRESS_BAR_LENGTH: int = 20
    PROGRESS_UPDATE_INTERVAL: int = 2  # seconds
    
    # Rate Limiting
    MAX_CONCURRENT_DOWNLOADS: int = int(os.environ.get('MAX_CONCURRENT_DOWNLOADS', '5'))
    DOWNLOAD_TIMEOUT: int = int(os.environ.get('DOWNLOAD_TIMEOUT', '3600'))  # 1 hour
    
    # Logging Configuration
    LOG_LEVEL: str = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Bot Messages
    MESSAGES: Dict[str, str] = {
        'welcome': """🚀 **Welcome to Terabox Download Bot!**

🔥 **Features:**
• Fast downloads from Terabox
• Real-time progress tracking
• Download statistics
• Multiple format support
• Easy to use interface

📋 **How to use:**
1. Send me a Terabox link
2. Click the download button
3. Wait for the magic! ✨

💡 **Commands:**
/start - Start the bot
/stats - View your statistics
/help - Get help and support""",
        
        'help': """❓ **Help & Support**

🔗 **Supported Links:**
• Terabox.com
• 1024terabox.com
• 4funbox.com
• Mirrobox.com
• Momerybox.com
• Teraboxapp.com

📋 **How to Download:**
1. Copy Terabox share link
2. Send the link to this bot
3. Click 'Download' button
4. Wait for upload to complete

⚠️ **Limitations:**
• Max file size: 2GB
• Download may take time for large files
• One download per user at a time

🆘 **Need Help?**
Contact: @YourSupportBot""",
        
        'processing': """🔄 **Processing your link...**

⏳ Please wait while I fetch file information...""",
        
        'download_start': """🚀 **Starting download...**

📁 **File:** `{file_name}`
📦 **Size:** {file_size}

⏳ Please wait...""",
        
        'upload_start': """📤 **Uploading to Telegram...**

📁 **File:** `{file_name}`
📦 **Size:** {file_size}

⏳ Please wait...""",
        
        'success': """✅ **Upload Complete!**

📁 **File:** `{file_name}`
📦 **Size:** {file_size}

🎉 **File sent successfully!**""",
        
        'error_invalid_link': """❌ Please send a valid Terabox link!

🔗 **Supported domains:**
• terabox.com
• 1024terabox.com
• 4funbox.com
• mirrobox.com
• momerybox.com
• teraboxapp.com""",
        
        'error_file_too_large': """⚠️ **File too large!**

The file size exceeds the 2GB limit.
Please try with a smaller file.""",
        
        'error_active_download': """⚠️ **You already have an active download!**

Please wait for it to complete before starting a new one.""",
        
        'error_session_expired': """❌ **Session expired!**

Please send the Terabox link again.""",
        
        'error_download_failed': """❌ **Download failed!**

Please try again later or contact support.""",
        
        'error_upload_failed': """❌ **Upload failed!**

The file was downloaded but couldn't be uploaded to Telegram.
This might be due to file size limits or network issues."""
    }
    
    # Keyboard Layouts
    KEYBOARDS: Dict[str, list] = {
        'main': [
            [{"text": "🔥 GitHub", "url": "https://github.com"}],
            [{"text": "📊 Stats", "callback_data": "stats"},
             {"text": "❓ Help", "callback_data": "help"}]
        ],
        
        'file_info': [
            [{"text": "⬇️ Download", "callback_data": "download_file"}],
            [{"text": "🖼️ Thumbnail", "callback_data": "show_thumbnail"}],
            [{"text": "📊 Stats", "callback_data": "stats"}]
        ],
        
        'stats': [
            [{"text": "🔄 Refresh", "callback_data": "stats"}],
            [{"text": "🏠 Home", "callback_data": "start"}]
        ],
        
        'help': [
            [{"text": "🏠 Home", "callback_data": "start"}],
            [{"text": "📊 Stats", "callback_data": "stats"}]
        ]
    }
    
    # File Type Icons
    FILE_ICONS: Dict[str, str] = {
        'video': '🎬',
        'audio': '🎵',
        'image': '🖼️',
        'document': '📄',
        'archive': '📦',
        'application': '⚙️',
        'default': '📁'
    }
    
    # File Extensions Mapping
    FILE_EXTENSIONS: Dict[str, str] = {
        # Video
        'mp4': 'video', 'avi': 'video', 'mkv': 'video', 'mov': 'video',
        'wmv': 'video', 'flv': 'video', 'webm': 'video', '3gp': 'video',
        
        # Audio
        'mp3': 'audio', 'wav': 'audio', 'flac': 'audio', 'aac': 'audio',
        'ogg': 'audio', 'wma': 'audio', 'm4a': 'audio',
        
        # Image
        'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'gif': 'image',
        'bmp': 'image', 'tiff': 'image', 'webp': 'image', 'svg': 'image',
        
        # Document
        'pdf': 'document', 'doc': 'document', 'docx': 'document',
        'xls': 'document', 'xlsx': 'document', 'ppt': 'document',
        'pptx': 'document', 'txt': 'document', 'rtf': 'document',
        
        # Archive
        'zip': 'archive', 'rar': 'archive', '7z': 'archive',
        'tar': 'archive', 'gz': 'archive', 'bz2': 'archive',
        
        # Application
        'exe': 'application', 'msi': 'application', 'deb': 'application',
        'rpm': 'application', 'apk': 'application', 'dmg': 'application'
    }
    
    @classmethod
    def get_file_icon(cls, filename: str) -> str:
        """Get file icon based on file extension"""
        try:
            extension = filename.split('.')[-1].lower()
            file_type = cls.FILE_EXTENSIONS.get(extension, 'default')
            return cls.FILE_ICONS.get(file_type, cls.FILE_ICONS['default'])
        except:
            return cls.FILE_ICONS['default']
    
    @classmethod
    def validate_config(cls) -> bool:
        """Validate configuration settings"""
        required_vars = ['BOT_TOKEN', 'ADMIN_ID']
        
        for var in required_vars:
            if not getattr(cls, var) or getattr(cls, var) == f'YOUR_{var}_HERE':
                print(f"❌ {var} is not set in environment variables!")
                return False
        
        return True
    
    @classmethod
    def get_message_effect(cls, effect_name: str = 'fire') -> str:
        """Get message effect ID"""
        return cls.MESSAGE_EFFECTS.get(effect_name, cls.MESSAGE_EFFECTS['fire'])
    
    @classmethod
    def is_supported_domain(cls, url: str) -> bool:
        """Check if URL contains supported domain"""
        return any(domain in url.lower() for domain in cls.SUPPORTED_DOMAINS)
    
    @classmethod
    def get_keyboard(cls, keyboard_name: str) -> list:
        """Get keyboard layout by name"""
        return cls.KEYBOARDS.get(keyboard_name, cls.KEYBOARDS['main'])
    
    @classmethod
    def format_message(cls, message_key: str, **kwargs) -> str:
        """Format message with parameters"""
        message = cls.MESSAGES.get(message_key, "Message not found")
        return message.format(**kwargs)

# Environment Variables Template
ENV_TEMPLATE = """
# Terabox Download Bot Configuration
# Copy this to .env file and fill in your values

# Bot Configuration (Required)
BOT_TOKEN=your_bot_token_here
ADMIN_ID=your_admin_user_id

# Database Configuration
MONGO_URI=mongodb://localhost:27017/
DB_NAME=terabox_bot

# File Configuration
DOWNLOAD_PATH=./downloads/
MAX_FILE_SIZE=2147483648
CHUNK_SIZE=8192

# Server Configuration
PORT=8080
HOST=0.0.0.0

# Rate Limiting
MAX_CONCURRENT_DOWNLOADS=5
DOWNLOAD_TIMEOUT=3600

# Logging
LOG_LEVEL=INFO
"""

def create_env_file():
    """Create .env file template"""
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write(ENV_TEMPLATE)
        print("✅ Created .env file template")
        print("📝 Please edit .env file with your configuration")
    else:
        print("⚠️ .env file already exists")

if __name__ == '__main__':
    create_env_file()
    
    if Config.validate_config():
        print("✅ Configuration is valid!")
    else:
        print("❌ Configuration validation failed!")
        print("Please set required environment variables.")
