import asyncio
import aiohttp
import aiofiles
import os
import time
import logging
import requests  # Added requests import
from datetime import datetime
from urllib.parse import urlparse
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatAction
import humanize
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot Configuration
API_ID = "24720215"
API_HASH = "c0d3395590fecba19985f95d6300785e"
BOT_TOKEN = "8037389280:AAG5WfzHcheszs-RHWL8WXszWPkrWjyulp8"
MONGO_URL = "mongodb+srv://Nischay999:Nischay999@cluster0.5kufo.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
FORCE_SUB_CHANNEL = "@NY_BOTS"
LOG_CHANNEL = -1002732334186  # Your log channel ID
OWNER_ID = 7910994767  # Your user ID
DOWNLOAD_PATH = "downloads/"
CHUNK_SIZE = 1024 * 1024

# Initialize bot
app = Client("terabox_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB setup
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client.terabox_bot
users_collection = db.users
stats_collection = db.stats

# Ensure download directory exists
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# Global variables for tracking
download_progress = {}
upload_progress = {}

async def add_user(user_id, username):
    """Add user to database"""
    user_data = {
        "user_id": user_id,
        "username": username,
        "join_date": datetime.now(),
        "downloads": 0,
        "total_downloaded": 0,
        "upload_type": "video"
    }
    await users_collection.update_one(
        {"user_id": user_id}, 
        {"$setOnInsert": user_data}, 
        upsert=True
    )

async def get_user_stats():
    """Get bot statistics"""
    total_users = await users_collection.count_documents({})
    total_downloads = await stats_collection.count_documents({})
    pipeline = [{"$group": {"_id": None, "total_size": {"$sum": "$file_size"}}}]
    total_size_result = await stats_collection.aggregate(pipeline).to_list(1)
    total_size = total_size_result[0]["total_size"] if total_size_result else 0
    return total_users, total_downloads, total_size

async def update_download_stats(user_id, file_size, filename):
    """Update download statistics"""
    await users_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"downloads": 1, "total_downloaded": file_size}}
    )
    await stats_collection.insert_one({
        "user_id": user_id,
        "filename": filename,
        "file_size": file_size,
        "download_date": datetime.now()
    })

async def get_terabox_info(url):
    """Get file info from Terabox API"""
    api_url = f"https://noor-terabox-api.woodmirror.workers.dev/api?url={url}"
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if "error" not in data and "proxy_url" in data:
                        return data
                    else:
                        return {"error": data.get("error", "Invalid response from API")}
                else:
                    return {"error": f"API request failed with status {response.status}"}
    except Exception as e:
        logger.error(f"API request error: {e}")
        return {"error": f"Network error: {str(e)}"}

def get_terabox_info_sync(url):
    """Synchronous version using requests for fallback"""
    api_url = f"https://noor-terabox-api.woodmirror.workers.dev/api?url={url}"
    
    try:
        response = requests.get(api_url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if "error" not in data and "proxy_url" in data:
                return data
            else:
                return {"error": data.get("error", "Invalid response from API")}
        else:
            return {"error": f"API request failed with status {response.status_code}"}
    except Exception as e:
        logger.error(f"Sync API request error: {e}")
        return {"error": f"Network error: {str(e)}"}

async def download_file_optimized(url, filename, user_id, progress_message):
    """Download file with optimized speed and progress tracking"""
    filepath = os.path.join(DOWNLOAD_PATH, filename)
    
    try:
        # Configure session for maximum speed
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=10,
            ttl_dns_cache=300,
            use_dns_cache=True,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                start_time = time.time()
                last_update = 0
                
                async with aiofiles.open(filepath, 'wb') as file:
                    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                        await file.write(chunk)
                        downloaded += len(chunk)
                        
                        current_time = time.time()
                        # Update progress every 3 seconds to avoid rate limits
                        if current_time - last_update > 3:
                            try:
                                elapsed = current_time - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                eta = (total_size - downloaded) / speed if speed > 0 else 0
                                
                                progress_bar = get_progress_bar(downloaded, total_size)
                                
                                progress_text = (
                                    f"📥 **Downloading:** `{filename}`\n\n"
                                    f"{progress_bar}\n"
                                    f"📊 **Progress:** `{humanize.naturalsize(downloaded)}` / `{humanize.naturalsize(total_size)}`\n"
                                    f"⚡ **Speed:** `{humanize.naturalsize(speed)}/s`\n"
                                    f"⏱️ **ETA:** `{humanize.naturaldelta(eta)}`\n"
                                    f"🔄 **Status:** `Downloading...`"
                                )
                                
                                await progress_message.edit_text(progress_text)
                                last_update = current_time
                            except Exception as e:
                                logger.error(f"Progress update error: {e}")
                
                return filepath
                
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

def download_file_sync(url, filename):
    """Synchronous download using requests as fallback"""
    filepath = os.path.join(DOWNLOAD_PATH, filename)
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
        }
        
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        if response.status_code == 200:
            with open(filepath, 'wb') as file:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        file.write(chunk)
            return filepath
        else:
            return None
            
    except Exception as e:
        logger.error(f"Sync download error: {e}")
        return None

