import discord
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput
import sqlite3
import os
from datetime import datetime
import threading
from flask import Flask

# Flask setup
app = Flask(__name__)

@app.route('/')
def home():
    return "Discord Bot is running!"

@app.route('/health')
def health():
    return {"status": "ok", "bot": "online" if client.is_ready() else "offline"}

def run_flask():
    """Run Flask in a separate thread"""
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required for presence updates
intents.presences = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

NOTIFICATION_CHANNEL_ID = int(os.getenv("NOTIFICATION_CHANNEL_ID")) # Replace with your channel ID
USERS_TO_MONITOR = [
    788903923922632704,
    1190979849926496276# User ID 2
    # Add more user IDs here
]

# Database setup
DB_FILE = "requests.db"

def init_db():
    """Initialize the database"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT,
                  username TEXT,
                  message TEXT,
                  link TEXT,
                  timestamp TEXT,
                  viewed INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def add_request(user_id, username, message, link):
    """Add a new request to the database"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO requests (user_id, username, message, link, timestamp) VALUES (?, ?, ?, ?, ?)",
              (str(user_id), username, message, link, timestamp))
    conn.commit()
    conn.close()

def get_request_by_index(index):
    """Get a request by its index (0-based)"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM requests ORDER BY id ASC LIMIT 1 OFFSET ?", (index,))
    result = c.fetchone()
    conn.close()
    return result

def get_total_requests():
    """Get total number of requests"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM requests")
    count = c.fetchone()[0]
    conn.close()
    return count

def mark_as_viewed(request_id):
    """Mark a request as viewed"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE requests SET viewed = 1 WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()

# Modal for submitting requests
class RequestModal(Modal, title="Submit a Reaction Request"):
    title_input = TextInput(
        label="Title/Message",
        placeholder="Enter a title or message for your request",
        max_length=200,
        required=True
    )
    
    link_input = TextInput(
        label="Link",
        placeholder="Enter the link (URL)",
        max_length=500,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        username = str(interaction.user)
        message = self.title_input.value
        link = self.link_input.value
        
        # Add to database
        add_request(user_id, username, message, link)
        
        await interaction.response.send_message(
            f"✅ Your request has been submitted!\n**Title:** {message}\n**Link:** {link}",
            ephemeral=True
        )

# Button view for users to submit requests
class SubmitRequestView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Submit Request", style=discord.ButtonStyle.primary, custom_id="submit_request")
    async def submit_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RequestModal())

# View for streamer to navigate requests
class NavigateRequestsView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.current_index = 0
    
    def create_embed(self, request_data):
        """Create an embed for displaying a request"""
        if request_data is None:
            embed = discord.Embed(
                title="📭 No Requests Available",
                description="No more requests at the moment. Click Next to check for new ones!",
                color=discord.Color.orange()
            )
            return embed
        
        req_id, user_id, username, message, link, timestamp, viewed = request_data
        
        embed = discord.Embed(
            title=f"🎬 Request #{req_id}",
            description=f"**Title:** {message}\n**Link:** {link}",
            color=discord.Color.green() if not viewed else discord.Color.greyple(),
            timestamp=datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        )
        embed.add_field(name="Submitted by", value=username, inline=True)
        embed.add_field(name="Status", value="✅ Viewed" if viewed else "🆕 New", inline=True)
        embed.set_footer(text=f"Request {self.current_index + 1} of {get_total_requests()}")
        
        return embed
    
    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary, custom_id="prev_request")
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if self.current_index > 0:
            self.current_index -= 1
        
        request = get_request_by_index(self.current_index)
        
        # Mark as viewed if it exists
        if request:
            mark_as_viewed(request[0])
        
        embed = self.create_embed(request)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="🔄", style=discord.ButtonStyle.success, custom_id="refresh_request")
    async def refresh_button(self, interaction: discord.Interaction, button: Button):
        """Refresh the current request view"""
        request = get_request_by_index(self.current_index)
        
        # Mark as viewed if it exists
        if request:
            mark_as_viewed(request[0])
        
        embed = self.create_embed(request)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.primary, custom_id="next_request")
    async def next_button(self, interaction: discord.Interaction, button: Button):
        total = get_total_requests()
        
        # If we're at "no requests" screen, check if new ones exist
        if self.current_index >= total and total > 0:
            self.current_index = total - 1
        elif self.current_index < total:
            self.current_index += 1
        
        request = get_request_by_index(self.current_index)
        
        # Mark as viewed if it exists
        if request:
            mark_as_viewed(request[0])
        
        embed = self.create_embed(request)
        
        await interaction.response.edit_message(embed=embed, view=self)

# Setup command - creates the submission interface
@tree.command(name="setup_submit", description="Setup the request submission interface")
@app_commands.checks.has_permissions(administrator=True)
async def setup_submit(interaction: discord.Interaction):
    embed = discord.Embed(
        title="# 🎬 SUBMIT YOUR REACTION REQUESTS HERE",
        description="Click the button below to send your reaction!",
        color=discord.Color.blue()
    )
    
    view = SubmitRequestView()
    await interaction.response.send_message(embed=embed, view=view)

# Setup command - creates the streamer navigation interface
@tree.command(name="setup_viewer", description="Setup the request viewer interface (Streamer only)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_viewer(interaction: discord.Interaction):
    view = NavigateRequestsView()
    
    total = get_total_requests()
    
    if total == 0:
        embed = discord.Embed(
            title="📭 No Requests Available",
            description="No requests have been submitted yet.",
            color=discord.Color.orange()
        )
    else:
        request = get_request_by_index(0)
        embed = view.create_embed(request)
        mark_as_viewed(request[0])
    
    await interaction.response.send_message(embed=embed, view=view)

# Clear all requests command (optional - for testing/management)
@tree.command(name="clear_requests", description="Clear all requests from the database")
@app_commands.checks.has_permissions(administrator=True)
async def clear_requests(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM requests")
    conn.commit()
    conn.close()
    
    await interaction.response.send_message("🗑️ All requests have been cleared!", ephemeral=True)

def add_tracked_user(user_id):
    """Add a user to track for online status"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS tracked_users (user_id TEXT PRIMARY KEY)")
    c.execute("INSERT OR IGNORE INTO tracked_users (user_id) VALUES (?)", (str(user_id),))
    conn.commit()
    conn.close()

