import time
import base58
from nacl.signing import SigningKey
import concurrent.futures

def generate_batch(n):
    for _ in range(n):
        sk = SigningKey.generate()
        pub = sk.verify_key.encode()
        addr = base58.b58encode(pub).decode()
        # Simulate checking against a set (very fast)
        _ = addr == "foo"

def benchmark():
    BATCH_SIZE = 1000
    NUM_BATCHES = 10
    TOTAL = BATCH_SIZE * NUM_BATCHES
    
    start = time.time()
    for _ in range(NUM_BATCHES):
        generate_batch(BATCH_SIZE)
    end = time.time()
    
    duration = end - start
    rate = TOTAL / duration
    print(f"Single Core Speed: {rate:.2f} keys/sec")

if __name__ == "__main__":
    benchmark()
