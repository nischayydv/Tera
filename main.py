import os
import asyncio
import requests
import time
import math
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pymongo import MongoClient
import aiofiles
import aiohttp
from urllib.parse import quote

# Bot Configuration
API_ID = "24720215"
API_HASH = "c0d3395590fecba19985f95d6300785e"
BOT_TOKEN = "8037389280:AAG5WfzHcheszs-RHWL8WXszWPkrWjyulp8"
MONGO_URI = "mongodb+srv://Nischay999:Nischay999@cluster0.5kufo.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
FORCE_SUB_CHANNEL = "@NY_BOTS"
LOG_CHANNEL = -1002732334186  # Your log channel ID
OWNER_ID = 7910994767  # Your user ID
# Initialize bot
app = Client("terabox_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.terabox_bot
users_collection = db.users
stats_collection = db.stats

# API endpoint
TERABOX_API = "https://noor-terabox-api.woodmirror.workers.dev/api?url="

# Emojis and animations
FIRE_EFFECT = 5104841245755180586  # 🔥
DOWNLOAD_EMOJIS = ["📥", "⬇️", "💾", "📁", "🔄"]
UPLOAD_EMOJIS = ["📤", "⬆️", "☁️", "🚀", "✨"]

def get_size(bytes_size):
    """Convert bytes to human readable format"""
    if bytes_size == 0:
        return "0B"
    size_name = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    i = int(math.floor(math.log(bytes_size, 1024)))
    p = math.pow(1024, i)
    s = round(bytes_size / p, 2)
    return f"{s} {size_name[i]}"

def get_progress_bar(percentage):
    """Create animated progress bar"""
    filled = int(percentage / 10)
    empty = 10 - filled
    return f"{'🟢' * filled}{'⚪' * empty} {percentage:.1f}%"

async def add_user(user_id, username=None, first_name=None):
    """Add new user to database"""
    user_data = {
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "join_date": datetime.now(),
        "downloads": 0,
        "total_size": 0
    }
    users_collection.update_one(
        {"user_id": user_id},
        {"$setOnInsert": user_data},
        upsert=True
    )

async def update_user_stats(user_id, file_size):
    """Update user download stats"""
    users_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"downloads": 1, "total_size": file_size}}
    )

async def get_user_stats(user_id):
    """Get user statistics"""
    user = users_collection.find_one({"user_id": user_id})
    return user if user else {"downloads": 0, "total_size": 0}

async def check_force_sub(user_id):
    """Check if user is subscribed to force sub channel"""
    try:
        # Skip force sub check for owner
        if user_id == OWNER_ID:
            return True
            
        # Get chat member info
        member = await app.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        
        # Check if user is member, admin, or creator
        if member.status in ["member", "administrator", "creator"]:
            return True
        elif member.status == "kicked":
            return False
        else:
            return False
    except Exception as e:
        print(f"Error checking subscription for {user_id}: {e}")
        # If channel doesn't exist or bot is not admin, skip force sub
        return True

async def download_file(url, filename, progress_callback=None):
    """Download file with progress tracking"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            async with aiofiles.open(filename, 'wb') as file:
                async for chunk in response.content.iter_chunked(8192):
                    await file.write(chunk)
                    downloaded += len(chunk)
                    
                    if progress_callback and total_size > 0:
                        percentage = (downloaded / total_size) * 100
                        await progress_callback(downloaded, total_size, percentage)

# Start command
@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    print(f"User {user_id} ({first_name}) started the bot")
    
    # Add user to database
    await add_user(user_id, username, first_name)
    
    # Skip force sub check for owner
    if user_id != OWNER_ID:
        # Check force subscription
        is_subscribed = await check_force_sub(user_id)
        print(f"Subscription check for {user_id}: {is_subscribed}")
        
        if not is_subscribed:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL[1:]}")],
                [InlineKeyboardButton("🔄 Check Again", callback_data="check_sub")]
            ])
            await message.reply_text(
                f"🔒 **Access Denied!**\n\n"
                f"You must join our channel to use this bot.\n"
                f"Channel: {FORCE_SUB_CHANNEL}\n\n"
                f"📌 Join the channel and click 'Check Again'",
                reply_markup=keyboard,
                message_effect_id=FIRE_EFFECT
            )
            return
    
    # Show welcome message
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/NY_BOTS")]
    ])
    
    welcome_text = f"""
