import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Dict, Optional
import aiohttp
import aiofiles
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from urllib.parse import quote
import json
import threading
from flask import Flask, jsonify
import requests

# Configuration
class Config:
    BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
    DB_NAME = os.environ.get('DB_NAME', 'terabox_bot')
    ADMIN_ID = int(os.environ.get('ADMIN_ID', '123456789'))
    DOWNLOAD_PATH = os.environ.get('DOWNLOAD_PATH', './downloads/')
    MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', '2147483648'))  # 2GB
    API_URL = "https://noor-terabox-api.woodmirror.workers.dev/api"
    PROXY_URL = "https://noor-terabox-api.woodmirror.workers.dev/proxy"

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB connection
client = AsyncIOMotorClient(Config.MONGO_URI)
db = client[Config.DB_NAME]

# Collections
users_collection = db.users
downloads_collection = db.downloads
stats_collection = db.stats

# Global variables
active_downloads = {}

# Flask app for health check
app = Flask(__name__)

@app.route('/')
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/stats')
def get_stats():
    return jsonify({"active_downloads": len(active_downloads)})

def run_flask():
    app.run(host='0.0.0.0', port=8080, debug=False)

# Database functions
async def init_db():
    """Initialize database collections"""
    try:
        await users_collection.create_index("user_id", unique=True)
        await downloads_collection.create_index("user_id")
        await stats_collection.create_index("date")
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

async def add_user(user_id: int, username: str = None, first_name: str = None):
    """Add or update user in database"""
    try:
        user_data = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "joined_at": datetime.now(),
            "total_downloads": 0,
            "total_size": 0
        }
        await users_collection.update_one(
            {"user_id": user_id},
            {"$setOnInsert": user_data},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error adding user: {e}")

async def update_user_stats(user_id: int, file_size: int):
    """Update user download statistics"""
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$inc": {"total_downloads": 1, "total_size": file_size}}
        )
    except Exception as e:
        logger.error(f"Error updating user stats: {e}")

async def log_download(user_id: int, file_name: str, file_size: int, status: str):
    """Log download activity"""
    try:
        download_data = {
            "user_id": user_id,
            "file_name": file_name,
            "file_size": file_size,
            "status": status,
            "timestamp": datetime.now()
        }
        await downloads_collection.insert_one(download_data)
    except Exception as e:
        logger.error(f"Error logging download: {e}")

# Utility functions
def format_bytes(bytes_size: int) -> str:
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"

def create_progress_bar(percentage: float, length: int = 20) -> str:
    """Create a progress bar"""
    filled = int(length * percentage / 100)
    bar = '█' * filled + '░' * (length - filled)
    return f"[{bar}] {percentage:.1f}%"

async def fetch_terabox_info(url: str) -> Dict:
    """Fetch file information from Terabox API"""
    try:
        api_url = f"{Config.API_URL}?url={quote(url)}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if "error" in data:
                        return {"error": data["error"]}
                    return data
                else:
                    return {"error": "Failed to fetch file information"}
    except Exception as e:
        logger.error(f"Error fetching Terabox info: {e}")
        return {"error": str(e)}