def get_progress_bar(current, total, length=20):
    """Generate progress bar"""
    if total == 0:
        return "░" * length + " 0%"
    
    percent = (current / total) * 100
    filled = int(length * current // total)
    bar = "█" * filled + "░" * (length - filled)
    return f"{bar} {percent:.1f}%"

def get_file_type(filename):
    """Get file type from filename"""
    ext = filename.lower().split('.')[-1]
    video_exts = ['mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v']
    audio_exts = ['mp3', 'flac', 'wav', 'aac', 'ogg', 'm4a']
    image_exts = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']
    
    if ext in video_exts:
        return "video"
    elif ext in audio_exts:
        return "audio"
    elif ext in image_exts:
        return "image"
    else:
        return "document"

@app.on_message(filters.command("start"))
async def start_command(client, message):
    """Start command handler"""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    await add_user(user_id, username)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="stats"),
         InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help"),
         InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]
    ])
    
    welcome_text = (
        "🚀 **Welcome to Advanced Terabox Download Bot!**\n\n"
        "✨ **Features:**\n"
        "• Ultra-fast multi-threaded downloads\n"
        "• Real-time progress tracking\n"
        "• Smart upload type detection\n"
        "• Comprehensive statistics\n"
        "• Optimized for maximum speed\n\n"
        "📨 **Usage:** Just send me a Terabox URL!\n\n"
        "🔥 **Powered by advanced algorithms**\n"
        "📤 **Credits:** @NY_BOTS"
    )
    
    await message.reply_text(
        welcome_text,
        reply_markup=keyboard,
        message_effect_id=5104841245755180586
    )

@app.on_message(filters.command("help"))
async def help_command(client, message):
    """Help command handler"""
    help_text = (
        "ℹ️ **How to Use the Bot**\n\n"
        "1️⃣ **Send Terabox URL:** Just paste any Terabox link\n"
        "2️⃣ **Wait for Processing:** Bot will fetch file info\n"
        "3️⃣ **Click Download:** Start the download process\n"
        "4️⃣ **Get Your File:** Receive the file in chat\n\n"
        "🔗 **Supported URLs:**\n"
        "• terabox.com\n"
        "• 1024tera.com\n"
        "• teraboxapp.com\n"
        "• nephobox.com\n\n"
        "⚙️ **Commands:**\n"
        "• /start - Start the bot\n"
        "• /help - Show this help\n"
        "• /stats - Show bot statistics\n\n"
        "📤 **Support:** @NY_BOTS"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back")]
    ])
    
    await message.reply_text(help_text, reply_markup=keyboard)

