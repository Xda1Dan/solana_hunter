import asyncio
import aiohttp
import json
import os
import time
import logging
from collections import deque

# --- Configuration ---
RPC_URL = "https://api.mainnet-beta.solana.com"  # Replace with your premium RPC if you have one
MAX_BATCH_SIZE = 50  # Number of blocks to fetch in one HTTP request
CONCURRENCY = 5      # Number of concurrent batch requests
MIN_BALANCE_SOL = 1.0
TARGETS_FILE = "targets.txt"
STATS_FILE = "scraper_stats.json"

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global State ---
stats = {
    "started_at": time.time(),
    "blocks_processed": 0,
    "transactions_scanned": 0,
    "signers_checked": 0,
    "high_value_found": 0,
    "current_slot": 0,
    "speed_blocks_per_sec": 0.0
}
existing_targets = set()

def load_targets():
    if os.path.exists(TARGETS_FILE):
        with open(TARGETS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    existing_targets.add(line)
    logger.info(f"Loaded {len(existing_targets)} existing targets.")

def save_target(address):
    if address not in existing_targets:
        with open(TARGETS_FILE, "a") as f:
            f.write(f"{address}\n")
        existing_targets.add(address)
        stats["high_value_found"] += 1
        logger.info(f"FOUND HIGH VALUE: {address}")

def update_stats():
    elapsed = time.time() - stats["started_at"]
    if elapsed > 0:
        stats["speed_blocks_per_sec"] = stats["blocks_processed"] / elapsed
    
    # Write atomic dump
    tmp_file = STATS_FILE + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(stats, f)
    os.rename(tmp_file, STATS_FILE)

async def get_slot(session):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSlot",
        "params": [{"commitment": "confirmed"}]
    }
    try:
        async with session.post(RPC_URL, json=payload) as resp:
            data = await resp.json()
            return data.get("result")
    except Exception as e:
        logger.error(f"Error getting slot: {e}")
        return None

async def get_blocks_batch(session, start_slot, count):
    """
    Fetches a range of blocks using JSON-RPC batching.
    Note: 'getBlocks' (plural) returns a list of slots. We want the actual block data.
    So we construct a batch of 'getBlock' calls.
    """
    batch_payload = []
    slots_requested = []
    
    for i in range(count):
        slot = start_slot + i
        slots_requested.append(slot)
        batch_payload.append({
            "jsonrpc": "2.0",
            "id": i,
            "method": "getBlock",
            "params": [
                slot,
                {
                    "encoding": "jsonParsed",
                    "transactionDetails": "full",
                    "rewards": False,
                    "commitment": "confirmed",
                    "maxSupportedTransactionVersion": 0
                }
            ]
        })

    try:
        async with session.post(RPC_URL, json=batch_payload) as resp:
            if resp.status == 429:
                logger.warning("Rate limited (429). Cooling down...")
                await asyncio.sleep(2)
                return []
            
            results = await resp.json()
            
            # Handle case where result is not a list (single error)
            if not isinstance(results, list):
                return []
            
            blocks = []
            for res in results:
                if "result" in res and res["result"]:
                    blocks.append(res["result"])
            return blocks

    except Exception as e:
        logger.error(f"Batch fetch error: {e}")
        return []

async def check_balances(session, addresses):
    """
    Checks balances for a list of addresses using getMultipleAccounts.
    """
    if not addresses:
        return []
    
    # Split into chunks of 100 (limit for getMultipleAccounts)
    chunks = [addresses[i:i + 100] for i in range(0, len(addresses), 100)]
    high_value = []

    for chunk in chunks:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getMultipleAccounts",
            "params": [chunk, {"encoding": "jsonParsed"}]
        }
        try:
            async with session.post(RPC_URL, json=payload) as resp:
                data = await resp.json()
                if "result" in data and "value" in data["result"]:
                    for i, account_info in enumerate(data["result"]["value"]):
                        if account_info:
                            lamports = account_info.get("lamports", 0)
                            sol_balance = lamports / 1e9
                            if sol_balance > MIN_BALANCE_SOL:
                                high_value.append(chunk[i])
        except Exception as e:
            logger.error(f"Balance check error: {e}")
    
    return high_value

async def worker(name, queue, session):
    logger.info(f"Worker {name} started.")
    while True:
        try:
            # Get a batch task from the queue
            start_slot, count = await queue.get()
            
            # Fetch blocks
            blocks = await get_blocks_batch(session, start_slot, count)
            
            # Process blocks
            candidates = set()
            tx_count = 0
            
            for block in blocks:
                if "transactions" in block:
                    tx_count += len(block["transactions"])
                    for tx in block["transactions"]:
                        try:
                            # Extract signers from jsonParsed
                            if "transaction" in tx and "message" in tx["transaction"]:
                                msg = tx["transaction"]["message"]
                                if "accountKeys" in msg:
                                    for account in msg["accountKeys"]:
                                        # Check if signer
                                        is_signer = False
                                        pubkey = None
                                        
                                        if isinstance(account, dict):
                                            if account.get("signer"):
                                                is_signer = True
                                                pubkey = account.get("pubkey")
                                        
                                        if is_signer and pubkey and pubkey not in existing_targets:
                                            candidates.add(pubkey)
                        except Exception:
                            continue

            # Update stats
            stats["blocks_processed"] += len(blocks)
            stats["transactions_scanned"] += tx_count
            stats["signers_checked"] += len(candidates)
            stats["current_slot"] = start_slot + count
            
            # Check balances for candidates
            if candidates:
                found = await check_balances(session, list(candidates))
                for addr in found:
                    save_target(addr)

            queue.task_done()
            
            # Periodic stats update
            if start_slot % 100 == 0:
                update_stats()
                print(f"\r[Speed: {stats['speed_blocks_per_sec']:.1f} blk/s] [Found: {stats['high_value_found']}] [Slot: {stats['current_slot']}]", end="", flush=True)

        except Exception as e:
            logger.error(f"Worker error: {e}")
            queue.task_done()

async def main():
    load_targets()
    
    # Create queue for block ranges
    queue = asyncio.Queue(maxsize=CONCURRENCY * 2)
    
    async with aiohttp.ClientSession() as session:
        # Get initial tip
        tip = await get_slot(session)
        if not tip:
            logger.error("Could not get initial slot. Exiting.")
            return
        
        logger.info(f"Starting from tip: {tip}")
        current_fetch_slot = tip - 1000 # Start a bit back
        
        # Start workers
        workers = [asyncio.create_task(worker(f"w-{i}", queue, session)) for i in range(CONCURRENCY)]
        
        # Producer loop
        while True:
            # Get latest tip to know how far we can go
            latest_tip = await get_slot(session)
            if not latest_tip:
                await asyncio.sleep(1)
                continue
            
            # If we are caught up, wait
            if current_fetch_slot >= latest_tip:
                await asyncio.sleep(0.5)
                continue
            
            # Add batch to queue
            # Don't go past latest tip
            batch_size = min(MAX_BATCH_SIZE, latest_tip - current_fetch_slot)
            if batch_size > 0:
                await queue.put((current_fetch_slot, batch_size))
                current_fetch_slot += batch_size
            else:
                await asyncio.sleep(0.1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