def remove_tracked_user(user_id):
    """Remove a user from tracking"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM tracked_users WHERE user_id = ?", (str(user_id),))
    conn.commit()
    conn.close()

def get_tracked_users():
    """Get list of tracked user IDs"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS tracked_users (user_id TEXT PRIMARY KEY)")
    c.execute("SELECT user_id FROM tracked_users")
    results = c.fetchall()
    conn.close()
    return [int(row[0]) for row in results]

def is_user_tracked(user_id):
    """Check if a user is being tracked"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM tracked_users WHERE user_id = ?", (str(user_id),))
    result = c.fetchone()
    conn.close()
    return result is not None

# Event listener for presence updates
@client.event
async def on_presence_update(before, after):
    """Triggered when a user's status changes"""
    # Check if user is tracked
    if not is_user_tracked(after.id):
        return
    
    # Check if they went from offline/invisible to online
    before_offline = before.status in [discord.Status.offline, discord.Status.invisible]
    after_online = after.status == discord.Status.online
    
    if before_offline and after_online:
        channel = client.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="🟢 User Online",
                description=f"{after.mention} is now online!",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=after.display_avatar.url)
            await channel.send(embed=embed)

# Commands to manage tracked users
@tree.command(name="track_user", description="Start tracking when a user comes online")
@app_commands.checks.has_permissions(administrator=True)
async def track_user(interaction: discord.Interaction, user: discord.Member):
    add_tracked_user(user.id)
    await interaction.response.send_message(
        f"✅ Now tracking {user.mention} for online status!",
        ephemeral=True
    )

@tree.command(name="untrack_user", description="Stop tracking a user's online status")
@app_commands.checks.has_permissions(administrator=True)
async def untrack_user(interaction: discord.Interaction, user: discord.Member):
    remove_tracked_user(user.id)
    await interaction.response.send_message(
        f"❌ Stopped tracking {user.mention}",
        ephemeral=True
    )

@tree.command(name="list_tracked", description="List all tracked users")
@app_commands.checks.has_permissions(administrator=True)
async def list_tracked(interaction: discord.Interaction):
    tracked_ids = get_tracked_users()
    
    if not tracked_ids:
        await interaction.response.send_message("No users are being tracked.", ephemeral=True)
        return
    
    users = []
    for user_id in tracked_ids:
        user = interaction.guild.get_member(user_id)
        if user:
            users.append(f"• {user.mention} ({user.name})")
    
    embed = discord.Embed(
        title="👁️ Tracked Users",
        description="\n".join(users) if users else "No tracked users found in this server.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.event
async def on_ready():
    init_db()
    
    # Add persistent views
    client.add_view(SubmitRequestView())
    client.add_view(NavigateRequestsView())
    
    await tree.sync()
    print(f"Bot is ready! Logged in as {client.user}")

if __name__ == "__main__":
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("Flask server started")
    
    # Run the Discord bot
    TOKEN = os.getenv("DISCORD_TOKEN")
    client.run(TOKEN)
