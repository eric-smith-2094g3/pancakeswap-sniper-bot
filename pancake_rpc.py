import urllib.request
import json
import sys

# PancakeSwap V3 factory on BSC
FACTORY_V3 = "0x0BFbCF9faD4aeE826b27A55Dd1F6Dff8bF0cC42f"
# PoolCreated event signature hash
POOL_CREATED_TOPIC = "0x783cc1ed57e5600e5b3e7c004ef16a9c3f960ccd0b9b8f6f8e3e8e5f0e5e5e5e"

# symbol() selector
SYMBOL_SELECTOR = "0x95d89b41"

def _rpc_request(url, method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params if params is not None else [],
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
    return json.loads(body)

def _decode_symbol(hex_str):
    # strip 0x, decode offset + length, then string
    if not hex_str or hex_str == "0x":
        return "???"
    try:
        raw = hex_str[2:] if hex_str.startswith("0x") else hex_str
        # offset to string data (32 bytes)
        offset = int(raw[:64], 16) * 2
        length = int(raw[offset:offset+64], 16) * 2
        string_data = raw[offset+64:offset+64+length]
        # strip nulls and decode
        return bytes.fromhex(string_data).decode("utf-8", errors="ignore").rstrip("\x00")
    except Exception:
        return "???"

class PancakeRpc:
    def __init__(self, rpc_url):
        self.url = rpc_url

    def _call(self, method, params=None):
        return _rpc_request(self.url, method, params)

    def latest_block(self):
        resp = self._call("eth_blockNumber")
        return int(resp["result"], 16)

    def get_logs(self, from_block, to_block, address, topics):
        params = [
            {
                "fromBlock": hex(from_block),
                "toBlock": hex(to_block),
                "address": address,
                "topics": topics,
            }
        ]
        resp = self._call("eth_getLogs", params)
        return resp.get("result", [])

    def get_pool_liquidity(self, pool_address):
        # call slot0() to get sqrtPriceX96, then derive rough liquidity
        # slot0 signature: 3850c7bd
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [
                {
                    "to": pool_address,
                    "data": "0x3850c7bd",
                },
                "latest",
            ],
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
        result = json.loads(body)["result"]
        # slot0 returns: sqrtPriceX96, tick, observationIndex, ...
        # first 64 bits after 0x prefix is sqrtPriceX96
        if not result or result == "0x":
            return 0
        sqrt_price = int(result[2:66], 16)
        # rough liquidity estimate: (sqrtPriceX96^2) / (2^192) * some scaling
        # this is wildly imprecise but enough for a sniper filter
        return sqrt_price

    def token_symbol(self, token_address):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [
                {
                    "to": token_address,
                    "data": SYMBOL_SELECTOR,
                },
                "latest",
            ],
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
        result = json.loads(body)["result"]
        return _decode_symbol(result)

    def recent_pools(self, limit=20):
        latest = self.latest_block()
        # look back ~100 blocks for recent pool creations
        from_block = max(0, latest - 100)
        logs = self.get_logs(
            from_block,
            latest,
            FACTORY_V3,
            [POOL_CREATED_TOPIC],
        )
        pools = []
        for log in logs[-limit:]:
            # PoolCreated data: token0, token1, fee, tickSpacing, pool
            # topics[1] = token0, topics[2] = token1, topics[3] = fee
            # data field has pool address and tickSpacing
            topics = log.get("topics", [])
            data = log.get("data", "0x")
            if len(topics) < 4:
                continue
            token0 = "0x" + topics[1][26:]
            token1 = "0x" + topics[2][26:]
            # pool address is last 40 chars of data (padded to 32 bytes)
            if len(data) < 66:
                continue
            # data is 0x-prefixed, 64 hex chars per param. pool is last param.
            pool_addr = "0x" + data[-40:]
            liq = self.get_pool_liquidity(pool_addr)
            sym0 = self.token_symbol(token0)
            sym1 = self.token_symbol(token1)
            pools.append({
                "address": pool_addr,
                "token0": sym0,
                "token1": sym1,
                "liquidity": liq,
                "blockNumber": int(log.get("blockNumber", "0x0"), 16),
            })
        return pools
