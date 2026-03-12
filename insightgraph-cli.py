#!/usr/bin/env python3
"""
insightgraph-cli.py
Command Line Interface for InsightGraph Local CI/CD integration.
Usage: python insightgraph-cli.py /path/to/project --fail-on-high-risk
"""

import sys
import argparse
import asyncio
import httpx

INSIGHTGRAPH_API = "http://localhost:8000/api"

async def main():
    parser = argparse.ArgumentParser(description="InsightGraph CI/CD checker")
    parser.add_argument("project_path", help="Path to the project to scan")
    parser.add_argument("--fail-on-high-risk", action="store_true", help="Fail build if high risk antipatterns are found")
    args = parser.parse_args()

    print(f"[InsightGraph CLI] Starting scan for: {args.project_path}")
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        # Trigger scan
        try:
            res = await client.post(f"{INSIGHTGRAPH_API}/scan", json={"paths": [args.project_path]})
            res.raise_for_status()
        except httpx.ConnectError:
            print("[Error] InsightGraph backend is not running at http://localhost:8000")
            sys.exit(1)
            
        print("[InsightGraph CLI] Scan triggered. Waiting for completion...")
        
        # Poll for completion
        while True:
            await asyncio.sleep(2)
            status_res = await client.get(f"{INSIGHTGRAPH_API}/scan/status")
            status_data = status_res.json()
            if status_data["status"] == "completed":
                print(f"[InsightGraph CLI] Scan completed! Parou: {status_data['scanned_files']} arquivos.")
                break
            elif status_data["status"] == "error":
                print(f"[Error] Scan failed: {status_data['errors']}")
                sys.exit(1)
            else:
                progress = status_data.get('progress_percent', 0)
                sys.stdout.write(f"\rScanning... {progress:.1f}%")
                sys.stdout.flush()

        print("\n[InsightGraph CLI] Fetching antipatterns...")
        anti_res = await client.get(f"{INSIGHTGRAPH_API}/antipatterns")
        anti_data = anti_res.json()
        
        god_classes = anti_data.get("god_classes", [])
        circular_deps = anti_data.get("circular_dependencies", [])
        
        high_risk = False
        
        if god_classes:
            print(f"  ⚠️  Found {len(god_classes)} God Classes/Hotspots!")
            for n in god_classes[:5]:
                print(f"     - {n['name']} (Complexity: {n['complexity']}, I/O: {n['in_degree']}/{n['out_degree']})")
            if len(god_classes) > 5:
                print(f"     ... and {len(god_classes)-5} more.")
            high_risk = True
            
        if circular_deps:
            print(f"  🔄 Found {len(circular_deps)} Circular Dependencies!")
            for c in circular_deps[:3]:
                print(f"     - Path length {c['length']}: {' -> '.join(c['path'])}")
            high_risk = True
            
        if not high_risk:
            print("[InsightGraph CLI] ✅ Code looks clean. No critical architectural degradation found.")
            sys.exit(0)
        else:
            if args.fail_on_high_risk:
                print("\n[InsightGraph CLI] ❌ FAILED: High-risk architectural patterns detected. Refactor required.")
                sys.exit(1)
            else:
                print("\n[InsightGraph CLI] ⚠️ WARNING: Architectural degradation detected, but not blocking build.")
                sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
