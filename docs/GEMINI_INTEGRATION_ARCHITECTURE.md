# Gemini Integration Architecture (V10)

This document establishes the execution topology and separation of concerns for the three Gemini operating modes evaluated in WebLens V10.

## Operating Modes

```
+-----------------------------------------------------------------------------------------+
|                               FOUR-SYSTEM EVALUATION LAB                                |
+-----------------------------------------------------------------------------------------+
        |                               |                            |
        v                               v                            v
  [SYSTEM 1]                      [SYSTEM 2]                   [SYSTEM 3]
Local WebLens MCP              Deployed WebLens MCP           Tavily Direct API
        |                               |                            |
        +-------------------------------+----------------------------+
                                        |
                                        v
                                   [SYSTEM 4]
                                GOOGLE GEMINI API
                                        |
       +--------------------------------+--------------------------------+
       |                                |                                |
       v                                v                                v
   [MODE G1]                        [MODE G2]                        [MODE G3]
Native Gemini                 Gemini + WebLens MCP                Gemini + Tavily
(Google Search Grounding)     (Gemini reasoning + WebLens)       (Gemini reasoning + Tavily)
```

### Mode G1: Native Gemini
- **Execution Path**: Gemini model directly invokes Google's native Search Grounding tool (`google_search`).
- **Telemetry**: Measures Google Search latency, Google grounding chunk alignment, and token overhead.
- **Provider Identity**: 100% native Google API.

### Mode G2: Gemini + WebLens MCP (Hybrid Power Mode)
- **Execution Path**: Gemini model receives WebLens MCP tool declarations (`web_search`, `extract_url`, `deep_research`). When an inquiry requires factual evidence, Gemini invokes WebLens MCP tools, consumes exact character span passages, and produces synthesized cited answers.
- **Telemetry**: Measures reasoning latency vs WebLens tool execution latency, tool invocation fidelity, and token conservation.

### Mode G3: Gemini + Tavily Direct API
- **Execution Path**: Gemini model orchestrates Tavily API search and extraction calls.
- **Telemetry**: Measures Tavily response ingestion, commercial credit consumption, and token inflation.

## Identity & Provenance Rules
1. Never conflate Mode G1 with Mode G2 or Mode G3.
2. Every benchmark result records `mode: "G1_native" | "G2_gemini_weblens" | "G3_gemini_tavily"`.
3. WebLens results in Mode G2 are never claimed as standalone search engine victories; they are evaluated as an agent-tool composition.