@app.on_message(filters.command("stats"))
async def stats_command(client, message):
    """Stats command handler"""
    total_users, total_downloads, total_size = await get_user_stats()
    
    stats_text = (
        f"📊 **Bot Statistics**\n\n"
        f"👥 **Total Users:** `{total_users:,}`\n"
        f"📥 **Total Downloads:** `{total_downloads:,}`\n"
        f"💾 **Total Downloaded:** `{humanize.naturalsize(total_size)}`\n"
        f"🤖 **Bot Status:** `Online & Fast`\n"
        f"⚡ **Server:** `High Performance`\n"
        f"🔧 **Engine:** `Advanced Multi-threaded`\n\n"
        f"📈 **Performance:** Excellent\n"
        f"🚀 **Speed:** Ultra Fast\n\n"
        f"📤 **Made by:** @NY_BOTS"
    )
    
    await message.reply_text(stats_text)

@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "stats"]))
async def handle_url(client, message):
    """Handle Terabox URL"""
    url = message.text.strip()
    
    # Validate Terabox URL
    if not any(domain in url.lower() for domain in ["terabox", "1024tera", "teraboxapp", "nephobox"]):
        await message.reply_text(
            "❌ **Invalid URL!**\n\n"
            "Please send a valid Terabox URL.\n"
            "Example: `https://terabox.com/s/xxxxx`",
            message_effect_id=5104841245755180586
        )
        return
    
    user_id = message.from_user.id
    await add_user(user_id, message.from_user.username or message.from_user.first_name)
    
    # Processing message
    processing_msg = await message.reply_text(
        "🔍 **Processing Request...**\n\n"
        "⏳ Fetching file information from Terabox...\n"
        "🔄 Please wait...",
        message_effect_id=5104841245755180586
    )
    
    # Get file info from API
    file_info = await get_terabox_info(url)
    
    if "error" in file_info:
        await processing_msg.edit_text(
            f"❌ **Error Occurred!**\n\n"
            f"**Details:** {file_info['error']}\n\n"
            f"🔄 Please try again or check your URL."
        )
        return
    
    # Extract file information
    filename = file_info.get('file_name', 'Unknown')
    file_size = file_info.get('file_size', 'Unknown')
    size_bytes = file_info.get('size_bytes', 0)
    file_type = get_file_type(filename)
    
    # Create download keyboard
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download Now", callback_data=f"download_{message.message_id}")],
        [InlineKeyboardButton("📋 File Details", callback_data=f"details_{message.message_id}"),
         InlineKeyboardButton("🔄 Refresh Info", callback_data=f"refresh_{message.message_id}")]
    ])
    
    # Store file info for callback
    download_progress[message.message_id] = {
        'url': url,
        'file_info': file_info,
        'user_id': user_id
    }
    
    info_text = (
        f"📁 **File Ready for Download!**\n\n"
        f"📄 **Name:** `{filename}`\n"
        f"📊 **Size:** `{file_size}` ({humanize.naturalsize(size_bytes)})\n"
        f"🎭 **Type:** `{file_type.upper()}`\n"
        f"✅ **Status:** `Ready`\n\n"
        f"🚀 **Click Download to start!**"
    )
    
    await processing_msg.edit_text(info_text, reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"^download_"))
