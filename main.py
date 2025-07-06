import asyncio
import os
import time
import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatAction
import humanize
import yt_dlp
import aiohttp
import subprocess
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot Configuration
API_ID = "24720215"
API_HASH = "c0d3395590fecba19985f95d6300785e"
BOT_TOKEN = "8037389280:AAG5WfzHcheszs-RHWL8WXszWPkrWjyulp8"
MONGO_URI = "mongodb+srv://Nischay999:Nischay999@cluster0.5kufo.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
FORCE_SUB_CHANNEL = "@NY_BOTS"
LOG_CHANNEL = -1002732334186  # Your log channel ID
OWNER_ID = 7910994767  # Your user ID
DOWNLOAD_PATH = "downloads/"

# Initialize bot
app = Client("terabox_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB setup
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client.terabox_bot
users_collection = db.users
stats_collection = db.stats

os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# Progress tracking
download_progress = {}

class ProgressHook:
    def __init__(self, user_id, message):
        self.user_id = user_id
        self.message = message
        self.last_update = 0
        
    def __call__(self, d):
        if d['status'] == 'downloading':
            current_time = time.time()
            if current_time - self.last_update > 2:  # Update every 2 seconds
                try:
                    downloaded = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
                    speed = d.get('speed', 0) or 0
                    eta = d.get('eta', 0) or 0
                    
                    if total > 0:
                        progress_bar = get_progress_bar(downloaded, total)
                        asyncio.create_task(self.message.edit_text(
                            f"📥 **Downloading:** `{d.get('filename', 'Unknown')}`\n\n"
                            f"{progress_bar}\n"
                            f"📊 **Downloaded:** `{humanize.naturalsize(downloaded)}` / `{humanize.naturalsize(total)}`\n"
                            f"⚡ **Speed:** `{humanize.naturalsize(speed)}/s`\n"
                            f"⏱️ **ETA:** `{eta}s`"
                        ))
                        self.last_update = current_time
                except:
                    pass

async def add_user(user_id, username):
    user_data = {
        "user_id": user_id,
        "username": username,
        "join_date": datetime.now(),
        "downloads": 0,
        "upload_type": "video"
    }
    await users_collection.update_one(
        {"user_id": user_id}, 
        {"$setOnInsert": user_data}, 
        upsert=True
    )

async def get_user_stats():
    total_users = await users_collection.count_documents({})
    total_downloads = await stats_collection.count_documents({})
    return total_users, total_downloads

async def update_download_stats(user_id, file_size):
    await users_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"downloads": 1}}
    )
    await stats_collection.insert_one({
        "user_id": user_id,
        "file_size": file_size,
        "download_date": datetime.now()
    })

async def get_terabox_info(url):
    api_url = f"https://noor-terabox-api.woodmirror.workers.dev/api?url={url}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as response:
            if response.status == 200:
                data = await response.json()
                if "error" not in data:
                    return data
                else:
                    return {"error": data["error"]}
            else:
                return {"error": "Failed to fetch file info"}

def get_progress_bar(current, total, length=20):
    percent = (current / total) * 100
    filled = int(length * current // total)
    bar = "█" * filled + "░" * (length - filled)
    return f"{bar} {percent:.1f}%"

async def download_with_ytdlp(url, output_path, progress_hook=None):
    """Download using yt-dlp with optimizations"""
    ydl_opts = {
        'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
        'format': 'best',
        'no_warnings': True,
        'extract_flat': False,
        'writethumbnail': False,
        'writeinfojson': False,
        'concurrent_fragment_downloads': 4,
        'http_chunk_size': 1024*1024,  # 1MB chunks
        'retries': 3,
        'fragment_retries': 3,
        'progress_hooks': [progress_hook] if progress_hook else [],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Get info first
            info = ydl.extract_info(url, download=False)
            filename = ydl.prepare_filename(info)
            
            # Download
            ydl.download([url])
            
            return filename, info
    except Exception as e:
        logger.error(f"yt-dlp error: {e}")
        return None, None

@app.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    await add_user(user_id, username)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ])
    
    await message.reply_text(
        "🚀 **Welcome to Terabox Download Bot!**\n\n"
        "✨ Send me a Terabox URL and I'll download it for you!\n\n"
        "🎯 **Features:**\n"
        "• Ultra-fast downloads with yt-dlp\n"
        "• Real-time progress tracking\n"
        "• Upload as video or document\n"
        "• Advanced download optimization\n\n"
        "📤 **Made by:** @NY_BOTS",
        reply_markup=keyboard,
        message_effect_id=5104841245755180586
    )

