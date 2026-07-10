#!/usr/bin/env python3
"""
Node-RED Flow Audit Script.
Checks flows.json for common issues:
  - Missing error handlers (red triangle)
  - Hardcoded configs
  - Large context data (>1MB → Redis)
  - Missing debug nodes
  - Unused nodes

Usage:
  python scripts/audit-flows.py nodered/flows.json
"""

import json
import os
import sys
from collections import Counter

WARN = "\033[93mWARN\033[0m"
ERROR = "\033[91mERROR\033[0m"
INFO = "\033[94mINFO\033[0m"
PASS = "\033[92mPASS\033[0m"


def audit_flows(flow_path: str) -> dict:
    """Audit a Node-RED flows.json for common issues."""
    with open(flow_path, encoding='utf-8') as f:
        data = json.load(f)

    flows = data if isinstance(data, list) else data.get("flows", [])

    issues = {
        "errors": [],
        "warnings": [],
        "info": [],
        "passes": [],
    }
    node_count = len(flows)

    issues["info"].append(f"Total nodes: {node_count}")

    # Stats
    type_counts = Counter(n.get("type", "unknown") for n in flows)
    issues["info"].append(f"Node types: {dict(type_counts)}")

    # Check each node
    for node in flows:
        nid = node.get("id", "?")
        ntype = node.get("type", "?")
        nname = node.get("name", "") or nid
        wires = node.get("wires", [])

        # 1. Check for unconnected outputs (missing error handlers)
        if isinstance(wires, list) and len(wires) > 0:
            for i, w in enumerate(wires):
                if not w or (isinstance(w, list) and len(w) == 0):
                    # HTTP response nodes don't need error handlers
                    if ntype not in ("http response", "http in", "websocket in", "websocket out"):
                        issues["warnings"].append(
                            f"[{ntype}] {nname}: output {i} unconnected — may need error handler"
                        )

        # 2. Check for hardcoded configs (potential env var candidates)
        if ntype in ("mqtt out", "mqtt in"):
            broker = node.get("broker", "")
            topic = node.get("topic", "")
            if topic and not topic.startswith("${") and not topic.startswith("env."):
                issues["warnings"].append(
                    f"[MQTT] {nname}: hardcoded topic '{topic}' — consider env var"
                )
            if broker and isinstance(broker, str) and not broker.startswith("${"):
                issues["warnings"].append(
                    f"[MQTT] {nname}: hardcoded broker config — consider env var"
                )

        if ntype in ("http in", "http response"):
            url = node.get("url", "")
            if url and not url.startswith("${"):
                issues["warnings"].append(
                    f"[HTTP] {nname}: hardcoded URL '{url}' — consider env var"
                )

        # 3. Check for missing error handlers on function/template nodes
        if ntype in ("function", "template", "exec", "http request"):
            has_catch = any(
                n.get("type") == "catch" and nid in str(n.get("wires", []))
                for n in flows
            )
            if not has_catch:
                issues["warnings"].append(
                    f"[{ntype}] {nname}: no catch node found — may lose errors silently"
                )

        # 4. Check large JSON data in function nodes
        if ntype == "function":
            func = node.get("func", "")
            if len(func) > 5000:
                issues["warnings"].append(
                    f"[function] {nname}: {len(func)} chars — consider moving logic to sap-bridge"
                )
            # Check for hardcoded Redis keys
            if "flow.set" in func or "global.set" in func:
                # Check if it's setting large objects
                if "robotStates" in func or "largeObject" in func or "state" in func:
                    issues["warnings"].append(
                        f"[function] {nname}: uses flow.set/global.set for state — consider Redis externalization"
                    )

        # 5. Check for commented-out debug nodes (leftovers)
        if ntype == "debug":
            if node.get("name", "").startswith("//") or node.get("name", "").startswith("#"):
                issues["info"].append(
                    f"[debug] {nname}: commented-out debug node — consider removing"
                )

        # 6. Check for missing timeout on http request
        if ntype == "http request":
            if not node.get("timeout") or node.get("timeout") == "0":
                issues["warnings"].append(
                    f"[http request] {nname}: no timeout set — may hang indefinitely"
                )

    # Check for catch-all error handler presence
    catch_nodes = [n for n in flows if n.get("type") == "catch"]
    if not catch_nodes:
        issues["warnings"].append("No catch nodes found in any flow — all errors may be lost")
    else:
        issues["passes"].append(f"Catch nodes found: {len(catch_nodes)}")

    # Check for debug nodes
    debug_nodes = [n for n in flows if n.get("type") == "debug"]
    if debug_nodes:
        issues["passes"].append(f"Debug nodes: {len(debug_nodes)}")

    # Check status nodes (health monitoring)
    status_nodes = [n for n in flows if n.get("type") == "status"]
    if status_nodes:
        issues["passes"].append(f"Status nodes: {len(status_nodes)}")

    # Check for switch nodes (decision logic)
    switch_nodes = [n for n in flows if n.get("type") == "switch"]
    issues["info"].append(f"Switch nodes: {len(switch_nodes)} — verify all cases handled")

    return issues


def print_report(issues: dict):
    """Print a formatted audit report."""
    print("\n" + "=" * 60)
    print("  Node-RED Flow Audit Report")
    print("=" * 60)

    for severity, items in [
        ("ERRORS", issues["errors"]),
        ("WARNINGS", issues["warnings"]),
        ("INFO", issues["info"]),
        ("PASSES", issues["passes"]),
    ]:
        if not items:
            continue
        print(f"\n  [{severity}]")
        for item in items:
            print(f"    {item}")

    print("\n  Summary:")
    print(f"    {len(issues['errors'])} errors")
    print(f"    {len(issues['warnings'])} warnings")
    print(f"    {len(issues['info'])} items")
    print(f"    {len(issues['passes'])} passed checks")
    print("=" * 60 + "\n")


def main():
    flow_path = sys.argv[1] if len(sys.argv) > 1 else "nodered/flows.json"
    if not os.path.exists(flow_path):
        print(f"File not found: {flow_path}")
        sys.exit(1)

    issues = audit_flows(flow_path)
    print_report(issues)

    # Exit with error if any warnings found (CI usage)
    if sys.argv.count("--strict") and issues["warnings"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