async def download_callback(client, callback: CallbackQuery):
    """Handle download callback"""
    try:
        message_id = int(callback.data.split("_")[1])
        
        if message_id not in download_progress:
            await callback.answer("❌ Session expired! Please send the URL again.", show_alert=True)
            return
        
        data = download_progress[message_id]
        file_info = data['file_info']
        user_id = data['user_id']
        
        await callback.answer("🚀 Starting download...")
        
        # Update message to show download starting
        progress_msg = await callback.message.edit_text(
            "📥 **Initializing Download...**\n\n"
            "🔄 Preparing high-speed download...\n"
            "⚡ Optimizing connection...\n"
            "⏳ Please wait..."
        )
        
        # Start download
        filename = file_info['file_name']
        filepath = await download_file_optimized(
            file_info['proxy_url'], 
            filename, 
            user_id, 
            progress_msg
        )
        
        if not filepath or not os.path.exists(filepath):
            await progress_msg.edit_text(
                "❌ **Download Failed!**\n\n"
                "Possible reasons:\n"
                "• Network connection issue\n"
                "• File link expired\n"
                "• Server temporarily unavailable\n\n"
                "🔄 Please try again later."
            )
            return
        
        # Start upload
        await progress_msg.edit_text(
            "📤 **Preparing Upload...**\n\n"
            "⏳ Initializing upload process...\n"
            "🔄 Please wait..."
        )
        
        # Set chat action
        await client.send_chat_action(callback.message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        
        # Get user upload preference
        user_data = await users_collection.find_one({"user_id": user_id})
        upload_type = user_data.get("upload_type", "video") if user_data else "video"
        
        file_size = os.path.getsize(filepath)
        file_type = get_file_type(filename)
        
        # Upload progress callback
        async def upload_progress_callback(current, total):
            try:
                progress_bar = get_progress_bar(current, total)
                percent = (current / total) * 100
                
                await progress_msg.edit_text(
                    f"📤 **Uploading:** `{filename}`\n\n"
                    f"{progress_bar}\n"
                    f"📊 **Progress:** `{humanize.naturalsize(current)}` / `{humanize.naturalsize(total)}`\n"
                    f"📈 **Percent:** `{percent:.1f}%`\n"
                    f"🔄 **Status:** `Uploading...`"
                )
            except Exception as e:
                logger.error(f"Upload progress error: {e}")
        
        # Create caption
        caption = (
            f"📁 **File:** `{filename}`\n"
            f"📊 **Size:** `{humanize.naturalsize(file_size)}`\n"
            f"🎭 **Type:** `{file_type.upper()}`\n"
            f"⏱️ **Downloaded:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            f"🚀 **Fast Download Powered by Advanced Algorithms**\n"
            f"📤 **Credits:** @NY_BOTS"
        )
        
        # Upload based on type and user preference
        try:
            if (upload_type == "video" and file_type == "video") or file_type == "video":
                await callback.message.reply_video(
                    filepath,
                    caption=caption,
                    progress=upload_progress_callback,
                    supports_streaming=True,
                    duration=0,
                    width=0,
                    height=0
                )
            elif file_type == "audio":
                await callback.message.reply_audio(
                    filepath,
                    caption=caption,
                    progress=upload_progress_callback,
                    duration=0
                )
            elif file_type == "image":
                await callback.message.reply_photo(
                    filepath,
                    caption=caption,
                    progress=upload_progress_callback
                )
            else:
                await callback.message.reply_document(
                    filepath,
                    caption=caption,
                    progress=upload_progress_callback
                )
            
            # Success message
            await progress_msg.edit_text(
                "✅ **Upload Completed Successfully!**\n\n"
                f"📁 **File:** `{filename}`\n"
                f"📊 **Size:** `{humanize.naturalsize(file_size)}`\n"
                f"🎉 **Status:** `Completed`\n\n"
                f"Thank you for using our service!"
            )
            
            # Update statistics
            await update_download_stats(user_id, file_size, filename)
            
            # Log to channel
            try:
                await client.send_message(
                    LOG_CHANNEL,
                    f"📥 **Download Completed**\n\n"
                    f"👤 **User:** {callback.from_user.mention}\n"
                    f"🆔 **ID:** `{user_id}`\n"
                    f"📁 **File:** `{filename}`\n"
                    f"📊 **Size:** `{humanize.naturalsize(file_size)}`\n"
                    f"🎭 **Type:** `{file_type}`\n"
                    f"⏱️ **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                    f"🔗 **URL:** `{data['url'][:50]}...`"
                )
            except Exception as e:
                logger.error(f"Log channel error: {e}")
        
        except Exception as e:
            logger.error(f"Upload error: {e}")
            await progress_msg.edit_text(
                f"❌ **Upload Failed!**\n\n"
                f"**Error:** {str(e)}\n\n"
                f"The file was downloaded but upload failed.\n"
                f"Please try again or contact support."
            )
        
        finally:
            # Cleanup
            try:
                os.remove(filepath)
                if message_id in download_progress:
                    del download_progress[message_id]
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    except Exception as e:
        logger.error(f"Download callback error: {e}")
        await callback.answer("❌ An error occurred! Please try again.", show_alert=True)

@app.on_callback_query(filters.regex(r"^details_"))
async def details_callback(client, callback: CallbackQuery):
    """Show file details"""
    try:
        message_id = int(callback.data.split("_")[1])
        
        if message_id not in download_progress:
            await callback.answer("❌ Session expired!", show_alert=True)
            return
        
        data = download_progress[message_id]
        file_info = data['file_info']
        
        details_text = (
            f"📋 **File Details**\n\n"
            f"📄 **Name:** `{file_info.get('file_name', 'Unknown')}`\n"
            f"📊 **Size:** `{file_info.get('file_size', 'Unknown')}`\n"
            f"🔗 **Direct URL:** `Available`\n"
            f"🎭 **Type:** `{get_file_type(file_info.get('file_name', '')).upper()}`\n"
            f"📅 **Fetched:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"✅ **Status:** `Ready for Download`\n\n"
            f"🚀 **Ready to download at maximum speed!**"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download Now", callback_data=f"download_{message_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"back_{message_id}")]
        ])
        
        await callback.message.edit_text(details_text, reply_markup=keyboard)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Details callback error: {e}")
        await callback.answer("❌ Error showing details!", show_alert=True)