async def download_file(url: str, file_name: str, file_size: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Download file with progress tracking"""
    user_id = update.effective_user.id
    
    try:
        # Create download directory
        os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)
        file_path = os.path.join(Config.DOWNLOAD_PATH, file_name)
        
        # Initialize progress tracking
        active_downloads[user_id] = {
            "file_name": file_name,
            "file_size": file_size,
            "downloaded": 0,
            "start_time": time.time(),
            "status": "downloading"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    async with aiofiles.open(file_path, 'wb') as file:
                        downloaded = 0
                        last_update = 0
                        
                        async for chunk in response.content.iter_chunked(8192):
                            await file.write(chunk)
                            downloaded += len(chunk)
                            active_downloads[user_id]["downloaded"] = downloaded
                            
                            # Update progress every 2 seconds
                            if time.time() - last_update > 2:
                                percentage = (downloaded / file_size) * 100
                                progress_bar = create_progress_bar(percentage)
                                
                                progress_text = (
                                    f"🔄 **Downloading...**\n\n"
                                    f"📁 **File:** `{file_name}`\n"
                                    f"📊 **Progress:** {progress_bar}\n"
                                    f"💾 **Size:** {format_bytes(downloaded)} / {format_bytes(file_size)}\n"
                                    f"⚡ **Speed:** {format_bytes(downloaded / (time.time() - active_downloads[user_id]['start_time']))}/s"
                                )
                                
                                try:
                                    await update.effective_message.edit_text(
                                        progress_text,
                                        parse_mode='Markdown'
                                    )
                                except:
                                    pass
                                
                                last_update = time.time()
                        
                        active_downloads[user_id]["status"] = "uploading"
                        return file_path
                else:
                    return False
    except Exception as e:
        logger.error(f"Download error: {e}")
        if user_id in active_downloads:
            del active_downloads[user_id]
        return False

# Bot handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    await add_user(user.id, user.username, user.first_name)
    
    welcome_text = (
        "🚀 **Welcome to Terabox Download Bot!**\n\n"
        "🔥 **Features:**\n"
        "• Fast downloads from Terabox\n"
        "• Progress tracking\n"
        "• Statistics\n"
        "• Easy to use\n\n"
        "📋 **How to use:**\n"
        "1. Send me a Terabox link\n"
        "2. Click download button\n"
        "3. Wait for the magic! ✨\n\n"
        "💡 **Commands:**\n"
        "/start - Start the bot\n"
        "/stats - View your stats\n"
        "/help - Get help"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔥 GitHub", url="https://github.com")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats"),
         InlineKeyboardButton("❓ Help", callback_data="help")]
    ]
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard),
        message_effect_id=5104841245755180586
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    user_id = update.effective_user.id
    
    try:
        user_data = await users_collection.find_one({"user_id": user_id})
        total_users = await users_collection.count_documents({})
        total_downloads = await downloads_collection.count_documents({})
        
        if user_data:
            stats_text = (
                f"📊 **Your Statistics**\n\n"
                f"👤 **User:** {update.effective_user.first_name}\n"
                f"📥 **Downloads:** {user_data.get('total_downloads', 0)}\n"
                f"💾 **Total Size:** {format_bytes(user_data.get('total_size', 0))}\n"
                f"📅 **Joined:** {user_data.get('joined_at', 'Unknown').strftime('%Y-%m-%d')}\n\n"
                f"🌐 **Global Stats:**\n"
                f"👥 **Total Users:** {total_users}\n"
                f"📊 **Total Downloads:** {total_downloads}\n"
                f"🤖 **Active Downloads:** {len(active_downloads)}"
            )
        else:
            stats_text = "❌ No statistics available. Use the bot first!"
            
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="stats")]]
        
        await update.message.reply_text(
            stats_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard),
            message_effect_id=5104841245755180586
        )
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await update.message.reply_text("❌ Error fetching statistics!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = (
        "❓ **Help & Support**\n\n"
        "🔗 **Supported Links:**\n"
        "• Terabox.com\n"
        "• 1024terabox.com\n"
        "• 4funbox.com\n"
        "• Mirrobox.com\n\n"
        "📋 **How to Download:**\n"
        "1. Copy Terabox share link\n"
        "2. Send the link to this bot\n"
        "3. Click 'Download' button\n"
        "4. Wait for upload to complete\n\n"
        "⚠️ **Limitations:**\n"
        f"• Max file size: {format_bytes(Config.MAX_FILE_SIZE)}\n"
        "• Download may take time for large files\n\n"
        "🆘 **Need Help?**\n"
        "Contact: @YourSupportBot"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏠 Home", callback_data="start")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")]
    ]
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard),
        message_effect_id=5104841245755180586
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    text = update.message.text
    
    # Check if message contains Terabox link
    terabox_domains = ['terabox.com', '1024terabox.com', '4funbox.com', 'mirrobox.com']
    
    if any(domain in text.lower() for domain in terabox_domains):
        await process_terabox_link(update, context, text)
    else:
        await update.message.reply_text(
            "❌ Please send a valid Terabox link!\n\n"
            "🔗 **Supported domains:**\n"
            "• terabox.com\n"
            "• 1024terabox.com\n"
            "• 4funbox.com\n"
            "• mirrobox.com",
            parse_mode='Markdown',
            message_effect_id=5104841245755180586
        )

async def process_terabox_link(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Process Terabox link and show file info"""
    processing_msg = await update.message.reply_text(
        "🔄 **Processing your link...**\n\n"
        "⏳ Please wait while I fetch file information...",
        parse_mode='Markdown',
        message_effect_id=5104841245755180586
    )
    
    # Fetch file information
    file_info = await fetch_terabox_info(url)
    
    if "error" in file_info:
        await processing_msg.edit_text(
            f"❌ **Error:** {file_info['error']}\n\n"
            "Please check your link and try again.",
            parse_mode='Markdown'
        )
        return
    
    # Store file info in context
    context.user_data['file_info'] = file_info
    context.user_data['original_url'] = url
    
    # Create file info message
    file_text = (
        f"📁 **File Information**\n\n"
        f"🏷️ **Name:** `{file_info['file_name']}`\n"
        f"📦 **Size:** {file_info['file_size']}\n"
        f"💾 **Bytes:** {format_bytes(file_info['size_bytes'])}\n\n"
        f"✅ **Ready to download!**"
    )
    
    # Check file size limit
    if file_info['size_bytes'] > Config.MAX_FILE_SIZE:
        file_text += f"\n\n⚠️ **Warning:** File size exceeds {format_bytes(Config.MAX_FILE_SIZE)} limit!"
        keyboard = [[InlineKeyboardButton("❌ File too large", callback_data="file_too_large")]]
    else:
        keyboard = [
            [InlineKeyboardButton("⬇️ Download", callback_data="download_file")],
            [InlineKeyboardButton("🖼️ Thumbnail", callback_data="show_thumbnail")],
            [InlineKeyboardButton("📊 Stats", callback_data="stats")]
        ]
    
    await processing_msg.edit_text(
        file_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "download_file":
        await download_callback(update, context)
    elif query.data == "show_thumbnail":
        await thumbnail_callback(update, context)
    elif query.data == "stats":
        await stats_callback(update, context)
    elif query.data == "help":
        await help_callback(update, context)
    elif query.data == "start":
        await start_callback(update, context)

async def download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle download button callback"""
    user_id = update.effective_user.id
    
    if user_id in active_downloads:
        await update.callback_query.edit_message_text(
            "⚠️ **You already have an active download!**\n\n"
            "Please wait for it to complete before starting a new one.",
            parse_mode='Markdown'
        )
        return
    
    file_info = context.user_data.get('file_info')
    if not file_info:
        await update.callback_query.edit_message_text(
            "❌ **Session expired!**\n\n"
            "Please send the Terabox link again.",
            parse_mode='Markdown'
        )
        return
    
    # Start download
    await update.callback_query.edit_message_text(
        "🚀 **Starting download...**\n\n"
        f"📁 **File:** `{file_info['file_name']}`\n"
        f"📦 **Size:** {file_info['file_size']}\n\n"
        "⏳ Please wait...",
        parse_mode='Markdown'
    )
    
    # Download file
    file_path = await download_file(
        file_info['proxy_url'],
        file_info['file_name'],
        file_info['size_bytes'],
        update,
        context
    )
    
    if file_path:
        # Upload to Telegram
        await upload_to_telegram(update, context, file_path, file_info)
        
        # Update statistics
        await update_user_stats(user_id, file_info['size_bytes'])
        await log_download(user_id, file_info['file_name'], file_info['size_bytes'], "completed")
        
        # Clean up
        try:
            os.remove(file_path)
        except:
            pass
        
        if user_id in active_downloads:
            del active_downloads[user_id]
    else:
        await update.callback_query.edit_message_text(
            "❌ **Download failed!**\n\n"
            "Please try again later or contact support.",
            parse_mode='Markdown'
        )
        
        await log_download(user_id, file_info['file_name'], file_info['size_bytes'], "failed")
        
        if user_id in active_downloads:
            del active_downloads[user_id]

async def upload_to_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, file_info: Dict):
    """Upload file to Telegram"""
    user_id = update.effective_user.id
    
    try:
        # Update status
        await update.effective_message.edit_text(
            f"📤 **Uploading to Telegram...**\n\n"
            f"📁 **File:** `{file_info['file_name']}`\n"
            f"📦 **Size:** {file_info['file_size']}\n\n"
            "⏳ Please wait...",
            parse_mode='Markdown'
        )
        
        # Send document
        with open(file_path, 'rb') as document:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=document,
                filename=file_info['file_name'],
                caption=f"✅ **Download Complete!**\n\n📁 **File:** `{file_info['file_name']}`\n📦 **Size:** {file_info['file_size']}",
                parse_mode='Markdown',
                message_effect_id=5104841245755180586
            )
        
        # Success message
        await update.effective_message.edit_text(
            f"✅ **Upload Complete!**\n\n"
            f"📁 **File:** `{file_info['file_name']}`\n"
            f"📦 **Size:** {file_info['file_size']}\n\n"
            "🎉 **File sent successfully!**",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await update.effective_message.edit_text(
            "❌ **Upload failed!**\n\n"
            "The file was downloaded but couldn't be uploaded to Telegram.\n"
            "This might be due to file size limits or network issues.",
            parse_mode='Markdown'
        )

async def thumbnail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle thumbnail button callback"""
    file_info = context.user_data.get('file_info')
    if not file_info or 'thumbnail' not in file_info:
        await update.callback_query.edit_message_text(
            "❌ **No thumbnail available for this file.**",
            parse_mode='Markdown'
        )
        return
    
    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=file_info['thumbnail'],
            caption=f"🖼️ **Thumbnail**\n\n📁 **File:** `{file_info['file_name']}`",
            parse_mode='Markdown',
            message_effect_id=5104841245755180586
        )
    except Exception as e:
        logger.error(f"Thumbnail error: {e}")
        await update.callback_query.answer("❌ Failed to load thumbnail!")

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stats button callback"""
    await stats_command(update, context)

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help button callback"""
    await help_command(update, context)

async def start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle start button callback"""
    await start_command(update, context)

# Main function
async def main():
    """Main function to run the bot"""
    # Initialize database
    await init_db()
    
    # Create application
    application = Application.builder().token(Config.BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Bot started successfully!")
    
    # Run the bot
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    asyncio.run(main())
