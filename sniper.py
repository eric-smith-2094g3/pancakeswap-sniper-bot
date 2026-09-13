import argparse
import sys
import time
import os
import json
from datetime import datetime

from pancake_rpc import PancakeRpc

# BSC blocks are ~3s; scanning every block is noisy. 5s feels right.
DEFAULT_INTERVAL = 5

def _fmt_liquidity(wei):
    # BNB ~$250 rough estimate for quick filter; we don't need precision here
    bnb = wei / 1e18
    return bnb * 250

def _pool_line(pool):
    token0 = pool["token0"]
    token1 = pool["token1"]
    liq = _fmt_liquidity(pool["liquidity"])
    return f"[{pool['address']}] {token0}/{token1}  liq=${liq:,.0f}  block={pool['blockNumber']}"

def _check_new_pools(rpc, seen):
    pools = rpc.recent_pools(limit=20)
    new_pools = []
    for p in pools:
        addr = p["address"]
        if addr not in seen:
            seen.add(addr)
            new_pools.append(p)
    return new_pools

def _filter_interesting(pools, min_liq):
    out = []
    for p in pools:
        liq = _fmt_liquidity(p["liquidity"])
        if liq >= min_liq:
            out.append(p)
    return out

def watch(rpc, interval, min_liq):
    seen = set()
    # warm up so we don't alert on old pools at startup
    for p in rpc.recent_pools(limit=50):
        seen.add(p["address"])

    print(f"watching PancakeSwap V3 for new pools (interval={interval}s, min_liq=${min_liq:,.0f})")
    print("ctrl-c to stop\n")

    while True:
        try:
            new = _check_new_pools(rpc, seen)
        except Exception as e:
            print(f"rpc error: {e}", file=sys.stderr)
            time.sleep(interval)
            continue

        interesting = _filter_interesting(new, min_liq)
        for p in interesting:
            print(_pool_line(p))
            # flush so piping to another tool gets it immediately
            sys.stdout.flush()

        time.sleep(interval)

def main():
    parser = argparse.ArgumentParser(
        description="Watch PancakeSwap V3 for new high-liquidity pools.",
        usage="python -m sniper.sniper [--watch] [--rpc-url URL] [--min-liquidity USD]",
    )
    parser.add_argument("--watch", action="store_true", help="run continuous watch loop")
    parser.add_argument("--rpc-url", default=os.environ.get("BSC_RPC_URL"), help="BSC JSON-RPC endpoint")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="seconds between polls")
    parser.add_argument("--min-liquidity", type=float, default=50000, help="minimum liquidity in USD to report")
    args = parser.parse_args()

    if not args.rpc_url:
        print("set BSC_RPC_URL env var or pass --rpc-url", file=sys.stderr)
        sys.exit(2)

    rpc = PancakeRpc(args.rpc_url)

    if args.watch:
        try:
            watch(rpc, args.interval, args.min_liquidity)
        except KeyboardInterrupt:
            sys.exit(130)
    else:
        pools = rpc.recent_pools(limit=10)
        for p in pools:
            print(_pool_line(p))

if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        sys.exit(130)
