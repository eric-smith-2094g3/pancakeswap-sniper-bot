# pancakeswap-sniper-bot

I got tired of missing launches on PancakeSwap, so I built this to watch the factory contract for new V3 pools and surface ones with decent initial liquidity. It's a single-shot scanner I run in a tmux pane.

## install

pip install -r requirements.txt

## usage

The --watch flag keeps it running and polls for new pools. Without it, does one scan and exits.
