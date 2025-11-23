import asyncio
import json
import os
import sys
import time
import logging
import concurrent.futures
from typing import List, Optional, Dict, Tuple, Set
from dataclasses import dataclass, field
import aiohttp
import base58
from nacl.signing import SigningKey

# ================= CONFIG =================
@dataclass
class Config:
    RPC_URLS: List[str] = field(default_factory=lambda: [
        "https://solana-mainnet.api.syndica.io/api-key/BSjbDnjDjdi6yZc1Kb9e3AJCWA9b33GxSWQApPjUNWdq1YJiR62KWNhLxHaTUdqdLGzeZehbfGBfBJBvKkWnDz8XFmjetyAup7",
    ])
    TARGETS_FILE: str = "targets.txt"
    TOTAL_BATCHES: int = 100
    BATCH_SIZE: int = 1000  # Increased batch size for offline generation
    CONCURRENCY: int = 10  # Keep high concurrency for CPU utilization
    COMMITMENT: str = "confirmed"
    TIMEOUT_S: int = 30
    REQUESTS_PER_KEY_BEFORE_ROTATE: int = 9
    MAX_RPS: int = 100 # High RPS allowed since we barely use it

    @property
    def valid_rpc_urls(self) -> List[str]:
        return [u.strip() for u in self.RPC_URLS if isinstance(u, str) and u.strip()]

# Global config instance
CONFIG = Config()

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("solana_checker.log"),
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class BatchResult:
    batch_index: int
    checked: int
    non_zero: int
    success: bool
    error: Optional[str] = None
    request_data: Optional[dict] = None
    response_data: Optional[dict] = None


# ================ CLI COLORS/STATUS ================
RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
CYAN = "\x1b[36m"


@dataclass
class Status:
    start_time: float
    checked: int = 0
    found: int = 0
    api_errors: int = 0
    current_priv: str = "-"
    stop: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    recent_found: List[Tuple[str, str, float, str]] = field(default_factory=list)
    errors_by_kind: Dict[str, int] = field(default_factory=dict)
    error_samples: List[str] = field(default_factory=list)
    sample_request_url: Optional[str] = None
    sample_request_payload: Optional[dict] = None

FOUND_FILE = "found.txt"
_found_lock = asyncio.Lock()


def fmt_runtime(start: float) -> str:
    s = int(time.time() - start)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


async def render_status(status: Status) -> None:
    # Single-line status updated in place
    while not status.stop:
        async with status.lock:
            line = (
                f"{BOLD}{CYAN}Checked{RESET}:{status.checked}  "
                f"{BOLD}{GREEN}Found{RESET}:{status.found}  "
                f"{BOLD}{YELLOW}Runtime{RESET}:{fmt_runtime(status.start_time)}  "
                f"{BOLD}{RED}API Errors{RESET}:{status.api_errors}  "
                f"{BOLD}{BLUE}Currently{RESET}: {DIM}{status.current_priv}{RESET}"
            )
        # Carriage return to rewrite the same line
        sys.stdout.write("\r" + line + " " * 10)
        sys.stdout.flush()
        await asyncio.sleep(0.2)
    # Final rewrite with newline to release the line
    async with status.lock:
        line = (
            f"{BOLD}{CYAN}Checked{RESET}:{status.checked}  "
            f"{BOLD}{GREEN}Found{RESET}:{status.found}  "
            f"{BOLD}{YELLOW}Runtime{RESET}:{fmt_runtime(status.start_time)}  "
            f"{BOLD}{RED}API Errors{RESET}:{status.api_errors}  "
            f"{BOLD}{BLUE}Currently{RESET}: {DIM}{status.current_priv}{RESET}"
        )
    sys.stdout.write("\r" + line + "\n")
    sys.stdout.flush()


async def log_found(addr: str, priv: str, sol: float, status: Status) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    header = "timestamp,address,private_key,balance_sol\n"
    line = f"{ts},{addr},{priv},{sol:.9f}\n"
    
    logger.info(f"FOUND: Address={addr} Priv={priv} Balance={sol:.9f}")

    async with _found_lock:
        need_header = not os.path.exists(FOUND_FILE) or os.path.getsize(FOUND_FILE) == 0
        with open(FOUND_FILE, "a", encoding="utf-8") as f:
            if need_header:
                f.write(header)
            f.write(line)
            f.flush()
    async with status.lock:
        status.recent_found.append((addr, priv, sol, ts))
        if len(status.recent_found) > 100:
            status.recent_found = status.recent_found[-100:]


