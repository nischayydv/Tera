import asyncio
import aiohttp
import aiofiles
import os
import time
import logging
from datetime import datetime
from urllib.parse import urlparse
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatAction
import humanize

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

# Progress tracking
active_downloads = {}
progress_messages = {}

async def add_user(user_id, username):
    """Add user to database"""
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
    """Get bot statistics"""
    total_users = await users_collection.count_documents({})
    total_downloads = await stats_collection.count_documents({})
    return total_users, total_downloads

async def update_download_stats(user_id, file_size):
    """Update download statistics"""
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
    """Get file info from Terabox API"""
    api_url = f"https://noor-terabox-api.woodmirror.workers.dev/api?url={url}"
    
    try:
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
    except Exception as e:
        return {"error": str(e)}

def get_progress_bar(current, total, length=20):
    """Generate progress bar"""
    if total == 0:
        return "░" * length + " 0%"
    percent = (current / total) * 100
    filled = int(length * current // total)
    bar = "█" * filled + "░" * (length - filled)
    return f"{bar} {percent:.1f}%"

async def download_file(url, filename, user_id, progress_msg):
    """Download file with progress tracking"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    start_time = time.time()
                    last_update = 0
                    
                    filepath = os.path.join(DOWNLOAD_PATH, filename)
                    
                    async with aiofiles.open(filepath, 'wb') as file:
                        async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                            await file.write(chunk)
                            downloaded += len(chunk)
                            
                            current_time = time.time()
                            if current_time - last_update >= 3:  # Update every 3 seconds
                                elapsed = current_time - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                eta = (total_size - downloaded) / speed if speed > 0 else 0
                                
                                progress_bar = get_progress_bar(downloaded, total_size)
                                
                                try:
                                    await progress_msg.edit_text(
                                        f"📥 **Downloading:** `{filename}`\n\n"
                                        f"{progress_bar}\n"
                                        f"📊 **Size:** `{humanize.naturalsize(downloaded)}` / `{humanize.naturalsize(total_size)}`\n"
                                        f"⚡ **Speed:** `{humanize.naturalsize(speed)}/s`\n"
                                        f"⏱️ **ETA:** `{humanize.naturaldelta(eta)}`\n"
                                        f"🚀 **Status:** Downloading..."
                                    )
                                except Exception as e:
                                    logger.error(f"Progress update error: {e}")
                                
                                last_update = current_time
                    
                    return filepath
                else:
                    return None
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

async def upload_file(client, chat_id, filepath, caption, upload_type, progress_msg):
    """Upload file with progress tracking"""
    file_size = os.path.getsize(filepath)
    last_update = 0
    
    async def upload_progress(current, total):
        nonlocal last_update
        current_time = time.time()
        if current_time - last_update >= 3:  # Update every 3 seconds
            progress_bar = get_progress_bar(current, total)
            try:
                await progress_msg.edit_text(
                    f"📤 **Uploading:** `{os.path.basename(filepath)}`\n\n"
                    f"{progress_bar}\n"
                    f"📊 **Size:** `{humanize.naturalsize(current)}` / `{humanize.naturalsize(total)}`\n"
                    f"🚀 **Status:** Uploading..."
                )
            except Exception as e:
                logger.error(f"Upload progress error: {e}")
            last_update = current_time
    
    try:
        if upload_type == "video" and filepath.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv')):
            await client.send_video(
                chat_id,
                filepath,
                caption=caption,
                progress=upload_progress,
                supports_streaming=True
            )
        else:
            await client.send_document(
                chat_id,
                filepath,
                caption=caption,
                progress=upload_progress
            )
        return True
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return False

@app.on_message(filters.command("start"))
async def start_command(client, message):
    """Start command handler"""
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
        "• High-speed downloads with progress tracking\n"
        "• Upload as video or document\n"
        "• Real-time statistics\n"
        "• Advanced download optimization\n"
        "• Smart progress updates\n\n"
        "📤 **Credit:** @NY_BOTS",
        reply_markup=keyboard,
        message_effect_id=5104841245755180586
    )

@app.on_message(filters.text & filters.private)
async def handle_url(client, message):
    """Handle Terabox URL messages"""
    url = message.text.strip()
    
    if not ("terabox" in url.lower() or "1024tera" in url.lower() or "mirrobox" in url.lower()):
        await message.reply_text("❌ Please send a valid Terabox URL!")
        return
    
    user_id = message.from_user.id
    await add_user(user_id, message.from_user.username)
    
    processing_msg = await message.reply_text(
        "🔍 **Processing your request...**\n\n"
        "⏳ Fetching file information...\n"
        "🔄 Please wait...",
        message_effect_id=5104841245755180586
    )
    
    # Get file info from API
    file_info = await get_terabox_info(url)
    
    if "error" in file_info:
        await processing_msg.edit_text(f"❌ **Error:** {file_info['error']}")
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download Now", callback_data=f"download_{user_id}_{url}")],
        [InlineKeyboardButton("📊 File Info", callback_data=f"info_{user_id}_{url}")]
    ])
    
    await processing_msg.edit_text(
        f"📁 **File Ready for Download:**\n\n"
        f"📄 **Name:** `{file_info['file_name']}`\n"
        f"📊 **Size:** `{file_info['file_size']}`\n"
        f"🖼️ **Type:** `{file_info['file_name'].split('.')[-1].upper()}`\n"
        f"⚡ **Status:** Ready\n\n"
        f"✅ **Click Download to start!**",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex(r"^download_"))
async def download_callback(client, callback: CallbackQuery):
    """Handle download button callback"""
    try:
        parts = callback.data.split("_", 2)
        user_id = int(parts[1])
        url = parts[2]
        
        # Verify user
        if callback.from_user.id != user_id:
            await callback.answer("❌ This download is not for you!", show_alert=True)
            return
        
        # Get file info
        file_info = await get_terabox_info(url)
        
        if "error" in file_info:
            await callback.answer(f"Error: {file_info['error']}", show_alert=True)
            return
        
        await callback.answer("🚀 Starting download...")
        
        # Edit message to show download progress
        progress_msg = await callback.message.edit_text(
            "📥 **Initializing Download...**\n\n"
            "🔄 Preparing download engine...\n"
            "⏳ Please wait...\n"
            "🚀 **Status:** Starting"
        )
        
        # Start download
        filepath = await download_file(
            file_info['proxy_url'], 
            file_info['file_name'], 
            user_id, 
            progress_msg
        )
        
        if not filepath or not os.path.exists(filepath):
            await progress_msg.edit_text(
                "❌ **Download Failed!**\n\n"
                "🔄 Please try again later.\n"
                "📞 Contact support if issue persists."
            )
            return
        
        # Update progress message for upload
        await progress_msg.edit_text(
            "📤 **Preparing Upload...**\n\n"
            "🔄 Initializing upload engine...\n"
            "⏳ Please wait...\n"
            "🚀 **Status:** Starting Upload"
        )
        
        # Set upload action
        await client.send_chat_action(callback.message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        
        # Get user upload preference
        user_data = await users_collection.find_one({"user_id": user_id})
        upload_type = user_data.get("upload_type", "video") if user_data else "video"
        
        file_size = os.path.getsize(filepath)
        
        # Create caption
        caption = (
            f"📁 **File:** `{file_info['file_name']}`\n"
            f"📊 **Size:** `{file_info['file_size']}`\n"
            f"🚀 **Downloaded successfully!**\n\n"
            f"📤 **Credit:** @NY_BOTS"
        )
        
        # Upload file
        upload_success = await upload_file(
            client, 
            callback.message.chat.id, 
            filepath, 
            caption, 
            upload_type, 
            progress_msg
        )
        
        if upload_success:
            await progress_msg.delete()
            
            # Send success message
            await callback.message.reply_text(
                "✅ **Download Complete!**\n\n"
                f"📁 **File:** `{file_info['file_name']}`\n"
                f"📊 **Size:** `{file_info['file_size']}`\n"
                f"🚀 **Status:** Successfully uploaded!\n\n"
                f"📤 **Credit:** @NY_BOTS"
            )
            
            # Update stats
            await update_download_stats(user_id, file_size)
            
            # Log to channel
            try:
                await client.send_message(
                    LOG_CHANNEL,
                    f"📥 **New Download**\n\n"
                    f"👤 **User:** {callback.from_user.mention}\n"
                    f"🆔 **ID:** `{user_id}`\n"
                    f"📁 **File:** `{file_info['file_name']}`\n"
                    f"📊 **Size:** `{file_info['file_size']}`\n"
                    f"🕐 **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                )
            except Exception as e:
                logger.error(f"Log error: {e}")
        else:
            await progress_msg.edit_text(
                "❌ **Upload Failed!**\n\n"
                "🔄 Please try again later.\n"
                "📞 Contact support if issue persists."
            )
    
    except Exception as e:
        logger.error(f"Download callback error: {e}")
        await callback.message.edit_text(f"❌ **Error:** {str(e)}")
    
    finally:
        # Clean up
        try:
            if 'filepath' in locals() and filepath:
                os.remove(filepath)
        except:
            pass

@app.on_callback_query(filters.regex(r"^info_"))
async def info_callback(client, callback: CallbackQuery):
    """Handle info button callback"""
    try:
        parts = callback.data.split("_", 2)
        user_id = int(parts[1])
        url = parts[2]
        
        # Get file info
        file_info = await get_terabox_info(url)
        
        if "error" in file_info:
            await callback.answer(f"Error: {file_info['error']}", show_alert=True)
            return
        
        info_text = (
            f"📁 **Detailed File Information:**\n\n"
            f"📄 **Name:** `{file_info['file_name']}`\n"
            f"📊 **Size:** `{file_info['file_size']}`\n"
            f"📦 **Bytes:** `{file_info['size_bytes']:,}`\n"
            f"🔗 **Direct Link:** Available\n"
            f"🖼️ **Thumbnail:** {'Available' if file_info.get('thumbnail') else 'Not Available'}\n"
            f"⚡ **Status:** Ready for download\n\n"
            f"✅ **All systems ready!**"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download", callback_data=f"download_{user_id}_{url}")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])
        
        await callback.message.edit_text(info_text, reply_markup=keyboard)
    
    except Exception as e:
        logger.error(f"Info callback error: {e}")
        await callback.answer("❌ Error getting file info!", show_alert=True)

@app.on_callback_query(filters.regex("^stats$"))
async def stats_callback(client, callback: CallbackQuery):
    """Handle stats button callback"""
    try:
        total_users, total_downloads = await get_user_stats()
        
        await callback.message.edit_text(
            f"📊 **Bot Statistics:**\n\n"
            f"👥 **Total Users:** `{total_users:,}`\n"
            f"📥 **Total Downloads:** `{total_downloads:,}`\n"
            f"🚀 **Download Engine:** Advanced\n"
            f"⚡ **Progress Tracking:** Real-time\n"
            f"🤖 **Status:** `Online & Fast`\n"
            f"💾 **Storage:** Optimized\n\n"
            f"📤 **Credit:** @NY_BOTS",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back")]
            ])
        )
    except Exception as e:
        logger.error(f"Stats callback error: {e}")
        await callback.answer("❌ Error getting stats!", show_alert=True)

@app.on_callback_query(filters.regex("^settings$"))
async def settings_callback(client, callback: CallbackQuery):
    """Handle settings button callback"""
    try:
        user_id = callback.from_user.id
        user_data = await users_collection.find_one({"user_id": user_id})
        upload_type = user_data.get("upload_type", "video") if user_data else "video"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📹 Video {'✅' if upload_type == 'video' else ''}", callback_data="set_video")],
            [InlineKeyboardButton(f"📄 Document {'✅' if upload_type == 'document' else ''}", callback_data="set_document")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])
        
        await callback.message.edit_text(
            f"⚙️ **User Settings:**\n\n"
            f"📤 **Upload Type:** `{upload_type.title()}`\n"
            f"🚀 **Download Speed:** Optimized\n"
            f"📊 **Progress Updates:** Every 3 seconds\n"
            f"💾 **Auto Cleanup:** Enabled\n\n"
            f"Choose your preferred upload type:",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Settings callback error: {e}")
        await callback.answer("❌ Error loading settings!", show_alert=True)

@app.on_callback_query(filters.regex(r"^set_(video|document)$"))
async def set_upload_type(client, callback: CallbackQuery):
    """Handle upload type setting"""
    try:
        upload_type = callback.data.split("set_")[1]
        user_id = callback.from_user.id
        
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"upload_type": upload_type}},
            upsert=True
        )
        
        await callback.answer(f"✅ Upload type set to {upload_type.title()}")
        await settings_callback(client, callback)
    except Exception as e:
        logger.error(f"Set upload type error: {e}")
        await callback.answer("❌ Error updating settings!", show_alert=True)

@app.on_callback_query(filters.regex("^help$"))
async def help_callback(client, callback: CallbackQuery):
    """Handle help button callback"""
    await callback.message.edit_text(
        f"ℹ️ **Help & Instructions:**\n\n"
        f"🔗 **How to use:**\n"
        f"1. Send me a Terabox URL\n"
        f"2. Wait for file information\n"
        f"3. Click 'Download Now' button\n"
        f"4. Watch real-time progress\n"
        f"5. Get your file!\n\n"
        f"🚀 **Features:**\n"
        f"• High-speed downloads\n"
        f"• Real-time progress tracking\n"
        f"• Smart upload detection\n"
        f"• Multiple file format support\n"
        f"• Auto cleanup after upload\n\n"
        f"⚙️ **Settings:**\n"
        f"• Video/Document upload mode\n"
        f"• Download statistics\n"
        f"• Progress update frequency\n\n"
        f"📤 **Credit:** @NY_BOTS",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])
    )

@app.on_callback_query(filters.regex("^back$"))
async def back_callback(client, callback: CallbackQuery):
    """Handle back button callback"""
    await start_command(client, callback.message)

if __name__ == "__main__":
    print("🚀 Starting Terabox Download Bot...")
    print("📤 Credit: @NY_BOTS")
    app.run()
