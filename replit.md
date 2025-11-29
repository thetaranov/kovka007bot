# Telegram Bot for Canopy/Awning Orders

## Overview
This is a Telegram bot application designed to help customers create and order custom canopies/awnings. The bot provides a link to an external design tool and collects customer contact information, then notifies administrators about new orders.

**Current Status**: Successfully configured and running in Replit environment.

**Last Updated**: November 29, 2025

## Project Architecture

### Technology Stack
- **Language**: Python 3.9
- **Bot Framework**: python-telegram-bot 13.7
- **Web Framework**: Flask 2.3.3 (for health check endpoints)
- **Deployment**: Configured for Replit environment

### Project Structure
```
.
├── bot.py              # Main bot application
├── requirements.txt    # Python dependencies
├── runtime.txt        # Python version specification
├── Procfile           # Process configuration (Heroku-style)
└── replit.md          # This documentation file
```

### Key Features
1. `/start` command - Greets users and provides links to:
   - External design tool (https://kovka007.vercel.app)
   - Direct contact with manager
2. Contact handler - Collects customer phone numbers
3. `/admin` command - Shows order statistics to authorized admins
4. Flask health check endpoints at `/` and `/health`

### Architecture Details
- **Bot Mode**: Polling (long-polling for updates from Telegram)
- **Storage**: In-memory storage for orders (non-persistent)
- **Flask Server**: Runs in a separate daemon thread on port 10000
- **Admin Notifications**: Sends messages to configured admin IDs when new contacts are received

## Environment Configuration

### Required Secrets
The following secrets are configured in Replit:
- **BOT_TOKEN**: Telegram bot token from @BotFather
- **ADMIN_IDS**: JSON array of Telegram user IDs for admin access (e.g., `[123456789]`)

### Workflow Configuration
- **Name**: Run Telegram Bot
- **Command**: `python bot.py`
- **Output**: Console logs
- **Status**: Running continuously

## How to Use

### For End Users
1. Start a chat with the bot on Telegram
2. Send `/start` to begin
3. Click the button to access the canopy design tool
4. Share contact information when prompted
5. Wait for manager to contact you

### For Administrators
1. Send `/admin` command to view order statistics
2. Receive automatic notifications when customers share their contact info
3. Follow up with customers using the provided phone numbers

## Dependencies
- `python-telegram-bot==13.7` - Telegram bot API wrapper
- `flask==2.3.3` - Web framework for health endpoints

## Important Notes
- Orders are stored in memory and will be lost on restart
- The bot uses polling mode (not webhooks)
- Flask server on port 10000 provides health check capability
- Admin IDs must be valid Telegram user IDs

## External Links
- Design Tool: https://kovka007.vercel.app
- Manager Contact: https://t.me/thetaranov

## Recent Changes
- **2025-11-29**: Initial import and setup in Replit environment
  - Installed Python 3.9 and dependencies
  - Configured environment secrets (BOT_TOKEN, ADMIN_IDS)
  - Set up workflow for continuous bot operation
  - Bot successfully running and connected to Telegram
