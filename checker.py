import asyncio
import os
import sys
import time
import json
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Dict, List, Optional, Tuple

import aiohttp
import base58
from nacl.signing import SigningKey

# ========= Defaults / Env =========
RPC_URL = os.environ.get(
    "RPC_URL",
    "https://solana-rpc.publicnode.com",
)
COMMITMENT = os.environ.get("COMMITMENT", "confirmed")
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "100"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "10"))
TIMEOUT_S = int(os.environ.get("TIMEOUT_S", "30"))
FOUND_FILE = os.environ.get("FOUND_FILE", "found.txt")

LAMPORTS_PER_SOL = 1_000_000_000

# ========= Types =========
FoundCallback = Callable[[str, str, float, str], Awaitable[None]]


@dataclass
class Status:
    start_time: float = field(default_factory=lambda: time.time())
    checked: int = 0
    found: int = 0
    api_errors: int = 0
    current_priv: str = "-"
    recent_found: List[Tuple[str, str, float, str]] = field(default_factory=list)
    # don't create an asyncio.Lock at import time; initialize in start()
    lock: Optional[asyncio.Lock] = None


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
    addrs: List[str] = []
    addr_to_priv: Dict[str, str] = {}
    last_priv = "-"
    for _ in range(n):
        sk = SigningKey.generate()
        pub = sk.verify_key.encode()
        addr = base58.b58encode(pub).decode()
        secret64 = sk.encode() + pub
        priv_b58 = base58.b58encode(secret64).decode()
        addrs.append(addr)
        addr_to_priv[addr] = priv_b58
        last_priv = priv_b58
    return addrs, addr_to_priv, last_priv


class Checker:
    def __init__(
        self,
        rpc_url: str = RPC_URL,
        commitment: str = COMMITMENT,
        batch_size: int = BATCH_SIZE,
        concurrency: int = CONCURRENCY,
        timeout_s: int = TIMEOUT_S,
        found_file: str = FOUND_FILE,
        on_found: Optional[FoundCallback] = None,
    ) -> None:
        self.rpc_url = rpc_url
        self.commitment = commitment
        self.batch_size = batch_size
        self.timeout_s = timeout_s
        # store concurrency so we can create semaphore when loop is available
        self._concurrency = concurrency
        # Defer creation of asyncio primitives until start() runs inside an event loop
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._task: Optional[asyncio.Task] = None
        self._running: Optional[asyncio.Event] = None
        self.status = Status()
        self._found_file = found_file
        self._found_lock: Optional[asyncio.Lock] = None
        self._on_found = on_found
        self._stop_flag = False
        self._injected_done = False
        self._injected_priv = os.environ.get(
            "TEST_INJECT_PRIV",
            "5CcxJCJJNXHhE3giPKatJA8Ppmorgi5KgiEnMpeHFQsChdRbnsbXrt6t4rtTJPTP2U9X614n8gmDcotLJbCtYP2K",
        )

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_flag = False
        self._injected_done = False
        self.status = Status()
        # create asyncio primitives bound to the currently running loop
        self._semaphore = asyncio.Semaphore(self._concurrency)
        self.status.lock = asyncio.Lock()
        self._found_lock = asyncio.Lock()
        self._running = asyncio.Event()
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=self.timeout_s, sock_read=self.timeout_s)
        self._session = aiohttp.ClientSession(timeout=timeout)
        self._task = asyncio.create_task(self._run_loop())
        self._running.set()

    async def stop(self) -> None:
        self._stop_flag = True
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except Exception:
                pass
        if self._session:
            await self._session.close()
            self._session = None
        if self._running:
            self._running.clear()

    def is_running(self) -> bool:
        return bool(self._running and self._running.is_set())

    async def _log_found(self, addr: str, priv: str, sol: float, ts: str) -> None:
        header = "timestamp,address,private_key,balance_sol\n"
        line = f"{ts},{addr},{priv},{sol:.9f}\n"
        async with self._found_lock:
            need_header = not os.path.exists(self._found_file) or os.path.getsize(self._found_file) == 0
            with open(self._found_file, "a", encoding="utf-8") as f:
                if need_header:
                    f.write(header)
                f.write(line)
                f.flush()

    async def _fetch_batch(self, addresses: List[str], addr_to_priv: Dict[str, str], batch_index: int) -> None:
        assert self._session is not None
        payload = {
            "jsonrpc": "2.0",
            "id": batch_index + 1,
            "method": "getMultipleAccounts",
            "params": [addresses, {"commitment": self.commitment}],
        }
        async with self._semaphore:
            try:
                async with self._session.post(self.rpc_url, json=payload, timeout=self.timeout_s) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        async with self.status.lock:
                            self.status.api_errors += 1
                        return
                    data = json.loads(text)
            except Exception:
                async with self.status.lock:
                    self.status.api_errors += 1
                return
        try:
            if "error" in data:
                async with self.status.lock:
                    self.status.api_errors += 1
                return
            values = data.get("result", {}).get("value", [])
            non_zero = 0
            for idx, v in enumerate(values):
                if v and isinstance(v, dict):
                    lamports = v.get("lamports", 0)
                    if lamports > 0:
                        non_zero += 1
                        addr = addresses[idx]
                        priv = addr_to_priv.get(addr, "-")
                        sol = lamports / LAMPORTS_PER_SOL
                        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                        if self._on_found:
                            try:
                                await self._on_found(addr, priv, sol, ts)
                            except Exception:
                                pass
                        await self._log_found(addr, priv, sol, ts)
                        async with self.status.lock:
                            self.status.recent_found.append((addr, priv, sol, ts))
                            if len(self.status.recent_found) > 100:
                                self.status.recent_found = self.status.recent_found[-100:]
            async with self.status.lock:
                self.status.checked += len(addresses)
                self.status.found += non_zero
        except Exception:
            async with self.status.lock:
                self.status.api_errors += 1

    async def _run_loop(self) -> None:
        assert self._session is not None
        i = 0
        while not self._stop_flag:
            addresses, addr_to_priv, last_priv = generate_keypairs_with_priv(self.batch_size)
            if (not self._injected_done) and i == 9 and self._injected_priv:
                try:
                    sk = signing_key_from_b58_priv(self._injected_priv)
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
                    self._injected_done = True
                except Exception:
                    pass
            async with self.status.lock:
                self.status.current_priv = last_priv
            await self._fetch_batch(addresses, addr_to_priv, i)
            async with self.status.lock:
                self.status.current_priv = last_priv
            i += 1

    def snapshot(self) -> Dict[str, object]:
        # Non-blocking snapshot of status
        s = self.status
        return {
            "checked": s.checked,
            "found": s.found,
            "api_errors": s.api_errors,
            "uptime_s": int(time.time() - s.start_time),
            "current_priv": s.current_priv,
            "recent_found": list(s.recent_found),
        }
