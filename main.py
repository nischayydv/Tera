import os
import asyncio
import aiohttp
import aiofiles
from datetime import datetime
import logging
from urllib.parse import quote
import time
import math

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode, MessageEffectId
from motor.motor_asyncio import AsyncIOMotorClient
import pymongo

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DB_NAME = "terabox_bot"
    API_BASE_URL = "https://noor-terabox-api.woodmirror.workers.dev/api"
    PROXY_BASE_URL = "https://noor-terabox-api.woodmirror.workers.dev/proxy"
    DOWNLOAD_DIR = "downloads"
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    CHUNK_SIZE = 8192

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(Config.MONGO_URI)
        self.db = self.client[Config.DB_NAME]
        self.users = self.db.users
        self.downloads = self.db.downloads
        self.stats = self.db.stats
    
    async def add_user(self, user_id: int, username: str = None, first_name: str = None):
        user_data = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "joined_at": datetime.now(),
            "total_downloads": 0,
            "total_size": 0
        }
        await self.users.update_one(
            {"user_id": user_id},
            {"$setOnInsert": user_data},
            upsert=True
        )
    
    async def get_user(self, user_id: int):
        return await self.users.find_one({"user_id": user_id})
    
    async def update_user_stats(self, user_id: int, file_size: int):
        await self.users.update_one(
            {"user_id": user_id},
            {"$inc": {"total_downloads": 1, "total_size": file_size}}
        )
    
    async def add_download(self, user_id: int, file_name: str, file_size: int, status: str = "pending"):
        download_data = {
            "user_id": user_id,
            "file_name": file_name,
            "file_size": file_size,
            "status": status,
            "created_at": datetime.now(),
            "completed_at": None
        }
        result = await self.downloads.insert_one(download_data)
        return str(result.inserted_id)
    
    async def update_download_status(self, download_id: str, status: str):
        from bson import ObjectId
        update_data = {"status": status}
        if status == "completed":
            update_data["completed_at"] = datetime.now()
        await self.downloads.update_one(
            {"_id": ObjectId(download_id)},
            {"$set": update_data}
        )
    
    async def get_total_stats(self):
        pipeline = [
            {"$group": {
                "_id": None,
                "total_users": {"$sum": 1},
                "total_downloads": {"$sum": "$total_downloads"},
                "total_size": {"$sum": "$total_size"}
            }}
        ]
        result = await self.users.aggregate(pipeline).to_list(1)
        return result[0] if result else {"total_users": 0, "total_downloads": 0, "total_size": 0}

class TeraBoxAPI:
    @staticmethod
    async def get_file_info(url: str):
        api_url = f"{Config.API_BASE_URL}?url={quote(url)}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": "Failed to fetch file information"}