🔥 **Welcome to Terabox Download Bot!** 🔥

👋 Hello **{first_name}**!

🚀 **Features:**
• 📥 Fast Terabox Downloads
• 📊 Download Progress Tracking
• 📈 Upload Progress with Speed
• 📊 Personal Statistics
• 🎯 Clean & User-Friendly Interface

📝 **How to use:**
Send me any Terabox link and I'll download it for you!

💡 **Example:**
`https://terabox.com/s/1abcdefghijklmnop`

🔥 **Ready to download?** Send me a Terabox link now!

**Credits:** @NY_BOTS
"""
    
    await message.reply_text(
        welcome_text,
        reply_markup=keyboard,
        message_effect_id=FIRE_EFFECT
    )
    
    # Send log to owner
    try:
        await client.send_message(
            OWNER_ID,
            f"🆕 **New User Started Bot**\n\n"
            f"👤 **Name:** {first_name}\n"
            f"🆔 **User ID:** `{user_id}`\n"
            f"📝 **Username:** @{username if username else 'None'}\n"
            f"🕒 **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
    except Exception as e:
        print(f"Error sending log to owner: {e}")

# Help command
@app.on_callback_query(filters.regex("help"))
async def help_callback(client, callback: CallbackQuery):
    help_text = """
🆘 **How to Use Terabox Download Bot**

**Step 1:** Send me a Terabox link
**Step 2:** Wait for file information
**Step 3:** Click download button
**Step 4:** Get your file!

**Supported Links:**
• terabox.com
• 1024terabox.com
• 4funbox.com
• mirrobox.com
• nephobox.com
• momerybox.com
• teraboxapp.com

**Commands:**
• /start - Start the bot
• /stats - View your statistics
• /help - Show this help message

**Need Support?** Contact @NY_BOTS
"""
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back", callback_data="back_to_start")
    ]])
    
    await callback.edit_message_text(help_text, reply_markup=keyboard)

# Stats command
@app.on_message(filters.command("stats"))
async def stats_command(client, message: Message):
    await show_user_stats(message.from_user.id, message)

@app.on_callback_query(filters.regex("my_stats"))
async def stats_callback(client, callback: CallbackQuery):
    await show_user_stats(callback.from_user.id, callback)

async def show_user_stats(user_id, context):
    user_stats = await get_user_stats(user_id)
    total_users = users_collection.count_documents({})
    
    stats_text = f"""
📊 **Your Statistics**

👤 **User ID:** `{user_id}`
📥 **Downloads:** `{user_stats['downloads']}`
📦 **Total Size:** `{get_size(user_stats['total_size'])}`
👥 **Total Users:** `{total_users}`
📅 **Member Since:** `{user_stats.get('join_date', 'Unknown')}`

