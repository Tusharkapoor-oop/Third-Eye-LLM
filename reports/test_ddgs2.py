"""Test ddgs library directly."""
import sys
try:
    from ddgs import DDGS
    print("ddgs imported successfully")
    ddgs = DDGS()
    results = list(ddgs.text("capital of France", max_results=5))
    print(f"Direct results: {len(results)}")
    for r in results:
        print(f"  {r}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
