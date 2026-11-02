# WebLens Next Action & Continuous Improvement Procedure

## Next Recommended Tasks

1. **Scale Paired Benchmark**:
   - Execute a 100-query batch across held-out queries in `benchmarks/eval_dataset_expanded.json`.
   - Command:
     ```powershell
     .\.venv\Scripts\python.exe weblens-lab/evaluations/run_paired_evaluation.py
     ```
   - Monitor Tavily credits via `weblens-lab/adapters/tavily_adapter/adapter.py` `fetch_account_telemetry()`.

2. **Automated Headless Browser Fallback Integration**:
   - Install Playwright Chromium in the sandbox container to evaluate JS-rendered single-page applications.
   - Command:
     ```powershell
     .\.venv\Scripts\python.exe -m playwright install chromium
     ```

3. **Deploy Updated V8 Container to Cloud Run**:
   - Push new sandbox enhancements and workflow 9 to Cloud Run revision:
     ```powershell
     gcloud run deploy weblens --source . --region=us-central1 --allow-unauthenticated --port=8080 --project=sewasetu-prod-2026 --quiet
     ```