def signing_key_from_b58_priv(priv_b58: str) -> SigningKey:
    raw = base58.b58decode(priv_b58)
    if len(raw) == 64:
        seed = raw[:32]
    elif len(raw) == 32:
        seed = raw
    else:
        raise ValueError("Unsupported private key length; expected 32 or 64 bytes")
    return SigningKey(seed)


def generate_keypairs_with_priv(n: int) -> Tuple[List[str], Dict[str, str], str]:
    """Generate n Solana keypairs; return (addresses, addr->priv_b58, last_priv). Private key is base58 of 64 bytes (seed+pub)."""
    addrs: List[str] = []
    addr_to_priv: Dict[str, str] = {}
    last_priv = "-"
    for _ in range(n):
        sk = SigningKey.generate()
        pub = sk.verify_key.encode()
        addr = base58.b58encode(pub).decode()
        # Build 64-byte secret (seed + pub)
        secret64 = sk.encode() + pub
        priv_b58 = base58.b58encode(secret64).decode()
        addrs.append(addr)
        addr_to_priv[addr] = priv_b58
        last_priv = priv_b58
    return addrs, addr_to_priv, last_priv


async def check_balance_rpc(
    session: aiohttp.ClientSession,
    address: str,
    rpc_pool,
    rate_limiter,
    status: Status
) -> float:
    """Check balance for a single address via RPC."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [address, {"commitment": CONFIG.COMMITMENT}],
    }
    
    try:
        url = await rpc_pool.next()
        await rate_limiter.acquire()
        
        async with session.post(url, json=payload, timeout=CONFIG.TIMEOUT_S) as resp:
            text = await resp.text()
            if resp.status != 200:
                if resp.status == 429:
                    await rate_limiter.pause(2.0)
                async with status.lock:
                    status.api_errors += 1
                return 0.0
            
            data = json.loads(text)
            if "error" in data:
                async with status.lock:
                    status.api_errors += 1
                return 0.0
                
            val = data.get("result", {}).get("value", 0)
            return val / 1_000_000_000
    except Exception as e:
        async with status.lock:
            status.api_errors += 1
        return 0.0


class RPCPool:
    def __init__(self, urls: List[str], rotate_after: int = 9):
        self.urls = urls
        self.rotate_after = max(1, rotate_after)
        self._idx = 0
        self._count = 0
        self._lock = asyncio.Lock()

    async def next(self) -> str:
        async with self._lock:
            url = self.urls[self._idx]
            self._count += 1
            if self._count >= self.rotate_after:
                self._count = 0
                self._idx = (self._idx + 1) % len(self.urls)
            return url


class PacedRateLimiter:
    def __init__(self, rate_per_sec: int):
        self.rate = max(1, rate_per_sec)
        self.interval = 1.0 / self.rate
        self._next_request = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            # If we are behind, reset to now (don't burst catch up)
            if self._next_request < now:
                self._next_request = now
            
            wait_until = self._next_request
            self._next_request += self.interval
            
            delay = wait_until - now
            if delay > 0:
                await asyncio.sleep(delay)

    async def pause(self, seconds: float):
        """Pause the limiter for a duration (e.g. on 429)"""
        async with self._lock:
            now = time.monotonic()
            # Push the next request time forward
            if self._next_request < now:
                self._next_request = now + seconds
            else:
                self._next_request += seconds


def load_targets(path: str) -> Set[str]:
    targets = set()
    if not os.path.exists(path):
        return targets
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                targets.add(line)
    return targets


async def main():
    print(f"{BOLD}Starting Solana Offline Matcher...{RESET}")
    
    # Load targets
    targets = load_targets(CONFIG.TARGETS_FILE)
    print(f"Loaded {BOLD}{len(targets)}{RESET} target addresses from {CONFIG.TARGETS_FILE}")
    
    rpc_urls = CONFIG.valid_rpc_urls
    print(f"RPCs: {DIM}{len(rpc_urls)} endpoints{RESET}")
    print(f"Mode: offline match  Batch size: {CONFIG.BATCH_SIZE}  Concurrency: {CONFIG.CONCURRENCY}\n")

    timeout = aiohttp.ClientTimeout(total=None, sock_connect=CONFIG.TIMEOUT_S, sock_read=CONFIG.TIMEOUT_S)
    total_checked = 0
    total_non_zero = 0
    total_errors = 0
    total_success = 0

    status = Status(start_time=time.time())
    renderer = asyncio.create_task(render_status(status))

    # Provided test private key to inject on batch 10 (i == 9) once per run
    injected_priv = "5CcxJCJJNXHhE3giPKatJA8Ppmorgi5KgiEnMpeHFQsChdRbnsbXrt6t4rtTJPTP2U9X614n8gmDcotLJbCtYP2K"
    injected_done = False
    rpc_pool = RPCPool(rpc_urls, CONFIG.REQUESTS_PER_KEY_BEFORE_ROTATE)
    
    # Process pool for key generation
    loop = asyncio.get_running_loop()
    process_pool = concurrent.futures.ProcessPoolExecutor()

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            rate_limiter = PacedRateLimiter(CONFIG.MAX_RPS)
            
            async def worker(wid: int):
                nonlocal total_checked, total_non_zero, total_errors, total_success, injected_done
                i = 0
                while True:
                    # stop if requested
                    async with status.lock:
                        if status.stop:
                            return
                    
                    # Offload key generation to process pool
                    addresses, addr_to_priv, last_priv = await loop.run_in_executor(
                        process_pool, 
                        generate_keypairs_with_priv, 
                        CONFIG.BATCH_SIZE
                    )

                    # Inject test key logic
                    if (not injected_done) and i == 9 and wid == 0:
                        try:
                            sk = signing_key_from_b58_priv(injected_priv)
                            pub = sk.verify_key.encode()
                            injected_addr = base58.b58encode(pub).decode()
                            secret64 = sk.encode() + pub
                            injected_priv_b58 = base58.b58encode(secret64).decode()
                            if addresses:
                                addresses[0] = injected_addr
                            else:
                                addresses.append(injected_addr)
                            addr_to_priv[injected_addr] = injected_priv_b58
                            last_priv = injected_priv_b58
                            injected_done = True
                        except Exception as e:
                            sys.stdout.write(f"\n{RED}Failed to inject test key: {e}{RESET}\n")
                            logger.error(f"Failed to inject test key: {e}")

                    async with status.lock:
                        status.current_priv = last_priv
                    
                    # OFFLINE CHECK
                    matches = []
                    for addr in addresses:
                        if addr in targets:
                            matches.append(addr)
                    
                    # If match found, check balance via RPC
                    for m_addr in matches:
                        priv = addr_to_priv.get(m_addr, "-")
                        sol = await check_balance_rpc(session, m_addr, rpc_pool, rate_limiter, status)
                        
                        # Log found regardless of balance (since it matched target)
                        msg = (
                            f"\n{BOLD}{GREEN}[MATCHED]{RESET} Address: {m_addr}  "
                            f"Priv: {DIM}{priv}{RESET}  "
                            f"Balance: {BOLD}{sol:.9f} SOL{RESET}"
                        )
                        sys.stdout.write(msg + "\n")
                        sys.stdout.flush()
                        await log_found(m_addr, priv, sol, status)
                        
                        async with status.lock:
                            status.found += 1
                            if sol > 0:
                                total_non_zero += 1

                    async with status.lock:
                        total_checked += len(addresses)
                        status.checked += len(addresses)
                        status.current_priv = last_priv
                    i += 1

            tasks = [asyncio.create_task(worker(w)) for w in range(CONFIG.CONCURRENCY)]
            try:
                await asyncio.gather(*tasks)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
    except KeyboardInterrupt:
        pass
    finally:
        status.stop = True
        process_pool.shutdown()
        try:
            await renderer
        except Exception:
            pass

    # Write summary to file
    summary_path = "run_summary.txt"
    try:
        lines = []
        lines.append("=== Solana Offline Matcher Summary ===")
        lines.append(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
        lines.append(f"Runtime: {fmt_runtime(status.start_time)}")
        lines.append("")
        lines.append(f"Targets loaded: {len(targets)}")
        lines.append(f"Generated and checked: {total_checked}")
        lines.append(f"Matches found: {status.found}")
        lines.append("")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass

    print("\n=== SUMMARY ===")
    print(f"Generated and checked: {total_checked}")
    print(f"Matches found: {status.found}")
    print(f"Summary written to: {summary_path}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass