import asyncio
import os
import httpx

async def main():
    api_key = os.environ.get("KIMI_API_KEY", "")
    model = os.environ.get("TEL_MODEL", "kimi-k2.5")
    url = "https://api.moonshot.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Say hello in one word."},
        ],
    }
    print(f"POST {url}")
    print(f"Model: {model}")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            print(f"Status : {resp.status_code}")
            print(f"Body   : {resp.text[:1000]}")
    except Exception as e:
        print(f"Exception type : {type(e).__name__}")
        print(f"Exception msg  : {e!r}")

asyncio.run(main())