@app.on_callback_query(filters.regex(r"^refresh_"))
async def refresh_callback(client, callback: CallbackQuery):
    """Refresh file info"""
    try:
        message_id = int(callback.data.split("_")[1])
        
        if message_id not in download_progress:
            await callback.answer("❌ Session expired!", show_alert=True)
            return
        
        await callback.answer("🔄 Refreshing file info...")
        
        data = download_progress[message_id]
        url = data['url']
        
        # Update message to show refreshing
        await callback.message.edit_text(
            "🔄 **Refreshing File Info...**\n\n"
            "⏳ Fetching latest information...\n"
            "🔄 Please wait..."
        )
        
        # Get fresh file info
        file_info = await get_terabox_info(url)
        
        if "error" in file_info:
            await callback.message.edit_text(
                f"❌ **Refresh Failed!**\n\n"
                f"**Error:** {file_info['error']}\n\n"
                f"🔄 Please try again later."
            )
            return
        
        # Update stored data
        download_progress[message_id]['file_info'] = file_info
        
        # Show updated info
        filename = file_info.get('file_name', 'Unknown')
        file_size = file_info.get('file_size', 'Unknown')
        size_bytes = file_info.get('size_bytes', 0)
        file_type = get_file_type(filename)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download Now", callback_data=f"download_{message_id}")],
            [InlineKeyboardButton("📋 File Details", callback_data=f"details_{message_id}"),
             InlineKeyboardButton("🔄 Refresh Info", callback_data=f"refresh_{message_id}")]
        ])
        
        info_text = (
            f"📁 **File Info Refreshed!**\n\n"
            f"📄 **Name:** `{filename}`\n"
            f"📊 **Size:** `{file_size}` ({humanize.naturalsize(size_bytes)})\n"
            f"🎭 **Type:** `{file_type.upper()}`\n"
            f"✅ **Status:** `Ready`\n"
            f"🔄 **Updated:** `{datetime.now().strftime('%H:%M:%S')}`\n\n"
            f"🚀 **Click Download to start!**"
        )
        
        await callback.message.edit_text(info_text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Refresh callback error: {e}")
        await callback.answer("❌ Error refreshing info!", show_alert=True)

@app.on_callback_query(filters.regex("^stats$"))
async def stats_callback(client, callback: CallbackQuery):
    """Show bot statistics"""
    total_users, total_downloads, total_size = await get_user_stats()
    
    stats_text = (
        f"📊 **Bot Statistics**\n\n"
        f"👥 **Total Users:** `{total_users:,}`\n"
        f"📥 **Total Downloads:** `{total_downloads:,}`\n"
        f"💾 **Total Downloaded:** `{humanize.naturalsize(total_size)}`\n"
        f"🤖 **Bot Status:** `Online & Fast`\n"
        f"⚡ **Server:** `High Performance`\n"
        f"🔧 **Engine:** `Advanced Multi-threaded`\n\n"
        f"📈 **Performance:** Excellent\n"
        f"🚀 **Speed:** Ultra Fast\n\n"
        f"📤 **Made by:** @NY_BOTS"
    )
    
    await callback.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="back"),
             InlineKeyboardButton("🔄 Refresh", callback_data="stats")]
        ])
    )