🔥 **Keep downloading and enjoy!**
"""
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back", callback_data="back_to_start")
    ]])
    
    if hasattr(context, 'edit_message_text'):
        await context.edit_message_text(stats_text, reply_markup=keyboard)
    else:
        await context.reply_text(stats_text, reply_markup=keyboard)

# Check subscription callback
@app.on_callback_query(filters.regex("check_sub"))
async def check_sub_callback(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name
    
    print(f"Checking subscription for {user_id}")
    
    # Skip for owner
    if user_id == OWNER_ID:
        await callback.edit_message_text(
            "✅ **Welcome Owner!**\n\n"
            "You have full access to the bot! 🎉\n"
            "Send me a Terabox link to get started.",
            message_effect_id=FIRE_EFFECT
        )
        return
    
    if await check_force_sub(user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
            [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/NY_BOTS")]
        ])
        
        await callback.edit_message_text(
            f"✅ **Subscription Verified!**\n\n"
            f"Welcome **{first_name}**! 🎉\n\n"
            f"🔥 **Terabox Download Bot is ready!**\n\n"
            f"Send me a Terabox link to download files instantly!\n\n"
            f"**Credits:** @NY_BOTS",
            reply_markup=keyboard,
            message_effect_id=FIRE_EFFECT
        )
        
        # Log successful subscription
        try:
            await client.send_message(
                OWNER_ID,
                f"✅ **User Subscribed**\n\n"
                f"👤 **Name:** {first_name}\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"📝 **Username:** @{callback.from_user.username if callback.from_user.username else 'None'}\n"
                f"🕒 **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
        except Exception as e:
            print(f"Error sending subscription log: {e}")
    else:
        await callback.answer("❌ You haven't joined the channel yet! Please join and try again.", show_alert=True)

# Back to start callback
@app.on_callback_query(filters.regex("back_to_start"))
async def back_to_start_callback(client, callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/NY_BOTS")]
    ])
    
    await callback.edit_message_text(
        f"🔥 **Terabox Download Bot** 🔥\n\n"
        f"👋 Welcome back, **{callback.from_user.first_name}**!\n\n"
        f"Send me a Terabox link to download files instantly!\n\n"
        f"**Credits:** @NY_BOTS",
        reply_markup=keyboard
    )

# Main download handler
@app.on_message(filters.text & filters.private)
async def handle_terabox_link(client, message: Message):
    user_id = message.from_user.id
    
    # Skip commands
    if message.text.startswith('/'):
        return
    
    print(f"Received message from {user_id}: {message.text[:50]}...")
    
    # Check force subscription (skip for owner)
    if user_id != OWNER_ID:
        if not await check_force_sub(user_id):
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL[1:]}")
            ]])
            await message.reply_text(
                "🔒 Please join our channel first to use this bot!",
                reply_markup=keyboard
            )
            return
    
    text = message.text
    
    # Check if message contains terabox link
    terabox_domains = ['terabox.com', '1024terabox.com', '4funbox.com', 'mirrobox.com', 'nephobox.com', 'momerybox.com', 'teraboxapp.com']
    
    if not any(domain in text for domain in terabox_domains):
        await message.reply_text(
            "❌ **Invalid Link!**\n\n"
            "Please send a valid Terabox link.\n\n"
            "**Supported domains:**\n"
            "• terabox.com\n• 1024terabox.com\n• 4funbox.com\n• mirrobox.com\n• nephobox.com\n• momerybox.com\n• teraboxapp.com"
        )
        return
    
    # Show processing message
    processing_msg = await message.reply_text(
        "🔄 **Processing your request...**\n\n"
        "⏳ Please wait while I fetch file information...",
        message_effect_id=FIRE_EFFECT
    )
    
    try:
        # Get file information from API
        api_url = f"{TERABOX_API}{quote(text)}"
        print(f"API URL: {api_url}")
        
        response = requests.get(api_url, timeout=30)
        print(f"API Response Status: {response.status_code}")
        
        data = response.json()
        print(f"API Response: {data}")
        
        if "error" in data:
            await processing_msg.edit_text(
                f"❌ **Error occurred!**\n\n"
                f"Error: {data['error']}\n\n"
                f"Please try again with a valid link."
            )
            return
        
        # Extract file information
        file_name = data.get('file_name', 'Unknown')
        file_size = data.get('file_size', 'Unknown')
        size_bytes = data.get('size_bytes', 0)
        download_link = data.get('proxy_url', '')
        thumbnail = data.get('thumbnail', '')
        
        if not download_link:
            await processing_msg.edit_text(
                "❌ **No download link found!**\n\n"
                "Please try again with a different link."
            )
            return
        
        # Create download keyboard
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download File", callback_data=f"download_{message.id}")],
            [InlineKeyboardButton("📊 File Info", callback_data=f"info_{message.id}")],
            [InlineKeyboardButton("🔄 Refresh Link", callback_data=f"refresh_{message.id}")]
        ])
        
        # Store download data temporarily
        download_data = {
            'file_name': file_name,
            'file_size': file_size,
            'size_bytes': size_bytes,
            'download_link': download_link,
            'thumbnail': thumbnail,
            'original_link': text,
            'user_id': user_id
        }
        
        # Store in a simple way (you can use Redis for production)
        app.download_data = getattr(app, 'download_data', {})
        app.download_data[message.id] = download_data
        
        file_info = f"""
📁 **File Ready for Download!**

📋 **Name:** `{file_name}`
📦 **Size:** `{file_size}`
🔗 **Source:** Terabox
⚡ **Status:** Ready

🎯 **Click Download to get your file!**

