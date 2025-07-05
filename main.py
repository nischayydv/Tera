import asyncio
import os
import time
import aiohttp
import aiofiles
from datetime import datetime
from urllib.parse import quote
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode, MessageEffectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

# Configuration
BOT_TOKEN = "YOUR_BOT_TOKEN"
MONGODB_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "terabox_bot"
PORT = 8080

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB setup
client = AsyncIOMotorClient(MONGODB_URI)
db = client[DATABASE_NAME]
users_collection = db.users
downloads_collection = db.downloads

class TeraboxBot:
    def __init__(self):
        self.app = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
        self.downloading_users = set()
        
    def setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await self.save_user(user)
        
        start_text = f"""🔥 **Welcome to Terabox Download Bot!** 🔥

Hey {user.first_name}! 👋

🚀 **What I can do:**
• Download files from Terabox links
• Show download progress in real-time
• Track your download history

📋 **How to use:**
1. Send me a Terabox link
2. I'll fetch the file information
3. Click download to start
4. Watch the magic happen! ✨

🎯 **Ready to download?** Send me a Terabox link now!"""
        
        keyboard = [[InlineKeyboardButton("📥 Start Downloading", callback_data="start_download")],
                   [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
                   [InlineKeyboardButton("❓ Help", callback_data="help")]]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(start_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup, message_effect_id=MessageEffectId.FIRE)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """🆘 **Help & Commands**

**Available Commands:**
• `/start` - Start the bot
• `/help` - Show this help message
• `/stats` - View your download statistics

**How to Download:**
1. 📎 Send any Terabox link
2. 📋 Bot will analyze the file
3. 🔽 Click "Download" button
4. 📊 Watch progress in real-time
5. 📁 Receive your file!

**Supported Links:**
• terabox.com • 1024terabox.com • terabox.app • terasharelink.com"""
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup, message_effect_id=MessageEffectId.HEART)

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_stats = await self.get_user_stats(user_id)
        
        stats_text = f"""📊 **Your Download Statistics**

👤 **User:** {update.effective_user.first_name}
📥 **Downloads:** {user_stats['total_downloads']}
💾 **Total Size:** {self.format_bytes(user_stats['total_size'])}
📅 **Join Date:** {user_stats['join_date']}
🏆 **Your Rank:** #{user_stats['rank']}
⭐ **Status:** {user_stats['status']}"""
        
        keyboard = [[InlineKeyboardButton("📋 Download History", callback_data="download_history")],
                   [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup, message_effect_id=MessageEffectId.LIKE)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        
        if self.is_terabox_link(text):
            await self.process_terabox_link(update, context, text)
        else:
            await update.message.reply_text("❌ **Invalid Link!**\n\nPlease send a valid Terabox link.", parse_mode=ParseMode.MARKDOWN, message_effect_id=MessageEffectId.EXPLODING_HEAD)

    async def process_terabox_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        processing_msg = await update.message.reply_text("🔄 **Processing your link...**\n⏳ Please wait while I analyze the file...", parse_mode=ParseMode.MARKDOWN, message_effect_id=MessageEffectId.EXPLODING_HEAD)
        
        for i in range(3):
            await asyncio.sleep(1)
            dots = "." * (i + 1)
            await processing_msg.edit_text(f"🔄 **Processing your link{dots}**\n⏳ Please wait while I analyze the file{dots}", parse_mode=ParseMode.MARKDOWN)
        
        try:
            file_info = await self.get_file_info(url)
            if file_info:
                await self.show_file_info(update, context, file_info, url, processing_msg)
            else:
                await processing_msg.edit_text("❌ **Error!**\nUnable to fetch file information.\nPlease check the link and try again.", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error processing link: {str(e)}")
            await processing_msg.edit_text("❌ **Error!**\nSomething went wrong. Please try again later.", parse_mode=ParseMode.MARKDOWN)

    async def get_file_info(self, url: str):
        api_url = f"https://noor-terabox-api.woodmirror.workers.dev/api?url={quote(url)}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    data = await response.json()
                    if "error" in data:
                        logger.error(f"API Error: {data['error']}")
                        return None
                    return data
        except Exception as e:
            logger.error(f"Error fetching file info: {str(e)}")
            return None

    async def show_file_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE, file_info: dict, original_url: str, processing_msg):
        file_name = file_info.get('file_name', 'Unknown')
        file_size = file_info.get('file_size', 'Unknown')
        size_bytes = file_info.get('size_bytes', 0)
        
        info_text = f"""📁 **File Information**

📋 **Name:** `{file_name}`
📊 **Size:** {file_size} ({self.format_bytes(size_bytes)})
🔗 **Source:** Terabox

✅ **Ready to download!**
Click the button below to start downloading."""
        
        context.user_data['file_info'] = file_info
        context.user_data['original_url'] = original_url
        
        keyboard = [[InlineKeyboardButton("📥 Download Now", callback_data="download_file")],
                   [InlineKeyboardButton("🔍 File Details", callback_data="file_details")],
                   [InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await processing_msg.edit_text(info_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        callbacks = {
            "download_file": self.start_download,
            "file_details": self.show_file_details,
            "cancel_download": self.cancel_download,
            "my_stats": self.show_my_stats,
            "download_history": self.show_download_history,
            "back_to_main": self.back_to_main,
            "help": self.show_help,
            "start_download": self.prompt_for_link
        }
        
        if query.data in callbacks:
            await callbacks[query.data](update, context)

    async def start_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id in self.downloading_users:
            await update.callback_query.edit_message_text("⚠️ **Already Downloading!**\nYou already have an active download.\nPlease wait for it to complete.", parse_mode=ParseMode.MARKDOWN)
            return
        
        file_info = context.user_data.get('file_info')
        if not file_info:
            await update.callback_query.edit_message_text("❌ **Error!**\nFile information not found. Please try again.", parse_mode=ParseMode.MARKDOWN)
            return
        
        self.downloading_users.add(user_id)
        await update.callback_query.edit_message_text(f"🚀 **Download Starting...**\n📁 **File:** {file_info['file_name']}\n📊 **Size:** {file_info['file_size']}\n\n⏳ Initializing download...", parse_mode=ParseMode.MARKDOWN)
        asyncio.create_task(self.download_file(update, context, file_info))

    async def download_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE, file_info: dict):
        user_id = update.effective_user.id
        
        try:
            download_url = file_info['proxy_url']
            file_name = file_info['file_name']
            size_bytes = file_info['size_bytes']
            
            download_dir = f"downloads/{user_id}"
            os.makedirs(download_dir, exist_ok=True)
            file_path = os.path.join(download_dir, file_name)
            
            start_time = time.time()
            await self.download_with_progress(update, download_url, file_path, file_name, size_bytes, start_time)
            await self.send_file_to_user(update, context, file_path, file_info)
            await self.update_download_stats(user_id, file_info)
            
            if os.path.exists(file_path):
                os.remove(file_path)
                
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            await update.callback_query.edit_message_text(f"❌ **Download Failed!**\nError: {str(e)}\n\nPlease try again later.", parse_mode=ParseMode.MARKDOWN)
        finally:
            self.downloading_users.discard(user_id)

    async def download_with_progress(self, update: Update, url: str, file_path: str, file_name: str, total_size: int, start_time: float):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    downloaded = 0
                    last_update = 0
                    
                    async with aiofiles.open(file_path, 'wb') as file:
                        async for chunk in response.content.iter_chunked(8192):
                            await file.write(chunk)
                            downloaded += len(chunk)
                            
                            current_time = time.time()
                            if downloaded - last_update >= 1048576 or current_time - start_time >= 5:
                                last_update = downloaded
                                await self.update_download_progress(update, downloaded, total_size, file_name, start_time)
                                await asyncio.sleep(0.1)
                else:
                    raise Exception(f"HTTP {response.status}: Failed to download file")

    async def update_download_progress(self, update: Update, downloaded: int, total_size: int, file_name: str, start_time: float):
        try:
            progress = (downloaded / total_size) * 100
            speed = downloaded / (time.time() - start_time)
            eta = (total_size - downloaded) / speed if speed > 0 else 0
            progress_bar = self.create_progress_bar(progress)
            
            progress_text = f"""📥 **Downloading...**

📁 **File:** {file_name}
📊 **Progress:** {progress:.1f}% ({self.format_bytes(downloaded)}/{self.format_bytes(total_size)})

{progress_bar}

⚡ **Speed:** {self.format_bytes(speed)}/s
⏰ **ETA:** {self.format_time(eta)}"""
            
            await update.callback_query.edit_message_text(progress_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Progress update error: {str(e)}")

    async def send_file_to_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, file_info: dict):
        user_id = update.effective_user.id
        file_name = file_info['file_name']
        
        try:
            await update.callback_query.edit_message_text(f"📤 **Uploading...**\n📁 **File:** {file_name}\n📊 **Size:** {file_info['file_size']}\n\n⏳ Uploading to Telegram...", parse_mode=ParseMode.MARKDOWN)
            
            with open(file_path, 'rb') as file:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=file,
                    filename=file_name,
                    caption=f"✅ **Download Complete!**\n\n📁 **File:** {file_name}\n📊 **Size:** {file_info['file_size']}\n⏰ **Downloaded:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n🎉 **Thank you for using Terabox Bot!**",
                    parse_mode=ParseMode.MARKDOWN,
                    message_effect_id=MessageEffectId.HEART
                )
            
            await update.callback_query.edit_message_text(f"✅ **Download Complete!**\n\n📁 **File:** {file_name}\n📊 **Size:** {file_info['file_size']}\n⏰ **Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n🎉 **File sent successfully!**", parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Upload error: {str(e)}")
            await update.callback_query.edit_message_text(f"❌ **Upload Failed!**\nThe file was downloaded but couldn't be uploaded.\nError: {str(e)}", parse_mode=ParseMode.MARKDOWN)

    # Helper methods
    def is_terabox_link(self, text: str) -> bool:
        terabox_domains = ['terabox.com', '1024terabox.com', 'terabox.app', 'terasharelink.com']
        return any(domain in text.lower() for domain in terabox_domains)

    def format_bytes(self, bytes_size: int) -> str:
        if bytes_size == 0:
            return "0 B"
        sizes = ['B', 'KB', 'MB', 'GB', 'TB']
        i = 0
        while bytes_size >= 1024 and i < len(sizes) - 1:
            bytes_size /= 1024
            i += 1
        return f"{bytes_size:.2f} {sizes[i]}"

    def format_time(self, seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"

    def create_progress_bar(self, progress: float) -> str:
        filled = int(progress // 10)
        empty = 10 - filled
        return f"{'█' * filled}{'░' * empty} {progress:.1f}%"

    # Database methods
    async def save_user(self, user):
        try:
            user_data = {
                '_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'join_date': datetime.now(),
                'last_activity': datetime.now(),
                'total_downloads': 0,
                'total_size': 0
            }
            await users_collection.insert_one(user_data)
        except DuplicateKeyError:
            await users_collection.update_one({'_id': user.id}, {'$set': {'last_activity': datetime.now()}})

    async def get_user_stats(self, user_id: int) -> dict:
        user = await users_collection.find_one({'_id': user_id})
        if not user:
            return {'total_downloads': 0, 'total_size': 0, 'join_date': 'Unknown', 'rank': 0, 'status': 'New User'}
        
        rank = await users_collection.count_documents({'total_downloads': {'$gt': user['total_downloads']}}) + 1
        status = 'New User'
        if user['total_downloads'] >= 100:
            status = 'Pro User'
        elif user['total_downloads'] >= 50:
            status = 'Premium User'
        elif user['total_downloads'] >= 10:
            status = 'Active User'
        
        return {
            'total_downloads': user['total_downloads'],
            'total_size': user['total_size'],
            'join_date': user['join_date'].strftime('%Y-%m-%d'),
            'rank': rank,
            'status': status
        }

    async def update_download_stats(self, user_id: int, file_info: dict):
        await users_collection.update_one(
            {'_id': user_id},
            {'$inc': {'total_downloads': 1, 'total_size': file_info.get('size_bytes', 0)}, '$set': {'last_activity': datetime.now()}}
        )
        
        download_record = {
            'user_id': user_id,
            'file_name': file_info.get('file_name'),
            'file_size': file_info.get('file_size'),
            'size_bytes': file_info.get('size_bytes', 0),
            'download_date': datetime.now(),
            'status': 'completed'
        }
        await downloads_collection.insert_one(download_record)

    # Additional callback methods
    async def show_file_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        file_info = context.user_data.get('file_info')
        if not file_info:
            await update.callback_query.edit_message_text("❌ File information not found.")
            return
        
        details_text = f"""📋 **Detailed File Information**

📁 **Name:** `{file_info.get('file_name', 'Unknown')}`
📊 **Size:** {file_info.get('file_size', 'Unknown')}
💾 **Bytes:** {file_info.get('size_bytes', 0):,}
🔗 **Type:** {file_info.get('file_name', '').split('.')[-1].upper() if '.' in file_info.get('file_name', '') else 'Unknown'}
🌐 **Source:** Terabox
📅 **Fetched:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        keyboard = [[InlineKeyboardButton("📥 Download", callback_data="download_file")],
                   [InlineKeyboardButton("🔙 Back", callback_data="back_to_file_info")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(details_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def cancel_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.edit_message_text("❌ **Download Cancelled**\n\nYour download has been cancelled.\nSend me another Terabox link to download!", parse_mode=ParseMode.MARKDOWN)

    async def show_my_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_stats = await self.get_user_stats(user_id)
        
        stats_text = f"""📊 **Your Statistics**

📥 **Downloads:** {user_stats['total_downloads']}
💾 **Total Size:** {self.format_bytes(user_stats['total_size'])}
🏆 **Rank:** #{user_stats['rank']}
⭐ **Status:** {user_stats['status']}
📅 **Member Since:** {user_stats['join_date']}"""
        
        keyboard = [[InlineKeyboardButton("📋 Download History", callback_data="download_history")],
                   [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def show_download_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        downloads = await downloads_collection.find({'user_id': user_id}).sort('download_date', -1).limit(5).to_list(5)
        
        if not downloads:
            history_text = "📋 **Download History**\n\nNo downloads yet. Start downloading some files!"
        else:
            history_text = "📋 **Recent Downloads**\n\n"
            for i, download in enumerate(downloads, 1):
                date = download['download_date'].strftime('%Y-%m-%d %H:%M')
                history_text += f"{i}. 📁 `{download['file_name']}`\n   📊 {download['file_size']} • {date}\n\n"
        
        keyboard = [[InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
                   [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(history_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def back_to_main(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        start_text = f"""🔥 **Welcome Back!** 🔥

Hey {user.first_name}! 👋

🎯 **Ready to download?** Send me a Terabox link!

📊 **Your Stats:**
• Downloads: {(await self.get_user_stats(user.id))['total_downloads']}
• Status: {(await self.get_user_stats(user.id))['status']}"""
        
        keyboard = [[InlineKeyboardButton("📥 Start Downloading", callback_data="start_download")],
                   [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(start_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """🆘 **Help & Commands**

**Available Commands:**
• `/start` - Start the bot
• `/help` - Show this help message
• `/stats` - View your download statistics

**How to Download:**
1. 📎 Send any Terabox link
2. 📋 Bot will analyze the file
3. 🔽 Click "Download" button
4. 📊 Watch progress in real-time
5. 📁 Receive your file!"""
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def prompt_for_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.edit_message_text("📎 **Send me a Terabox link to get started!**\n\nSupported formats:\n• terabox.com/s/xxxxx\n• 1024terabox.com/s/xxxxx\n• terabox.app/s/xxxxx", parse_mode=ParseMode.MARKDOWN)

    def run(self):
        logger.info("Starting Terabox Bot...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    bot = TeraboxBot()
    bot.run()