@app.on_message(filters.text & filters.private)
async def handle_url(client, message):
    url = message.text.strip()
    
    if not ("terabox" in url.lower() or "1024tera" in url.lower()):
        await message.reply_text("❌ Please send a valid Terabox URL!")
        return
    
    user_id = message.from_user.id
    await add_user(user_id, message.from_user.username)
    
    processing_msg = await message.reply_text(
        "🔍 **Processing your request...**\n\n"
        "⏳ Fetching file information...",
        message_effect_id=5104841245755180586
    )
    
    # Get file info from API
    file_info = await get_terabox_info(url)
    
    if "error" in file_info:
        await processing_msg.edit_text(f"❌ **Error:** {file_info['error']}")
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download", callback_data=f"download_{url}")],
        [InlineKeyboardButton("📊 File Info", callback_data=f"info_{url}")]
    ])
    
    await processing_msg.edit_text(
        f"📁 **File Information:**\n\n"
        f"📄 **Name:** `{file_info['file_name']}`\n"
        f"📊 **Size:** `{file_info['file_size']}`\n"
        f"🖼️ **Type:** `{file_info['file_name'].split('.')[-1].upper()}`\n\n"
        f"✅ **Ready to download with yt-dlp optimization!**",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex(r"^download_"))
async def download_callback(client, callback: CallbackQuery):
    url = callback.data.split("download_", 1)[1]
    user_id = callback.from_user.id
    
    file_info = await get_terabox_info(url)
    
    if "error" in file_info:
        await callback.answer(f"Error: {file_info['error']}", show_alert=True)
        return
    
    await callback.answer("🚀 Starting download with yt-dlp...")
    
    progress_msg = await callback.message.edit_text(
        "📥 **Downloading with yt-dlp...**\n\n"
        "🔄 Initializing download engine...\n"
        "⏳ Please wait..."
    )
    
    # Create progress hook
    progress_hook = ProgressHook(user_id, progress_msg)
    
    # Download with yt-dlp
    filepath, info = await asyncio.get_event_loop().run_in_executor(
        None, 
        lambda: download_with_ytdlp(file_info['proxy_url'], DOWNLOAD_PATH, progress_hook)
    )
    
    if not filepath or not os.path.exists(filepath):
        await progress_msg.edit_text("❌ **Download failed!** Trying alternative method...")
        
        # Fallback to direct download
        try:
            import aiohttp
            import aiofiles
            
            async with aiohttp.ClientSession() as session:
                async with session.get(file_info['proxy_url']) as response:
                    if response.status == 200:
                        filepath = os.path.join(DOWNLOAD_PATH, file_info['file_name'])
                        async with aiofiles.open(filepath, 'wb') as f:
                            async for chunk in response.content.iter_chunked(1024*1024):
                                await f.write(chunk)
                    else:
                        await progress_msg.edit_text("❌ **Download failed completely!**")
                        return
        except Exception as e:
            await progress_msg.edit_text(f"❌ **Download failed:** {str(e)}")
            return
    
    # Upload file
    await progress_msg.edit_text(
        "📤 **Uploading...**\n\n"
        "⏳ Preparing upload..."
    )
    
    await client.send_chat_action(callback.message.chat.id, ChatAction.UPLOAD_DOCUMENT)
    
    user_data = await users_collection.find_one({"user_id": user_id})
    upload_type = user_data.get("upload_type", "video") if user_data else "video"
    
    file_size = os.path.getsize(filepath)
    
    async def upload_progress(current, total):
        progress_bar = get_progress_bar(current, total)
        await progress_msg.edit_text(
            f"📤 **Uploading:** `{os.path.basename(filepath)}`\n\n"
            f"{progress_bar}\n"
            f"📊 **Uploaded:** `{humanize.naturalsize(current)}` / `{humanize.naturalsize(total)}`"
        )
    
    try:
        caption = f"📁 **File:** `{os.path.basename(filepath)}`\n📊 **Size:** `{humanize.naturalsize(file_size)}`\n\n🚀 **Downloaded with yt-dlp optimization**\n📤 **By:** @NY_BOTS"
        
        if upload_type == "video" and filepath.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
            await callback.message.reply_video(
                filepath,
                caption=caption,
                progress=upload_progress,
                supports_streaming=True
            )
        else:
            await callback.message.reply_document(
                filepath,
                caption=caption,
                progress=upload_progress
            )
        
        await progress_msg.delete()
        
        # Update stats
        await update_download_stats(user_id, file_size)
        
        # Log to channel
        try:
            await client.send_message(
                LOG_CHANNEL,
                f"📥 **New Download**\n\n"
                f"👤 **User:** {callback.from_user.mention}\n"
                f"🆔 **ID:** `{user_id}`\n"
                f"📁 **File:** `{os.path.basename(filepath)}`\n"
                f"📊 **Size:** `{humanize.naturalsize(file_size)}`\n"
                f"🚀 **Method:** yt-dlp + API\n"
                f"🕐 **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
        except:
            pass
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await progress_msg.edit_text(f"❌ **Upload failed:** {str(e)}")
    
    finally:
        # Clean up
        try:
            os.remove(filepath)
        except:
            pass

@app.on_callback_query(filters.regex(r"^info_"))
async def info_callback(client, callback: CallbackQuery):
    url = callback.data.split("info_", 1)[1]
    
    file_info = await get_terabox_info(url)
    
    if "error" in file_info:
        await callback.answer(f"Error: {file_info['error']}", show_alert=True)
        return
    
    info_text = (
        f"📁 **Detailed File Information:**\n\n"
        f"📄 **Name:** `{file_info['file_name']}`\n"
        f"📊 **Size:** `{file_info['file_size']}`\n"
        f"📦 **Size (bytes):** `{file_info['size_bytes']:,}`\n"
        f"🚀 **Download Method:** yt-dlp + API\n"
        f"⚡ **Optimization:** Multi-threaded\n"
        f"🔗 **API Response:** Valid\n\n"
        f"✅ **Ready for ultra-fast download!**"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download", callback_data=f"download_{url}")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])
    
    await callback.message.edit_text(info_text, reply_markup=keyboard)

@app.on_callback_query(filters.regex("^stats$"))
async def stats_callback(client, callback: CallbackQuery):
    total_users, total_downloads = await get_user_stats()
    
    await callback.message.edit_text(
        f"📊 **Bot Statistics:**\n\n"
        f"👥 **Total Users:** `{total_users:,}`\n"
        f"📥 **Total Downloads:** `{total_downloads:,}`\n"
        f"🚀 **Download Engine:** yt-dlp\n"
        f"⚡ **Optimization:** Multi-threaded\n"
        f"🤖 **Status:** `Online & Fast`\n\n"
        f"📤 **Made by:** @NY_BOTS",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])
    )

