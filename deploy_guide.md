# Solana Hunter - AWS Deployment Guide

This guide details how to deploy the **Solana Hunter** system (Scraper + Matcher + Monitor Bot) on an AWS EC2 instance for 24/7 operation.

## 1. Prerequisites

*   **AWS Account**: You need an active AWS account.
*   **EC2 Instance**:
    *   **OS**: Ubuntu Server 22.04 LTS (Recommended) or Debian.
    *   **Instance Type**: `c5.large` or `c5.xlarge` (Compute Optimized) is recommended for high-speed matching. `t3.medium` is the absolute minimum.
    *   **Storage**: At least 20GB gp3 SSD.
*   **SSH Access**: Ensure you have the `.pem` key file to SSH into your server.

## 2. System Setup

Connect to your instance:
```bash
ssh -i /path/to/your-key.pem ubuntu@<YOUR_SERVER_IP>
```

Update the system and install essential tools:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git build-essential curl screen htop
```

Install Rust (for the Matcher):
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
# Press 1 to proceed with default installation
source "$HOME/.cargo/env"
```

## 3. Project Setup

### 3.1. Upload Code
You can upload your code using `scp` from your local machine:
```bash
# Run this from your LOCAL machine
scp -i /Users/danielius/.ssh/iPhone.pem -r /Users/danielius/Documents/solana_hunter ubuntu@13.48.131.108:~/solana_hunter
```
*Alternatively, if you use GitHub, you can `git clone` your repository.*

### 3.2. Python Environment
Set up the Python environment for the Scraper and Bot:
```bash
cd ~/solana_hunter
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install aiohttp python-telegram-bot
```

### 3.3. Build Rust Matcher
Compile the high-performance Rust matcher:
```bash
cd solana-matcher
cargo build --release
cd ..
```
*This may take a few minutes.*

### 3.4. Permissions
Ensure your scripts are executable:
```bash
chmod +x start.sh stop.sh
```

## 4. Configuration

### 4.1. Bot Configuration
Open `monitor_bot.py` and ensure your `TOKEN` and `ALLOWED_USER_ID` are correct.
```bash
nano monitor_bot.py
```
*Press `Ctrl+X`, `Y`, `Enter` to save and exit.*

### 4.2. Scraper Configuration
Open `fast_scraper.py` to adjust `CONCURRENCY` if needed (default is 5).
```bash
nano fast_scraper.py
```

## 5. Running the System

We will use `screen` to keep the session alive even if you disconnect.

1.  **Start a new screen session**:
    ```bash
    screen -S hunter
    ```

2.  **Activate Python environment** (if not already active):
    ```bash
    source venv/bin/activate
    ```

3.  **Launch the System**:
    ```bash
    ./start.sh
    ```
    You should see output indicating the Scraper, Matcher, and Bot have started.

4.  **Detach**:
    Press `Ctrl+A`, then `D` to detach from the screen session. The system will keep running in the background.

## 6. Monitoring & Maintenance

### Check Status
*   **Telegram**: Use the `/status` command in your bot.
*   **Logs**:
    ```bash
    tail -f scraper.log
    tail -f bot.log
    tail -f solana-matcher/matcher.log
    ```

### Stop System
To stop all processes:
```bash
./stop.sh
```

### Re-attach to Screen
To go back to your running session console:
```bash
screen -r hunter
```

### Updates
If you change code locally, upload the new files, then:
1.  `./stop.sh`
2.  Re-build Rust if needed (`cd solana-matcher && cargo build --release && cd ..`)
3.  `./start.sh`

## 7. Troubleshooting

*   **"Block not available"**: The scraper handles this, but if it happens constantly, check your internet connection or RPC URL.
*   **High CPU Usage**: This is normal for the Rust matcher. It uses all available cores.
*   **Bot not responding**: Check `bot.log` for errors. Ensure the token is correct.

---
**Security Note**: Never share your `targets.txt` or `found.txt` publicly.
