import time
from solders.keypair import Keypair

def generate_batch(n):
    for _ in range(n):
        kp = Keypair()
        addr = str(kp.pubkey())
        # Simulate checking against a set
        _ = addr == "foo"

def benchmark():
    BATCH_SIZE = 10000
    NUM_BATCHES = 100
    TOTAL = BATCH_SIZE * NUM_BATCHES
    
    start = time.time()
    for _ in range(NUM_BATCHES):
        generate_batch(BATCH_SIZE)
    end = time.time()
    
    duration = end - start
    rate = TOTAL / duration
    print(f"Solders Single Core Speed: {rate:.2f} keys/sec")

if __name__ == "__main__":
    benchmark()