**Credits:** @NY_BOTS
"""
        
        await processing_msg.edit_text(file_info, reply_markup=keyboard)
        
        # Log to owner if LOG_CHANNEL is set
        try:
            if LOG_CHANNEL:
                await client.send_message(
                    LOG_CHANNEL,
                    f"📥 **New Download Request**\n\n"
                    f"👤 **User:** {message.from_user.mention}\n"
                    f"📁 **File:** `{file_name}`\n"
                    f"📦 **Size:** `{file_size}`\n"
                    f"🕒 **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                )
        except Exception as e:
            print(f"Error sending log: {e}")
        
    except Exception as e:
        print(f"Error processing link: {e}")
        await processing_msg.edit_text(
            f"❌ **Error occurred!**\n\n"
            f"Error: {str(e)}\n\n"
            f"Please try again later or contact support."
        )

# Download callback handler
@app.on_callback_query(filters.regex(r"download_(\d+)"))
async def download_callback(client, callback: CallbackQuery):
    message_id = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    
    # Get download data
    download_data = getattr(app, 'download_data', {}).get(message_id)
    if not download_data:
        await callback.answer("❌ Download data not found! Please try again.", show_alert=True)
        return
    
    if download_data['user_id'] != user_id:
        await callback.answer("❌ This download is not for you!", show_alert=True)
        return
    
    await callback.answer("🔄 Starting download...", show_alert=False)
    
    # Edit message to show download progress
    progress_msg = await callback.edit_message_text(
        "🔄 **Preparing Download...**\n\n"
        f"📁 **File:** `{download_data['file_name']}`\n"
        f"📦 **Size:** `{download_data['file_size']}`\n\n"
        f"⏳ **Status:** Initializing...",
        message_effect_id=FIRE_EFFECT
    )
    
    try:
        file_name = download_data['file_name']
        download_link = download_data['download_link']
        size_bytes = download_data['size_bytes']
        
        # Download progress callback
        last_update = 0
        async def progress_callback(downloaded, total, percentage):
            nonlocal last_update
            current_time = time.time()
            
            if current_time - last_update >= 2:  # Update every 2 seconds
                progress_bar = get_progress_bar(percentage)
                speed = downloaded / (current_time - start_time) if current_time > start_time else 0
                
                progress_text = f"""
📥 **Downloading...**

📁 **File:** `{file_name}`
📦 **Size:** `{get_size(total)}`

📊 **Progress:**
{progress_bar}

📈 **Downloaded:** `{get_size(downloaded)}`
⚡ **Speed:** `{get_size(speed)}/s`
⏱️ **ETA:** `{int((total - downloaded) / speed) if speed > 0 else 0}s`

🔥 **Please wait...**
"""
                
                try:
                    await progress_msg.edit_text(progress_text)
                    last_update = current_time
                except:
                    pass
        
        # Start download
        start_time = time.time()
        await download_file(download_link, file_name, progress_callback)
        
        # Upload progress callback
        async def upload_progress(current, total):
            percentage = (current / total) * 100
            progress_bar = get_progress_bar(percentage)
            speed = current / (time.time() - upload_start_time) if time.time() > upload_start_time else 0
            
            upload_text = f"""
📤 **Uploading to Telegram...**

📁 **File:** `{file_name}`
📦 **Size:** `{get_size(total)}`

📊 **Progress:**
{progress_bar}

📈 **Uploaded:** `{get_size(current)}`
⚡ **Speed:** `{get_size(speed)}/s`
⏱️ **ETA:** `{int((total - current) / speed) if speed > 0 else 0}s`

