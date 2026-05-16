#!/bin/bash
# Activate virtualenv if present
if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
fi

export TEL_NODE_ID="${TEL_NODE_ID:-HUB}"
export TEL_HUB_HOST="${TEL_HUB_HOST:-0.0.0.0}"
python3 -m tel_deploy hub
