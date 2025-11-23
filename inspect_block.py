import requests
import json

RPC_URL = "https://solana-mainnet.api.syndica.io/api-key/BSjbDnjDjdi6yZc1Kb9e3AJCWA9b33GxSWQApPjUNWdq1YJiR62KWNhLxHaTUdqdLGzeZehbfGBfBJBvKkWnDz8XFmjetyAup7"

def get_latest_block():
    # 1. Get current slot
    resp = requests.post(RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": "getSlot", "params": [{"commitment": "confirmed"}]})
    slot = resp.json()["result"]
    print(f"Current Slot: {slot}")

    # 2. Get Block
    payload = {
        "jsonrpc": "2.0", 
        "id": 1, 
        "method": "getBlock", 
        "params": [
            slot, 
            {
                "encoding": "json", 
                "transactionDetails": "full", 
                "rewards": False, 
                "maxSupportedTransactionVersion": 0
            }
        ]
    }
    resp = requests.post(RPC_URL, json=payload)
    if resp.status_code != 200:
        print(f"Error: {resp.text}")
        return

    data = resp.json()
    if "error" in data:
        print(f"RPC Error: {data['error']}")
        # Try a slightly older slot if current is missing
        payload["params"][0] = slot - 10
        resp = requests.post(RPC_URL, json=payload)
        data = resp.json()

    with open("block_dump.json", "w") as f:
        json.dump(data, f, indent=2)
    print("Saved block data to block_dump.json")

if __name__ == "__main__":
    get_latest_block()
