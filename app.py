# app.py
import os
import requests
from flask import Flask, redirect, request, session, jsonify
from flask_cors import CORS
from flask_session import Session
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=[os.getenv('FRONTEND_URL')])
app.secret_key = os.getenv('SESSION_SECRET_KEY')

# Configure server-side session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
Session(app)

# Constants
DISCORD_OAUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_API_BASE_URL = "https://discord.com/api"
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI')
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
REQUIRED_GUILD_ID = os.getenv('REQUIRED_GUILD_ID')
REQUIRED_ROLE_ID = os.getenv('REQUIRED_ROLE_ID')

# Validate Environment Variables
if not all([CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, BOT_TOKEN, REQUIRED_GUILD_ID, REQUIRED_ROLE_ID, os.getenv('SESSION_SECRET_KEY'), os.getenv('FRONTEND_URL')]):
    logging.error("One or more environment variables are missing. Please check your .env file.")
    exit(1)

@app.route('/auth/discord')
def auth_discord():
    scope = "identify guilds guilds.members.read"
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": scope,
        "prompt": "consent"
    }
    url = requests.Request('GET', DISCORD_OAUTH_URL, params=params).prepare().url
    logging.debug(f"Redirecting to Discord OAuth URL: {url}")
    return redirect(url)

@app.route('/auth/discord/callback')
def auth_discord_callback():
    code = request.args.get('code')
    if not code:
        logging.error("No authorization code provided in the callback URL.")
        return "No code provided", 400

    # Debugging: Log received authorization code
    logging.debug(f"Received authorization code: {code}")

    # Exchange code for access token
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": "identify guilds guilds.members.read"
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # Debugging: Log the token exchange request data
    logging.debug(f"Requesting token with data: {data}")

    token_response = requests.post(DISCORD_TOKEN_URL, data=data, headers=headers)
    
    # Debugging: Log the raw token response
    logging.debug(f"Token response: {token_response.text}")

    if token_response.status_code != 200:
        logging.error(f"Failed to obtain access token: {token_response.text}")
        return f"Failed to obtain access token: {token_response.text}", 400

    token_json = token_response.json()
    access_token = token_json.get('access_token')

    if not access_token:
        logging.error("No access token found in the token exchange response.")
        return "No access token found in response", 400

    logging.debug(f"Obtained access token: {access_token}")

    # Fetch user information
    user_response = requests.get(
        f"{DISCORD_API_BASE_URL}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    logging.debug(f"User info response: {user_response.text}")

    if user_response.status_code != 200:
        logging.error(f"Failed to fetch user info: {user_response.text}")
        return f"Failed to fetch user info: {user_response.text}", 400
    user_json = user_response.json()
    logging.debug(f"Authenticated user: {user_json['username']}#{user_json['discriminator']}")

    # Fetch user's guilds
    guilds_response = requests.get(
        f"{DISCORD_API_BASE_URL}/users/@me/guilds",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    logging.debug(f"Guilds response: {guilds_response.text}")

    if guilds_response.status_code != 200:
        logging.error(f"Failed to fetch user guilds: {guilds_response.text}")
        return f"Failed to fetch user guilds: {guilds_response.text}", 400
    guilds = guilds_response.json()

    # Check if user is in the required guild
    is_in_guild = any(str(guild['id']) == REQUIRED_GUILD_ID for guild in guilds)
    logging.debug(f"User in required guild: {is_in_guild}")

    if not is_in_guild:
        logging.error("User is not a member of the required guild.")
        return "You are not a member of the required Discord server.", 403

    # Fetch user's roles in the required guild
    member_response = requests.get(
        f"{DISCORD_API_BASE_URL}/guilds/{REQUIRED_GUILD_ID}/members/{user_json['id']}",
        headers={"Authorization": f"Bot {BOT_TOKEN}"}
    )
    
    logging.debug(f"Member response: {member_response.text}")

    if member_response.status_code != 200:
        logging.error(f"Failed to fetch guild member info: {member_response.text}")
        return f"Failed to fetch guild member info: {member_response.text}", 400
    member_json = member_response.json()
    user_roles = member_json.get('roles', [])
    logging.debug(f"User roles in guild {REQUIRED_GUILD_ID}: {user_roles}")

    # Check if user has the required role by ID
    has_required_role = REQUIRED_ROLE_ID in user_roles
    logging.debug(f"User has required role: {has_required_role}")

    if not has_required_role:
        logging.error("User does not have the required role.")
        return "You do not have the required role to access this application.", 403

    # Store user info in session
    session['user'] = {
        "id": user_json['id'],
        "username": user_json['username'],
        "discriminator": user_json['discriminator'],
        "avatar": user_json['avatar']
    }
    logging.debug("User authenticated and session stored.")

    # Redirect to frontend
    return redirect(os.getenv('FRONTEND_URL'))

@app.route('/auth/user', methods=['GET'])
def get_current_user():
    user = session.get('user')
    if user:
        return jsonify({"authenticated": True, "user": user})
    else:
        return jsonify({"authenticated": False, "user": None})

@app.route('/auth/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({"message": "Logged out successfully."}), 200

if __name__ == '__main__':
    app.run(debug=True)
