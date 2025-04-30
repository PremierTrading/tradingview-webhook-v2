# TradingView Webhook Service V2

This repo contains the complete backend as deployed on Render, now version 2.

Includes:
- Database initialization (`init_db.py`)
- User creation (`create_users_with_custom_api_keys.py`)
- Flask app (`app.py`) with endpoints:
  - `GET /health`
  - `POST /register`
  - `POST /login`
  - `POST /webhook`
  - `GET /download-backup`

## Setup & Deployment

1. Clone this repo:
   ```bash
   git clone https://github.com/PremierTrading/tradingview-webhook-v2.git
   cd tradingview-webhook-v2