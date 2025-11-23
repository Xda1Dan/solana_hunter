import asyncio
import aiohttp
import json
import time
import os
from typing import List, Set

# Config
RPC_URL = "https://solana-mainnet.api.syndica.io/api-key/BSjbDnjDjdi6yZc1Kb9e3AJCWA9b33GxSWQApPjUNWdq1YJiR62KWNhLxHaTUdqdLGzeZehbfGBfBJBvKkWnDz8XFmjetyAup7"
TARGETS_FILE = "targets.txt"
BATCH_SIZE = 100
MAX_RPS = 20
COMMITMENT = "confirmed"
MIN_BALANCE_SOL = 1.0
MIN_BALANCE_LAMPORTS = int(MIN_BALANCE_SOL * 1_000_000_000)

class RateLimiter:
    def __init__(self, rate_per_sec: int):
        self.rate = max(1, rate_per_sec)
        self.interval = 1.0 / self.rate
        self._next_request = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next_request < now:
                self._next_request = now
            wait_until = self._next_request
            self._next_request += self.interval
            delay = wait_until - now
            if delay > 0:
                await asyncio.sleep(delay)

    async def pause(self, seconds: float):
        async with self._lock:
            now = time.monotonic()
            if self._next_request < now:
                self._next_request = now + seconds
            else:
                self._next_request += seconds

async def rpc_call(session, method, params, limiter):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }
    while True:
        try:
            await limiter.acquire()
            async with session.post(RPC_URL, json=payload) as resp:
                if resp.status == 429:
                    print("Rate limited (429). Pausing...")
                    await limiter.pause(2.0)
                    continue
                if resp.status != 200:
                    print(f"HTTP Error {resp.status}")
                    return None
                return await resp.json()
        except Exception as e:
            print(f"RPC Error: {e}")
            await asyncio.sleep(1)

async def get_slot(session, limiter):
    data = await rpc_call(session, "getSlot", [{"commitment": COMMITMENT}], limiter)
    if data and "result" in data:
        return data["result"]
    return None

async def get_block(session, slot, limiter):
    params = [
        slot,
        {
            "encoding": "jsonParsed",  # Changed to jsonParsed for easier signer identification
            "transactionDetails": "full",
            "rewards": False,
            "maxSupportedTransactionVersion": 0
        }
    ]
    data = await rpc_call(session, "getBlock", params, limiter)
    if data and "result" in data:
        return data["result"]
    return None

async def check_balances(session, addresses, limiter):
    valid_addresses = []
    for i in range(0, len(addresses), BATCH_SIZE):
        batch = addresses[i:i + BATCH_SIZE]
        params = [batch, {"commitment": COMMITMENT}]
        data = await rpc_call(session, "getMultipleAccounts", params, limiter)
        
        if data and "result" in data and "value" in data["result"]:
            values = data["result"]["value"]
            for idx, val in enumerate(values):
                if val is not None:
                    lamports = val.get("lamports", 0)
                    if lamports > MIN_BALANCE_LAMPORTS:
                        valid_addresses.append(batch[idx])
    return valid_addresses