🚀 **Almost done...**
"""
            
            try:
                await progress_msg.edit_text(upload_text)
            except:
                pass
        
        # Upload file
        upload_start_time = time.time()
        await progress_msg.edit_text(
            f"📤 **Uploading to Telegram...**\n\n"
            f"📁 **File:** `{file_name}`\n"
            f"📦 **Size:** `{download_data['file_size']}`\n\n"
            f"🚀 **Please wait...**"
        )
        
        # Send file
        await client.send_document(
            chat_id=callback.message.chat.id,
            document=file_name,
            caption=f"📁 **{file_name}**\n\n"
                   f"📦 **Size:** `{download_data['file_size']}`\n"
                   f"⏱️ **Downloaded in:** `{int(time.time() - start_time)}s`\n\n"
                   f"🔥 **Downloaded by:** {callback.from_user.mention}\n"
                   f"**Credits:** @NY_BOTS",
            progress=upload_progress,
            message_effect_id=FIRE_EFFECT
        )
        
        # Clean up
        try:
            os.remove(file_name)
        except:
            pass
        
        # Update user stats
        await update_user_stats(user_id, size_bytes)
        
        # Success message
        await progress_msg.edit_text(
            f"✅ **Download Complete!**\n\n"
            f"📁 **File:** `{file_name}`\n"
            f"📦 **Size:** `{download_data['file_size']}`\n"
            f"⏱️ **Time:** `{int(time.time() - start_time)}s`\n\n"
            f"🎉 **File sent successfully!**\n"
            f"**Credits:** @NY_BOTS"
        )
        
    except Exception as e:
        await progress_msg.edit_text(
            f"❌ **Download Failed!**\n\n"
            f"Error: {str(e)}\n\n"
            f"Please try again or contact support."
        )
        
        # Clean up on error
        try:
            if os.path.exists(file_name):
                os.remove(file_name)
        except:
            pass

# File info callback
@app.on_callback_query(filters.regex(r"info_(\d+)"))
async def info_callback(client, callback: CallbackQuery):
    message_id = int(callback.data.split('_')[1])
    
    download_data = getattr(app, 'download_data', {}).get(message_id)
    if not download_data:
        await callback.answer("❌ File info not found!", show_alert=True)
        return
    
    info_text = f"""
📋 **Detailed File Information**

📁 **Name:** `{download_data['file_name']}`
📦 **Size:** `{download_data['file_size']}`
🔢 **Bytes:** `{download_data['size_bytes']:,}`
🔗 **Source:** Terabox
⚡ **Status:** Ready for download

🌐 **Original Link:**
`{download_data['original_link']}`

🎯 **Ready to download!**
"""
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back", callback_data=f"back_{message_id}")
    ]])
    
    await callback.edit_message_text(info_text, reply_markup=keyboard)

# Refresh link callback
@app.on_callback_query(filters.regex(r"refresh_(\d+)"))
async def refresh_callback(client, callback: CallbackQuery):
    message_id = int(callback.data.split('_')[1])
    
    download_data = getattr(app, 'download_data', {}).get(message_id)
    if not download_data:
        await callback.answer("❌ File data not found!", show_alert=True)
        return
    
    await callback.answer("🔄 Refreshing link...", show_alert=False)
    
    try:
        # Refresh the download link
        api_url = f"{TERABOX_API}{quote(download_data['original_link'])}"
        response = requests.get(api_url, timeout=30)
        data = response.json()
        
        if "error" in data:
            await callback.answer(f"❌ Error: {data['error']}", show_alert=True)
            return
        
        # Update download data
        download_data['download_link'] = data['proxy_url']
        app.download_data[message_id] = download_data
        
        await callback.answer("✅ Link refreshed successfully!", show_alert=True)
        
    except Exception as e:
        await callback.answer(f"❌ Error refreshing link: {str(e)}", show_alert=True)

# Back callback
@app.on_callback_query(filters.regex(r"back_(\d+)"))
async def back_callback(client, callback: CallbackQuery):
    message_id = int(callback.data.split('_')[1])
    
    download_data = getattr(app, 'download_data', {}).get(message_id)
    if not download_data:
        await callback.answer("❌ File data not found!", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download File", callback_data=f"download_{message_id}")],
        [InlineKeyboardButton("📊 File Info", callback_data=f"info_{message_id}")],
        [InlineKeyboardButton("🔄 Refresh Link", callback_data=f"refresh_{message_id}")]
    ])
    
    file_info = f"""
📁 **File Ready for Download!**

📋 **Name:** `{download_data['file_name']}`
📦 **Size:** `{download_data['file_size']}`
🔗 **Source:** Terabox
⚡ **Status:** Ready

🎯 **Click Download to get your file!**

**Credits:** @NY_BOTS
"""
    
    await callback.edit_message_text(file_info, reply_markup=keyboard)

# Run the bot
if __name__ == "__main__":
    print("🔥 Terabox Download Bot Starting...")
    print("Credits: @NY_BOTS")
    print(f"Owner ID: {OWNER_ID}")
    print(f"Force Sub Channel: {FORCE_SUB_CHANNEL}")
    print(f"Log Channel: {LOG_CHANNEL}")
    
    # Test MongoDB connection
    try:
        mongo_client.server_info()
        print("✅ MongoDB connected successfully!")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
    
    print("Bot is running... Press Ctrl+C to stop")
    app.run()
