"""Local adapter comparison. Does not invoke an agent or measure provider tokens."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from cam_laya_cli.benchmark import distribution
from cam_laya_cli.worker import Client, request


def serve():
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("cam-laya-transport-benchmark")

    @server.tool()
    def decide(request_json: dict) -> dict:
        """Evaluate exactly the same request through the CAM local worker."""
        return request({"op": "decide", "request": request_json})

    server.run(transport="stdio")


def comparable(value):
    return {k: v for k, v in value.items() if k not in {"timing", "inference_ms"}}


async def compare(value, count):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    ipc, mcp = [], []
    with Client() as client:
        first = client.call({"op": "decide", "request": value})
        if first["status"] not in {"ok", "abstained"}:
            return {"status": "unavailable", "reason": first}
        params = StdioServerParameters(command=sys.executable,
                                       args=[str(Path(__file__).resolve()), "--serve"],
                                       env={key: os.environ[key] for key in
                                            ["XDG_CONFIG_HOME", "XDG_STATE_HOME", "HF_HOME",
                                             "HF_HUB_CACHE", "PYTHONPATH"] if key in os.environ})
        start = time.perf_counter()
        async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
            await session.initialize()
            initialization_ms = (time.perf_counter() - start) * 1000
            tools = await session.list_tools()
            for index in range(count):
                order = ("ipc", "mcp") if index % 2 == 0 else ("mcp", "ipc")
                for adapter in order:
                    start = time.perf_counter()
                    if adapter == "ipc":
                        cli_result = client.call({"op": "decide", "request": value})
                        ipc.append(round((time.perf_counter() - start) * 1000, 3))
                    else:
                        result = await session.call_tool("decide", {"request_json": value})
                        mcp.append(round((time.perf_counter() - start) * 1000, 3))
                        decoded = result.structured_content
                        if decoded is None:
                            decoded = json.loads(next(block.text for block in result.content if block.type == "text"))
                if result.is_error or comparable(decoded) != comparable(cli_result):
                    raise ValueError("adapter output parity failed")
    return {"status": "ok", "samples": count, "same_outputs": True,
            "input_sha256": hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(),
            "mcp_initialization_ms": round(initialization_ms, 3),
            "order": "counterbalanced ipc/mcp, then mcp/ipc",
            "persistent_ipc": distribution(ipc), "persistent_mcp": distribution(mcp),
            "tool_definition_bytes": len(tools.model_dump_json().encode()),
            "limitations": "IPC excludes fresh CLI startup. Wire bytes are not provider tokens.",
            "provider_tokens": None, "billed_usd": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--input", type=Path, default=Path("examples/request.json"))
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.serve:
        serve()
        return
    if not 1 <= args.samples <= 1000:
        parser.error("samples must be between one and 1000")
    result = asyncio.run(compare(json.loads(args.input.read_text()), args.samples))
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
        print(json.dumps({"status": result["status"], "output": str(args.output),
                          "same_outputs": result.get("same_outputs"),
                          "ipc_median_ms": result.get("persistent_ipc", {}).get("median_ms"),
                          "mcp_median_ms": result.get("persistent_mcp", {}).get("median_ms")}))
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
