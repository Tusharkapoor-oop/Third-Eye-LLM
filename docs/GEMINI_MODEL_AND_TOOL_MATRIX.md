# Gemini Model & Tool Matrix (V10)

## Model Matrix

| Model Identifier | Primary Use Case | Context Size | Input Price ($/1M) | Output Price ($/1M) | Recommended Role |
|---|---|---|---|---|---|
| `gemini-2.5-flash` | Fast Research, Chat, Agent Tool Use | 1,000,000 | $0.075 | $0.30 | Primary Orchestrator |
| `gemini-2.5-pro` | Deep Synthesis, Complex Reasoning | 2,000,000 | $1.25 | $5.00 | Heavyweight Synthesis |
| `gemini-2.0-flash` | Ultra-low Latency Grounded Search | 1,048,576 | $0.10 | $0.40 | Real-time Search Evaluator |
| `gemini-2.0-flash-thinking-exp` | Multi-hop Analysis & Math Validation | 1,048,576 | Free Tier / Preview | Free Tier / Preview | Conflict Resolver |
| `text-embedding-004` | Semantic Retrieval & Embeddings | 2,048 | $0.025 | N/A | Vector Retrieval Baseline |

## Tool & Capability Matrix

| Tool Feature | API Parameter / Type | Supported Models | Output Metadata |
|---|---|---|---|
| **Google Search Grounding** | `types.Tool(google_search=types.GoogleSearch())` | All 2.0 / 2.5 / 1.5 models | `grounding_metadata` (sources, queries, supports) |
| **Code Execution** | `types.Tool(code_execution=types.ToolCodeExecution())` | Flash & Pro models | Code blocks & execution stdout |
| **Function Calling (MCP)** | `types.Tool(function_declarations=[...])` | All Gemini models | `function_calls` and tool arguments |
| **Structured Output** | `response_mime_type="application/json"` | All Gemini models | Enforced JSON schema payload |
| **Context Caching** | `client.caches.create(...)` | Pro & Flash models | Cached token discount (>32k tokens) |
| **Streaming** | `client.models.generate_content_stream()` | All Gemini models | Chunk-by-chunk delta tokens |

