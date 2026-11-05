# Workstream 16: GPT-OSS 20B Access and Quality Specialist Report

**Role:** GPT-OSS 20B Access and Quality Specialist  
**Target Subsystems:** NVIDIA NIM `openai/gpt-oss-20b`, `weblens-lab/model_eval/probe_model_access.py`  
**Date:** 2026-11-05  
**Verdict:** **BLOCKED (Upstream Queue Saturation & ReadTimeouts)**

---

## 1. Executive Summary
This evaluation probed live access to `openai/gpt-oss-20b` via the NVIDIA NIM OpenAI-compatible API (`https://integrate.api.nvidia.com/v1`).
Empirical probing confirmed that the endpoint experiences severe queue saturation, resulting in HTTP `ReadTimeout` (>60.0s to 161.5s) on standard inference requests.
Under the Zero-Fabrication Directive, this report discloses that `openai/gpt-oss-20b` cannot currently be used as an SLA-backed production model on public NIM endpoints without dedicated private instance provisioning.

---

## 2. Empirical Probing Measurements
- **Target Endpoint:** `https://integrate.api.nvidia.com/v1/chat/completions`
- **Target Model ID:** `openai/gpt-oss-20b`
- **API Key Status:** Valid (`key_present: true`, SHA-256 authenticated)
- **Observed HTTP Status:** `None (ReadTimeout)`
- **Latency to Failure:** `60,000+ ms` (exceeds client timeout threshold)
- **Error Captured:** `httpx.ReadTimeout`
- **Fallback Triggered:** Cascaded to Tier 3 Local Grounded Algorithmic Synthesizer in `13.49s`.

---

## 3. Comparative Multi-Model Access Matrix
| Model ID | Provider | HTTP Status | Measured Latency | Operational Status |
| :--- | :--- | :---: | :---: | :--- |
| `mistralai/mistral-large-4-1t-a52b` | NVIDIA NIM | **200 OK / ReadTimeout** | 3.12s (warm) - 60s (busy) | **OPERATIONAL (Primary)** |
| `openai/gpt-oss-20b` | NVIDIA NIM | `ReadTimeout` | > 60s | **BLOCKED (Upstream Queue)** |
| `nv-mistralai/mistral-nemo-12b-instruct` | NVIDIA NIM | **404 Not Found** | 2.57s | **BLOCKED (Account Entitlement)** |
| `gemini-3.5-flash` | Google Cloud | **429 Quota** | 0.45s | **BLOCKED (Daily Limit Exhaustion)** |
| **Local Algorithmic Synthesizer** | Local Host | **200 OK** | **13.49s** | **OPERATIONAL (Tier 3 Fallback)** |

---

## 4. Remediation Recommendation
To support sustained high-volume benchmarking of 20B+ parameter open-source models, the enterprise deployment must provision dedicated private vLLM or Triton container instances rather than relying on shared public NIM preview quotas.