@app.on_callback_query(filters.regex("^settings$"))
async def settings_callback(client, callback: CallbackQuery):
    """Show user settings"""
    user_id = callback.from_user.id
    user_data = await users_collection.find_one({"user_id": user_id})
    
    if user_data:
        upload_type = user_data.get("upload_type", "video")
        user_downloads = user_data.get("downloads", 0)
        total_downloaded = user_data.get("total_downloaded", 0)
    else:
        upload_type = "video"
        user_downloads = 0
        total_downloaded = 0
        [InlineKeyboardButton(f"📹 Video {'✅' if upload_type == 'video' else '❌'}", callback_data="set_video")],
        [InlineKeyboardButton(f"📄 Document {'✅' if upload_type == 'document' else '❌'}", callback_data="set_document")],
        [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])
    
    settings_text = (
        f"⚙️ **Your Settings**\n\n"
        f"📤 **Upload Type:** `{upload_type.title()}`\n"
        f"📥 **Downloads:** `{user_downloads}`\n"
        f"💾 **Total Downloaded:** `{humanize.naturalsize(total_downloaded)}`\n\n"
        f"🎯 **Customize your upload preferences**\n"
        f"📹 **Video:** Upload videos as video files\n"
        f"📄 **Document:** Upload all files as documents\n\n"
        f"💡 **Tip:** Video mode supports streaming!"
    )
    
    await callback.message.edit_text(settings_text, reply_markup=keyboard)

@app.on_callback_query(filters.regex("^set_video$"))
async def set_video_callback(client, callback: CallbackQuery):
    """Set upload type to video"""
    user_id = callback.from_user.id
    
    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"upload_type": "video"}},
        upsert=True
    )
    
    await callback.answer("✅ Upload type set to Video!", show_alert=True)
    
    # Refresh settings page
    await settings_callback(client, callback)

@app.on_callback_query(filters.regex("^set_document$"))
async def set_document_callback(client, callback: CallbackQuery):
    """Set upload type to document"""
    user_id = callback.from_user.id
    
    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"upload_type": "document"}},
        upsert=True
    )
    
    await callback.answer("✅ Upload type set to Document!", show_alert=True)
    
    # Refresh settings page
    await settings_callback(client, callback)

@app.on_callback_query(filters.regex("^my_stats$"))
async def my_stats_callback(client, callback: CallbackQuery):
    """Show user personal statistics"""
    user_id = callback.from_user.id
    user_data = await users_collection.find_one({"user_id": user_id})
    
    if user_data:
        join_date = user_data.get("join_date", datetime.now())
        downloads = user_data.get("downloads", 0)
        total_downloaded = user_data.get("total_downloaded", 0)
        upload_type = user_data.get("upload_type", "video")
        
        # Calculate days since joining
        days_since_join = (datetime.now() - join_date).days
        
        # Get user's download history
        user_downloads_history = await stats_collection.find({"user_id": user_id}).sort("download_date", -1).limit(5).to_list(5)
        
        recent_downloads = ""
        if user_downloads_history:
            recent_downloads = "\n📋 **Recent Downloads:**\n"
            for i, download in enumerate(user_downloads_history, 1):
                filename = download.get("filename", "Unknown")[:30]
                size = humanize.naturalsize(download.get("file_size", 0))
                recent_downloads += f"`{i}.` {filename}... ({size})\n"
        
        stats_text = (
            f"📊 **Your Personal Stats**\n\n"
            f"👤 **User:** {callback.from_user.mention}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"📅 **Joined:** `{join_date.strftime('%Y-%m-%d')}`\n"
            f"⏰ **Days Active:** `{days_since_join}`\n"
            f"📥 **Total Downloads:** `{downloads}`\n"
            f"💾 **Data Downloaded:** `{humanize.naturalsize(total_downloaded)}`\n"
            f"📤 **Upload Preference:** `{upload_type.title()}`\n"
            f"{recent_downloads}\n"
            f"🏆 **Rank:** {'Premium User' if downloads > 50 else 'Regular User'}\n"
            f"⭐ **Status:** {'Active' if downloads > 0 else 'New'}"
        )
    else:
        stats_text = (
            f"📊 **Your Personal Stats**\n\n"
            f"👤 **User:** {callback.from_user.mention}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"📅 **Status:** `New User`\n"
            f"📥 **Downloads:** `0`\n"
            f"💾 **Data Downloaded:** `0 B`\n\n"
            f"🚀 **Start downloading to see your stats!**"
        )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="settings")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back")]
    ])
    
    await callback.message.edit_text(stats_text, reply_markup=keyboard)