@app.on_callback_query(filters.regex("^settings$"))
async def settings_callback(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    user_data = await users_collection.find_one({"user_id": user_id})
    upload_type = user_data.get("upload_type", "video") if user_data else "video"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📹 Video {'✅' if upload_type == 'video' else ''}", callback_data="set_video")],
        [InlineKeyboardButton(f"📄 Document {'✅' if upload_type == 'document' else ''}", callback_data="set_document")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        f"⚙️ **Settings:**\n\n"
        f"📤 **Upload Type:** `{upload_type.title()}`\n"
        f"🚀 **Download Engine:** yt-dlp\n"
        f"⚡ **Optimization:** Enabled\n\n"
        f"Choose how you want files to be uploaded:",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex(r"^set_(video|document)$"))
async def set_upload_type(client, callback: CallbackQuery):
    upload_type = callback.data.split("set_")[1]
    user_id = callback.from_user.id
    
    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"upload_type": upload_type}},
        upsert=True
    )
    
    await callback.answer(f"✅ Upload type set to {upload_type.title()}")
    await settings_callback(client, callback)

@app.on_callback_query(filters.regex("^help$"))
async def help_callback(client, callback: CallbackQuery):
    await callback.message.edit_text(
        f"ℹ️ **Help & Instructions:**\n\n"
        f"🔗 **How to use:**\n"
        f"1. Send me a Terabox URL\n"
        f"2. Wait for file information\n"
        f"3. Click 'Download' button\n"
        f"4. Enjoy ultra-fast download!\n\n"
        f"🚀 **Features:**\n"
        f"• yt-dlp powered downloads\n"
        f"• Multi-threaded optimization\n"
        f"• Real-time progress tracking\n"
        f"• Automatic fallback methods\n"
        f"• Smart upload type detection\n\n"
        f"⚙️ **Settings:**\n"
        f"• Video/Document upload mode\n"
        f"• Download statistics\n\n"
        f"📤 **Made by:** @NY_BOTS",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])
    )

@app.on_callback_query(filters.regex("^back$"))
async def back_callback(client, callback: CallbackQuery):
    await start_command(client, callback.message)

if __name__ == "__main__":
    print("🚀 Starting Terabox Download Bot with yt-dlp...")
    app.run()
