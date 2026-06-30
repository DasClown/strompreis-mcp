"""Strompreis MCP Server — v0.2.0 with database persistence and auth."""

import sys
import json
import os
from typing import Any

from . import forecast
from . import smard_client
from . import database
from . import auth


def handle_request(request: dict) -> dict:
    """Handle a single MCP request."""
    method = request.get("method", "")
    req_id = request.get("id", 0)

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "strompreis-mcp",
                    "version": "0.2.0",
                },
            },
        }

    elif method == "notifications/initialized":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "price_forecast",
                        "description": (
                            "Get hourly electricity price forecast for Germany. "
                            "Returns prices in ct/kWh for the next N hours. "
                            "Use this to answer 'When is electricity cheapest?'"
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "hours": {
                                    "type": "integer",
                                    "description": "Number of hours to forecast (1-72, default 24)",
                                    "default": 24,
                                },
                            },
                        },
                    },
                    {
                        "name": "best_hours",
                        "description": (
                            "Find the cheapest hours for power consumption. "
                            "Returns a human-readable recommendation for "
                            "running appliances or charging."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "count": {
                                    "type": "integer",
                                    "description": "Number of cheapest hours to return (default 3)",
                                    "default": 3,
                                },
                            },
                        },
                    },
                    {
                        "name": "db_status",
                        "description": (
                            "Check database health: row count, latest timestamp, "
                            "usage statistics. Useful for monitoring."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                ],
            },
        }

    elif method == "tools/call":
        tool_name = request.get("params", {}).get("name", "")
        arguments = request.get("params", {}).get("arguments", {})

        # Auth check for tool calls
        if not auth.authenticate(tool_name=tool_name):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32000,
                    "message": "Rate limit exceeded. Set STROMPREIS_API_KEY for higher limits.",
                },
            }

        if tool_name == "price_forecast":
            hours = int(arguments.get("hours", 24))
            data = forecast.forecast(hours=hours)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(data, indent=2, ensure_ascii=False),
                        }
                    ],
                },
            }

        elif tool_name == "best_hours":
            count = int(arguments.get("count", 3))
            text = forecast.best_hours(count=count)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                        }
                    ],
                },
            }

        elif tool_name == "db_status":
            stats = auth.get_usage_stats()
            total_rows = database.get_price_count()
            latest_ts = database.get_latest_db_timestamp()
            text = (
                f"📊 DB Status\n"
                f"  Rows:     {total_rows}\n"
                f"  Latest:   {latest_ts or 'empty'}\n"
                f"  Mode:     {stats['mode']}\n"
                f"  Keys:     {stats['total_active_keys']}\n"
                f"  Today:    {stats['today_calls']} calls"
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                },
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
            }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    return {"jsonrpc": "2.0", "id": req_id, "result": {}}


def main():
    """Run the MCP server via stdio."""
    # Pre-warm: fetch live data + ensure DB initialized
    try:
        database.init_db()
        smard_client.get_latest_prices()
    except Exception:
        pass  # Will use fallback if SMARD unavailable

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            continue
        except BrokenPipeError:
            break
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": 0,
                "error": {"code": -32603, "message": str(e)},
            }
            print(json.dumps(error_response), flush=True)


if __name__ == "__main__":
    main()