async def main():
    print(f"Starting Smart Solana Scraper (Min Balance: {MIN_BALANCE_SOL} SOL)...")
    limiter = RateLimiter(MAX_RPS)
    
    existing_targets = set()
    if os.path.exists(TARGETS_FILE):
        with open(TARGETS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    existing_targets.add(line)
    print(f"Loaded {len(existing_targets)} existing targets.")

    async with aiohttp.ClientSession() as session:
        last_slot = await get_slot(session, limiter)
        if last_slot is None:
            print("Failed to get initial slot.")
            return
        
async def get_blocks(session, start_slot, end_slot, limiter):
    params = [start_slot, end_slot, {"commitment": COMMITMENT}]
    data = await rpc_call(session, "getBlocks", params, limiter)
    if data and "result" in data:
        return data["result"]
    return []

def clean_targets_file():
    if not os.path.exists(TARGETS_FILE):
        return set()
    
    print("Cleaning targets.txt (removing duplicates)...")
    unique_targets = set()
    with open(TARGETS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                unique_targets.add(line)
    
    with open(TARGETS_FILE, "w") as f:
        for addr in unique_targets:
            f.write(f"{addr}\n")
            
    print(f"Cleaned. Loaded {len(unique_targets)} unique targets.")
    return unique_targets

async def process_block(session, slot, limiter, existing_targets):
    try:
        block_data = await get_block(session, slot, limiter)
        if block_data is None:
            return 0, []

        tx_count = 0
        candidates = set()
        if "transactions" in block_data:
            tx_count = len(block_data["transactions"])
            for tx in block_data["transactions"]:
                if "transaction" in tx and "message" in tx["transaction"]:
                    msg = tx["transaction"]["message"]
                    if "accountKeys" in msg:
                        for account in msg["accountKeys"]:
                            if isinstance(account, dict):
                                if account.get("signer"):
                                    addr = account.get("pubkey")
                                    if addr and addr not in existing_targets:
                                        candidates.add(addr)
        return tx_count, list(candidates)
    except Exception as e:
        print(f"\nError processing block {slot}: {e}")
        return 0, []

async def main():
    print(f"Starting Smart Solana Scraper (Min Balance: {MIN_BALANCE_SOL} SOL)...")
    limiter = RateLimiter(MAX_RPS)
    
    # Clean and load targets
    existing_targets = clean_targets_file()

    async with aiohttp.ClientSession() as session:
        # Start from a recent slot (e.g. 100 blocks ago)
        tip = await get_slot(session, limiter)
        if tip is None:
            print("Failed to get initial slot.")
            return
        
        last_processed_slot = tip - 100
        print(f"Starting from slot {last_processed_slot} (Tip: {tip})")
        
        while True:
            try:
                # Get latest tip
                current_tip = await get_slot(session, limiter)
                if current_tip is None:
                    await asyncio.sleep(1)
                    continue

                # If we are too close to the tip, wait a bit
                if last_processed_slot >= current_tip - 1:
                    print(f"\r[Status] Waiting for new blocks (Tip: {current_tip})...   ", end="", flush=True)
                    await asyncio.sleep(1.0)
                    continue

                # Define range to fetch
                start = last_processed_slot + 1
                end = min(start + 20, current_tip) # Fetch chunks of 20 for concurrency

                print(f"\r[Status] Finding valid blocks in range {start}-{end}...", end="", flush=True)
                valid_slots = await get_blocks(session, start, end, limiter)
                
                if not valid_slots:
                    print(f"\r[Info] No valid blocks in range {start}-{end}. Skipping.      ", end="", flush=True)
                    last_processed_slot = end
                    continue

                print(f"\r[Status] Processing {len(valid_slots)} blocks concurrently...      ", end="", flush=True)
                
                # Process blocks concurrently
                tasks = [process_block(session, slot, limiter, existing_targets) for slot in valid_slots]
                results = await asyncio.gather(*tasks)
                
                total_tx = 0
                all_candidates = set()
                
                for tx_count, candidates in results:
                    total_tx += tx_count
                    for c in candidates:
                        all_candidates.add(c)
                
                print(f"\r[Batch {start}-{end}] {total_tx} txs. Checking {len(all_candidates)} unique signers...", end="", flush=True)

                if all_candidates:
                    found = await check_balances(session, list(all_candidates), limiter)
                    if found:
                        print(f"\n[SUCCESS] Batch {start}-{end}: Found {len(found)} high-value wallets!")
                        with open(TARGETS_FILE, "a") as f:
                            for addr in found:
                                if addr not in existing_targets:
                                    f.write(f"{addr}\n")
                                    existing_targets.add(addr)
                    else:
                        print(f"\r[Batch {start}-{end}] Scanned {len(all_candidates)} signers. 0 high-value found.      ", end="", flush=True)
                else:
                    print(f"\r[Batch {start}-{end}] No new signers found.                                     ", end="", flush=True)
                
                last_processed_slot = end

            except KeyboardInterrupt:
                print("\nStopped by user.")
                break
            except Exception as e:
                print(f"\nError: {e}")
                await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
