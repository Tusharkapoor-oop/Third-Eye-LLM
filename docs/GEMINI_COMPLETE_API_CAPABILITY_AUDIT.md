# Google Gemini: Complete API & Capability Audit (V10)

## Executive Summary
This audit provides a comprehensive, technical assessment of the Google Gemini API ecosystem, developer interfaces, model families, tool capabilities, and architectural integration points for the WebLens Four-System Evaluation Lab.

## 1. SDK & Transport Architecture
- **Primary SDK**: `google-genai` (modern unified SDK, package version `>=2.34.0`).
- **REST Protocol**: `https://generativelanguage.googleapis.com/v1beta/` (Developer API) and `https://aiplatform.googleapis.com/v1/` (Enterprise Vertex AI).
- **Authentication**:
  - Developer API: `GEMINI_API_KEY` or `GOOGLE_API_KEY` query parameter / header.
  - Vertex AI: OAuth2 Bearer token with Google Cloud Application Default Credentials (ADC).
- **Core Operations**:
  - `client.models.generate_content`: Single-turn and multi-turn text, multimodal, and tool-augmented generation.
  - `client.chats.create`: Stateful conversational sessions.
  - `client.interactions`: Background tasks, asynchronous interactions, and agent execution.

## 2. Model Family & Parameter Specifications

| Model ID | Context Window | Output Cap | Multimodal | Search Grounding | Code Execution | Thinking Mode |
|---|---|---|---|---|---|---|
| `gemini-2.5-pro` | 2,000,000 tokens | 8,192 tokens | Text, Audio, Video, PDF | Supported | Supported | Supported |
| `gemini-2.5-flash` | 1,000,000 tokens | 8,192 tokens | Text, Audio, Video, PDF | Supported | Supported | Supported |
| `gemini-2.0-flash` | 1,048,576 tokens | 8,192 tokens | Text, Image, Audio, Video | Supported | Supported | Supported |
| `gemini-2.0-flash-thinking-exp-01-21` | 1,048,576 tokens | 65,536 tokens | Text, Image | Supported | Supported | Native Thinking |
| `gemini-1.5-pro` | 2,097,152 tokens | 8,192 tokens | Text, Image, Audio, Video | Supported | Supported | Prompt-guided |
| `gemini-1.5-flash` | 1,048,576 tokens | 8,192 tokens | Text, Image, Audio, Video | Supported | Supported | Prompt-guided |

## 3. Native Tools & Capabilities
1. **Google Search Grounding**:
   - Enabled via `types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])`.
   - Returns structured `grounding_metadata` with `web_search_queries`, `grounding_chunks` (URL, title), and `grounding_supports` (passage text, segment indices, confidence scores).
2. **Code Execution**:
   - Sandboxed Python code interpreter executed by Google backend to perform exact mathematical calculations and data manipulation.
3. **Structured Outputs**:
   - `response_mime_type="application/json"` with Pydantic / JSON schema enforcement.
4. **Context Caching**:
   - Implicit caching for prompts exceeding 32k tokens.
   - Explicit caching via `client.caches.create` for large invariant document corpora.
5. **Function Calling & MCP Integration**:
   - Function declaration schema adheres to OpenAPI 3.0 / JSON Schema.
   - Supports tool calling where the model emits tool call requests and ingests tool response blocks.

## 4. Gemini Deep Research
- **Nature**: Asynchronous agentic deep research system.
- **Workflow**: Formulates multi-step research plan -> executes multi-hop search & browse -> inspects contradictory sources -> synthesizes long-form referenced report.
- **API Availability**: Accessible via Google Workspace Gemini Advanced and specialized developer preview endpoints.
- **Disposition for Evaluation**: If account tier or endpoint restricts Deep Research task creation, marked as `BLOCKED: REQUIRE_PREVIEW_ENTITLEMENT` with exact HTTP status documented, falling back to Mode G1 (Gemini 2.5 Flash Grounded Search) and Mode G2 (Gemini + WebLens MCP).