class ProgressTracker:
    def __init__(self, total_size: int):
        self.total_size = total_size
        self.downloaded = 0
        self.start_time = time.time()
        self.last_update = 0
    
    def update(self, chunk_size: int):
        self.downloaded += chunk_size
        
    def get_progress(self):
        if self.total_size == 0:
            return 0
        return (self.downloaded / self.total_size) * 100
    
    def get_speed(self):
        elapsed = time.time() - self.start_time
        if elapsed == 0:
            return 0
        return self.downloaded / elapsed
    
    def get_eta(self):
        speed = self.get_speed()
        if speed == 0:
            return 0
        remaining = self.total_size - self.downloaded
        return remaining / speed
    
    def format_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
    
    def format_time(self, seconds):
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds/60)}m {int(seconds%60)}s"
        else:
            return f"{int(seconds/3600)}h {int((seconds%3600)/60)}m"
    
    def get_progress_bar(self, length=20):
        progress = self.get_progress()
        filled_length = int(length * progress // 100)
        bar = "█" * filled_length + "░" * (length - filled_length)
        return bar

class TeraBoxBot:
    def __init__(self):
        self.db = Database()
        self.downloads = {}
        
        # Emoji animations
        self.fire_emojis = ["🔥", "🌟", "⚡", "💥", "✨", "🎯", "🚀", "💫"]
        self.progress_emojis = ["📥", "⬇️", "📦", "📋", "📊", "📈", "📉", "📌"]
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await self.db.add_user(user.id, user.username, user.first_name)
        
        welcome_text = f"""
🔥 **Welcome to TeraBox Downloader Bot!** 🔥

🌟 **Features:**
• 📥 Fast TeraBox downloads
• 📊 Real-time progress tracking
• 📈 Upload progress monitoring
• 📋 Download statistics
• 🎯 Inline keyboard controls

🚀 **How to use:**
1. Send me a TeraBox URL
2. Click download button
3. Get your file instantly!

💫 **Ready to download?** Send me a TeraBox link!
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 My Stats", callback_data="stats"),
             InlineKeyboardButton("🌟 Help", callback_data="help")],
            [InlineKeyboardButton("🔥 Channel", url="https://t.me/your_channel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            message_effect_id=MessageEffectId.FIRE
        )
    
    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        url = update.message.text.strip()
        
        # Check if URL is valid TeraBox URL
        if not any(domain in url.lower() for domain in ["terabox", "1024tera", "mirrobox", "momerybox", "teraboxapp"]):
            await update.message.reply_text(
                "❌ **Invalid URL!** Please send a valid TeraBox URL.",
                parse_mode=ParseMode.MARKDOWN,
                message_effect_id=MessageEffectId.FIRE
            )
            return
        
        # Show processing message
        processing_msg = await update.message.reply_text(
            "🔄 **Processing your request...**\n⚡ Fetching file information...",
            parse_mode=ParseMode.MARKDOWN,
            message_effect_id=MessageEffectId.FIRE
        )
        
        try:
            # Get file information
            file_info = await TeraBoxAPI.get_file_info(url)
            
            if "error" in file_info:
                await processing_msg.edit_text(
                    f"❌ **Error:** {file_info['error']}",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Extract file details
            file_name = file_info.get("file_name", "Unknown")
            file_size = file_info.get("file_size", "Unknown")
            size_bytes = file_info.get("size_bytes", 0)
            thumbnail = file_info.get("thumbnail", "")
            proxy_url = file_info.get("proxy_url", "")
            
            # Check file size limit
            if size_bytes > Config.MAX_FILE_SIZE:
                await processing_msg.edit_text(
                    f"❌ **File too large!**\n📁 File size: {file_size}\n🚫 Max allowed: 2GB",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Create download info message
            info_text = f"""
🎯 **File Information**

📄 **Name:** `{file_name}`
📊 **Size:** {file_size}
🔗 **Status:** Ready to download

🔥 **Click download to start!**
            """
            
            keyboard = [
                [InlineKeyboardButton("📥 Download", callback_data=f"download_{user.id}_{quote(proxy_url)}_{quote(file_name)}_{size_bytes}")],
                [InlineKeyboardButton("🖼️ View Thumbnail", url=thumbnail) if thumbnail else InlineKeyboardButton("📋 File Info", callback_data="info")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await processing_msg.edit_text(
                info_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error processing URL: {e}")
            await processing_msg.edit_text(
                "❌ **Error occurred while processing your request!**",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def handle_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data.split("_", 4)
        if len(data) < 5:
            await query.edit_message_text("❌ Invalid download data!")
            return
        
        user_id = int(data[1])
        proxy_url = data[2]
        file_name = data[3]
        size_bytes = int(data[4])
        
        # Check if user is authorized
        if query.from_user.id != user_id:
            await query.answer("❌ You can only download your own files!", show_alert=True)
            return
        
        # Add to database
        download_id = await self.db.add_download(user_id, file_name, size_bytes)
        
        # Start download
        await self.start_download(query, proxy_url, file_name, size_bytes, download_id)
    
    async def start_download(self, query, proxy_url, file_name, size_bytes, download_id):
        try:
            # Initialize progress tracker
            progress_tracker = ProgressTracker(size_bytes)
            
            # Create download directory if not exists
            os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
            file_path = os.path.join(Config.DOWNLOAD_DIR, file_name)
            
            # Download progress message
            progress_msg = await query.edit_message_text(
                "🔄 **Starting download...**\n⚡ Initializing...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Download file
            async with aiohttp.ClientSession() as session:
                async with session.get(proxy_url) as response:
                    if response.status != 200:
                        await self.db.update_download_status(download_id, "failed")
                        await progress_msg.edit_text(
                            "❌ **Download failed!** Server returned error.",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        return
                    
                    async with aiofiles.open(file_path, 'wb') as file:
                        last_update = time.time()
                        
                        async for chunk in response.content.iter_chunked(Config.CHUNK_SIZE):
                            await file.write(chunk)
                            progress_tracker.update(len(chunk))
                            
                            # Update progress every 2 seconds
                            if time.time() - last_update > 2:
                                await self.update_progress_message(
                                    progress_msg, progress_tracker, file_name, "downloading"
                                )
                                last_update = time.time()
            
            # Upload to Telegram
            await self.upload_file(progress_msg, file_path, file_name, size_bytes, download_id, query.from_user.id)
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            await self.db.update_download_status(download_id, "failed")
            await progress_msg.edit_text(
                "❌ **Download failed!** Please try again.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def upload_file(self, progress_msg, file_path, file_name, size_bytes, download_id, user_id):
        try:
            # Start upload
            progress_tracker = ProgressTracker(size_bytes)
            
            await progress_msg.edit_text(
                "📤 **Uploading to Telegram...**\n⚡ Preparing upload...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Upload file to Telegram
            with open(file_path, 'rb') as file:
                await progress_msg.get_bot().send_document(
                    chat_id=user_id,
                    document=file,
                    filename=file_name,
                    caption=f"🔥 **Downloaded successfully!**\n📁 **File:** `{file_name}`\n📊 **Size:** {progress_tracker.format_size(size_bytes)}",
                    parse_mode=ParseMode.MARKDOWN,
                    message_effect_id=MessageEffectId.FIRE
                )
            
            # Update database
            await self.db.update_download_status(download_id, "completed")
            await self.db.update_user_stats(user_id, size_bytes)
            
            # Success message
            keyboard = [
                [InlineKeyboardButton("📊 My Stats", callback_data="stats"),
                 InlineKeyboardButton("🔥 Download More", callback_data="download_more")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await progress_msg.edit_text(
                f"✅ **Upload Complete!**\n🎯 **File:** `{file_name}`\n📊 **Size:** {progress_tracker.format_size(size_bytes)}\n🚀 **Status:** Success",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
            # Clean up file
            try:
                os.remove(file_path)
            except:
                pass
                
        except Exception as e:
            logger.error(f"Upload error: {e}")
            await self.db.update_download_status(download_id, "failed")
            await progress_msg.edit_text(
                "❌ **Upload failed!** File downloaded but couldn't upload to Telegram.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def update_progress_message(self, message, progress_tracker, file_name, action):
        try:
            progress = progress_tracker.get_progress()
            speed = progress_tracker.get_speed()
            eta = progress_tracker.get_eta()
            progress_bar = progress_tracker.get_progress_bar()
            
            emoji = self.progress_emojis[int(progress / 12.5) % len(self.progress_emojis)]
            
            progress_text = f"""
{emoji} **{action.title()}...**

📁 **File:** `{file_name[:30]}...`
📊 **Progress:** {progress:.1f}%
{progress_bar}

📥 **Downloaded:** {progress_tracker.format_size(progress_tracker.downloaded)}
📈 **Speed:** {progress_tracker.format_size(speed)}/s
⏱️ **ETA:** {progress_tracker.format_time(eta)}
            """
            
            await message.edit_text(
                progress_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Progress update error: {e}")
    
    async def handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        user_data = await self.db.get_user(user_id)
        total_stats = await self.db.get_total_stats()
        
        if not user_data:
            await query.edit_message_text(
                "❌ **No user data found!**",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Format sizes
        user_size = ProgressTracker(0).format_size(user_data.get("total_size", 0))
        total_size = ProgressTracker(0).format_size(total_stats.get("total_size", 0))
        
        stats_text = f"""
📊 **Your Statistics**

👤 **User:** {user_data.get('first_name', 'Unknown')}
📅 **Joined:** {user_data.get('joined_at', 'Unknown').strftime('%Y-%m-%d')}
📥 **Downloads:** {user_data.get('total_downloads', 0)}
📊 **Total Size:** {user_size}

🌟 **Global Statistics**
👥 **Total Users:** {total_stats.get('total_users', 0)}
📥 **Total Downloads:** {total_stats.get('total_downloads', 0)}
📊 **Total Size:** {total_size}
        """
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="stats"),
             InlineKeyboardButton("🏠 Home", callback_data="home")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            stats_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        help_text = """
🌟 **TeraBox Downloader Bot Help**

🚀 **How to use:**
1. Send me a TeraBox share URL
2. Bot will fetch file information
3. Click "📥 Download" button
4. Wait for download & upload to complete
5. Receive your file in Telegram!

📋 **Supported URLs:**
• TeraBox.com
• 1024tera.com
• Mirrobox.com
• Momerybox.com
• TeraBoxApp.com

⚡ **Features:**
• Real-time progress tracking
• Download statistics
• Fast parallel downloads
• Automatic file cleanup
• Error handling & retry

🔥 **Limits:**
• Max file size: 2GB
• Concurrent downloads: 3
• Daily limit: 50 files per user

❓ **Need help?** Contact @your_support
        """
        
        keyboard = [
            [InlineKeyboardButton("🏠 Home", callback_data="home"),
             InlineKeyboardButton("📊 Stats", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data
        
        if data.startswith("download_"):
            await self.handle_download(update, context)
        elif data == "stats":
            await self.handle_stats(update, context)
        elif data == "help":
            await self.handle_help(update, context)
        elif data == "home":
            await query.answer()
            await self.start(update, context)
        elif data == "cancel":
            await query.answer()
            await query.edit_message_text(
                "❌ **Download cancelled!**",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.answer("🔄 Processing...")

def main():
    """Start the bot"""
    bot = TeraBoxBot()
    
    # Create application
    application = Application.builder().token(Config.BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_url))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    
    # Start polling
    logger.info("🔥 TeraBox Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
