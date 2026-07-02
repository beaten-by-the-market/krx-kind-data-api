"""MCP 서버 — KIND 카탈로그의 각 엔드포인트를 MCP 툴로 노출.

카탈로그(endpoints.ENDPOINTS)의 `"params"` 메타데이터를 그대로 JSON-Schema로
변환해 툴 인자를 만들고, 호출되면 fetch(name, **arguments) → DataFrame을
JSON records로 돌려준다. 엔드포인트를 추가하면 툴이 **자동으로** 늘어난다.

설치 & 실행
-----------
    pip install "krx-kind-data-api[mcp]"
    python -m krx_kind_data_api.mcp_server          # stdio 트랜스포트

Claude Desktop / Claude Code 등록 (claude_desktop_config.json 또는 mcp 설정):
    {
      "mcpServers": {
        "krx-kind": {
          "command": "python",
          "args": ["-m", "krx_kind_data_api.mcp_server"]
        }
      }
    }

설계 메모
---------
아래 순수 함수들(tool_name/endpoint_from_tool/input_schema/run_tool)은 `mcp`
패키지에 의존하지 않는다. 덕분에 mcp 미설치 환경에서도 스키마/디스패치 로직을
단위 테스트할 수 있다. `mcp` import는 서버를 실제 구동하는 build_server()/main()
안에서만 일어난다.
"""
from __future__ import annotations

import json
from typing import Any

from . import endpoint_info, fetch, list_endpoints

TOOL_PREFIX = "kind_"

# 응답이 지나치게 커지지 않도록 records 상한(초과분은 잘라내고 truncated 플래그로 알림).
MAX_ROWS = 500


# ── 순수 로직 (mcp 불필요) ──────────────────────────────────────────

def tool_name(endpoint: str) -> str:
    """엔드포인트 이름 → MCP 툴 이름. 예: 'pubofr_prog_com' → 'kind_pubofr_prog_com'."""
    return f"{TOOL_PREFIX}{endpoint}"


def endpoint_from_tool(tool: str) -> str:
    """MCP 툴 이름 → 엔드포인트 이름(역변환)."""
    return tool[len(TOOL_PREFIX):] if tool.startswith(TOOL_PREFIX) else tool


def input_schema(endpoint: str) -> dict:
    """endpoint_info(name)["params"] → MCP inputSchema(JSON-Schema).

    각 파라미터는 문자열 타입으로 노출한다(KIND 화면은 문자열 폼값을 기대).
    enum/format/example이 있으면 스키마에 반영한다.
    """
    params = endpoint_info(endpoint).get("params", {})
    properties: dict[str, dict] = {}
    for key, meta in params.items():
        prop: dict[str, Any] = {"type": "string", "description": meta["desc"]}
        if meta.get("enum"):
            prop["enum"] = list(meta["enum"])
        if meta.get("format"):
            prop["description"] += f" (형식: {meta['format']})"
        if meta.get("example") not in (None, ""):
            prop["examples"] = [meta["example"]]
        properties[key] = prop
    return {
        "type": "object",
        "properties": properties,
        "required": [k for k, v in params.items() if v.get("required")],
        "additionalProperties": False,
    }


def _clean_arguments(arguments: dict | None) -> dict:
    """빈 문자열/None 인자는 제거 → 카탈로그 defaults가 적용되도록."""
    return {
        k: v for k, v in (arguments or {}).items() if v not in (None, "")
    }


def run_tool(endpoint: str, arguments: dict | None = None) -> dict:
    """엔드포인트를 호출해 JSON-직렬화 가능한 결과 dict를 반환.

    반환: {"endpoint", "rows", "columns", "truncated", "records"}.
    fetch()가 KINDFetchError 등을 던지면 그대로 전파한다(호출부가 처리).
    """
    df = fetch(endpoint, **_clean_arguments(arguments))
    total = len(df)
    truncated = total > MAX_ROWS
    view = df.head(MAX_ROWS) if truncated else df
    # to_json은 numpy/NaT 타입을 JSON-안전하게 변환해준다.
    records = json.loads(view.to_json(orient="records", force_ascii=False))
    return {
        "endpoint": endpoint,
        "rows": total,
        "columns": list(df.columns),
        "truncated": truncated,
        "records": records,
    }


def catalog() -> list[dict]:
    """등록될 툴 목록의 메타(테스트/디버깅용). name·description·inputSchema."""
    return [
        {
            "name": tool_name(ep),
            "description": endpoint_info(ep).get("screen", ep),
            "inputSchema": input_schema(ep),
        }
        for ep in list_endpoints()
    ]


# ── 서버 구동 (mcp 필요) ────────────────────────────────────────────

def build_server():
    """low-level mcp.server.Server 인스턴스를 구성해 반환."""
    from mcp.server import Server
    import mcp.types as types

    server = Server("krx-kind")

    @server.list_tools()
    async def _list_tools() -> list["types.Tool"]:
        return [
            types.Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in catalog()
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None):
        endpoint = endpoint_from_tool(name)
        try:
            result = run_tool(endpoint, arguments)
            text = json.dumps(result, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001  KIND 오류를 툴 결과로 전달
            text = json.dumps(
                {"endpoint": endpoint, "error": f"{type(e).__name__}: {e}"},
                ensure_ascii=False,
            )
        return [types.TextContent(type="text", text=text)]

    return server


async def _amain() -> None:
    from mcp.server.stdio import stdio_server

    server = build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    import asyncio

    asyncio.run(_amain())


if __name__ == "__main__":
    main()