@app.on_callback_query(filters.regex("^help$"))
async def help_callback(client, callback: CallbackQuery):
    """Show help information"""
    help_text = (
        "ℹ️ **How to Use the Bot**\n\n"
        "1️⃣ **Send Terabox URL:** Just paste any Terabox link\n"
        "2️⃣ **Wait for Processing:** Bot will fetch file info\n"
        "3️⃣ **Click Download:** Start the download process\n"
        "4️⃣ **Get Your File:** Receive the file in chat\n\n"
        "🔗 **Supported URLs:**\n"
        "• terabox.com\n"
        "• 1024tera.com\n"
        "• teraboxapp.com\n"
        "• nephobox.com\n\n"
        "⚙️ **Commands:**\n"
        "• /start - Start the bot\n"
        "• /help - Show this help\n"
        "• /stats - Show bot statistics\n\n"
        "🎯 **Features:**\n"
        "• Ultra-fast downloads\n"
        "• Real-time progress tracking\n"
        "• Multiple upload formats\n"
        "• Personal statistics\n"
        "• Smart file type detection\n\n"
        "❓ **Need Help?** Contact @NY_BOTS"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back")]
    ])
    
    await callback.message.edit_text(help_text, reply_markup=keyboard)

@app.on_callback_query(filters.regex("^back$"))
async def back_callback(client, callback: CallbackQuery):
    """Go back to main menu"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="stats"),
         InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help"),
         InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]
    ])
    
    welcome_text = (
        "🚀 **Welcome to Advanced Terabox Download Bot!**\n\n"
        "✨ **Features:**\n"
        "• Ultra-fast multi-threaded downloads\n"
        "• Real-time progress tracking\n"
        "• Smart upload type detection\n"
        "• Comprehensive statistics\n"
        "• Optimized for maximum speed\n\n"
        "📨 **Usage:** Just send me a Terabox URL!\n\n"
        "🔥 **Powered by advanced algorithms**\n"
        "📤 **Credits:** @NY_BOTS"
    )
    
    await callback.message.edit_text(welcome_text, reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"^back_"))
async def back_to_file_callback(client, callback: CallbackQuery):
    """Go back to file info"""
    try:
        message_id = int(callback.data.split("_")[1])
        
        if message_id not in download_progress:
            await callback.answer("❌ Session expired!", show_alert=True)
            return
        
        data = download_progress[message_id]
        file_info = data['file_info']
        
        filename = file_info.get('file_name', 'Unknown')
        file_size = file_info.get('file_size', 'Unknown')
        size_bytes = file_info.get('size_bytes', 0)
        file_type = get_file_type(filename)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download Now", callback_data=f"download_{message_id}")],
            [InlineKeyboardButton("📋 File Details", callback_data=f"details_{message_id}"),
             InlineKeyboardButton("🔄 Refresh Info", callback_data=f"refresh_{message_id}")]
        ])
        
        info_text = (
            f"📁 **File Ready for Download!**\n\n"
            f"📄 **Name:** `{filename}`\n"
            f"📊 **Size:** `{file_size}` ({humanize.naturalsize(size_bytes)})\n"
            f"🎭 **Type:** `{file_type.upper()}`\n"
            f"✅ **Status:** `Ready`\n\n"
            f"🚀 **Click Download to start!**"
        )
        
        await callback.message.edit_text(info_text, reply_markup=keyboard)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Back to file callback error: {e}")
        await callback.answer("❌ Error going back!", show_alert=True)

@app.on_callback_query(filters.regex("^refresh$"))
async def refresh_main_callback(client, callback: CallbackQuery):
    """Refresh main menu"""
    await callback.answer("🔄 Refreshed!")
    await back_callback(client, callback)

# Error handler
@app.on_message(filters.all & filters.private)
async def handle_other_messages(client, message):
    """Handle other messages"""
    if message.text and not message.text.startswith('/'):
        # If it's not a command and not a URL, show help
        if not any(domain in message.text.lower() for domain in ["terabox", "1024tera", "teraboxapp", "nephobox", "http"]):
            await message.reply_text(
                "❓ **Unknown Message**\n\n"
                "Please send a valid Terabox URL or use /help for instructions.\n\n"
                "📝 **Example:** `https://terabox.com/s/xxxxx`\n"
                "ℹ️ **Help:** /help"
            )

# Admin commands (optional)
ADMIN_IDS = [123456789]  # Add admin user IDs

@app.on_message(filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast_command(client, message):
    """Broadcast message to all users (Admin only)"""
    if len(message.command) < 2:
        await message.reply_text("❌ **Usage:** `/broadcast <message>`")
        return
    
    broadcast_text = message.text.split(None, 1)[1]
    
    # Get all users
    users = await users_collection.find({}).to_list(None)
    
    success = 0
    failed = 0
    
    status_msg = await message.reply_text(f"📢 **Broadcasting to {len(users)} users...**")
    
    for user in users:
        try:
            await client.send_message(user['user_id'], broadcast_text)
            success += 1
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast failed for {user['user_id']}: {e}")
        
        # Update status every 50 users
        if (success + failed) % 50 == 0:
            await status_msg.edit_text(
                f"📢 **Broadcasting...**\n\n"
                f"✅ **Success:** {success}\n"
                f"❌ **Failed:** {failed}\n"
                f"⏳ **Remaining:** {len(users) - success - failed}"
            )
    
    await status_msg.edit_text(
        f"📢 **Broadcast Completed!**\n\n"
        f"✅ **Success:** {success}\n"
        f"❌ **Failed:** {failed}\n"
        f"📊 **Total:** {len(users)}"
    )

@app.on_message(filters.command("users") & filters.user(ADMIN_IDS))
async def users_command(client, message):
    """Show user statistics (Admin only)"""
    total_users, total_downloads, total_size = await get_user_stats()
    
    # Get recent users
    recent_users = await users_collection.find({}).sort("join_date", -1).limit(10).to_list(10)
    
    recent_list = ""
    for user in recent_users:
        username = user.get('username', 'Unknown')
        join_date = user.get('join_date', datetime.now()).strftime('%Y-%m-%d')
        downloads = user.get('downloads', 0)
        recent_list += f"• @{username} ({downloads} downloads) - {join_date}\n"
    
    admin_stats = (
        f"👥 **Admin Statistics**\n\n"
        f"📊 **Total Users:** `{total_users:,}`\n"
        f"📥 **Total Downloads:** `{total_downloads:,}`\n"
        f"💾 **Total Data:** `{humanize.naturalsize(total_size)}`\n\n"
        f"👤 **Recent Users:**\n{recent_list}\n"
        f"🤖 **Bot Status:** Online\n"
        f"⚡ **Performance:** Excellent"
    )
    
    await message.reply_text(admin_stats)

# Start the bot
if __name__ == "__main__":
    logger.info("🚀 Starting Terabox Download Bot...")
    try:
        app.run()
    except Exception as e:
        logger.error(f"Bot startup error: {e}")
