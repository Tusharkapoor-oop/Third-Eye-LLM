import asyncio
import socket
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp.client import Client

CWD = r"C:\Users\ACER\Downloads\Broswer for ai agnets"


def wait_port(port: int, timeout: float = 30.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.25)
    return False


async def run(mode: str, port: int) -> None:
    async with Client(f"http://127.0.0.1:{port}/mcp", mode=mode) as client:
        print("MODE", mode, "PROTOCOL", client.protocol_version)
        tools = await client.list_tools()
        print("TOOLS", [t.name for t in tools.tools])
        res = await client.call_tool(
            "web_search", {"query": "python asyncio timeout", "max_results": 1}
        )
        print("SEARCH isError", res.is_error)
        for c in res.content:
            text = getattr(c, "text", None)
            if text:
                print(text[:220])


async def main() -> None:
    port = 8765
    proc = subprocess.Popen(
        ["uv", "run", "weblens", "serve", "--http", "--port", str(port)],
        cwd=CWD,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        if not wait_port(port):
            print("server did not start")
            err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
            print(err[-3000:])
            return
        for mode in ("legacy", "auto"):
            try:
                await run(mode, port)
            except Exception as e:
                print("MODE", mode, "FAILED", type(e).__name__, str(e)[:500])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


asyncio.run(main())
