# WebLens Product Identity, Operating Boundaries, and Principles

## 1. Fundamental Identity

WebLens is an evidence-first web-intelligence infrastructure tool designed specifically for autonomous AI agents, multi-agent frameworks, and external LLM workflows. It exposes structured search, content extraction, bounded crawling, lexical retrieval, and deep research capabilities via the standard Model Context Protocol (MCP) and JSON APIs.

Its primary purpose is to provide downstream AI agents with reliable, verifiable, source-attributed information retrieved from the live public web, enabling agents to reason over factual evidence rather than hallucinated or ungrounded training data.

---

## 2. Explicit Non-Goals & Boundaries

To preserve architectural focus and operational discipline, WebLens strictly defines what it is NOT:

1. **NOT an AI Browser for Human Users:** WebLens does not render graphical user interfaces, interactive browser tabs, or user-facing navigation bars.
2. **NOT a General Browser Automation Platform:** WebLens does not emulate arbitrary user actions, solve dynamic CAPTCHAs, automate shopping checkouts, or execute arbitrary client-side form submissions. Internal headless browser instances (such as Playwright) are employed strictly as retrieval engines for JavaScript-heavy static pages.
3. **NOT an Autonomous Task-Completion Agent:** WebLens does not decide downstream goals, plan multi-step business tasks, or act on behalf of end users. It provides the structured ground truth and citations; the client AI agent retains full responsibility for reasoning, planning, and taking action.
4. **NOT a ChatGPT or Gemini Replacement:** WebLens is not a conversational chatbot for consumer entertainment. It does not generate conversational fluff or synthetic answers without verbatim source grounding.
5. **NOT a User-Facing Deep Research App:** WebLens Deep Research is an infrastructure tool accessed via programmatic MCP calls (`weblens_research`, `weblens_app_deep_research`), returning structured citations, passages, and confidence scores rather than speculative essays.
6. **NOT a Search Result Aggregator Website:** WebLens is not a consumer search portal like DuckDuckGo or Google Search UI. It is an agent infrastructure utility.

---

## 3. Core Agentic Capabilities

WebLens equips downstream agents with nine primary operational capabilities:

1. **Multi-Provider Web Discovery:** Discovers relevant pages through keyless consensus routing (Bing, DuckDuckGo, Wikipedia, Mojeek, Mwmbl) with fallback to verified commercial engines without vendor lock-in.
2. **High-Fidelity Content Extraction:** Extracts readable main text, code blocks, structured tables, and metadata while stripping navigation chrome, advertisements, cookies, and boilerplate.
3. **Bounded Domain Crawling:** Traverses site hierarchies up to strict depth, page, and rate boundaries, immune to crawler traps, calendar loops, and recursive directory mirrors.
4. **Verbatim Passage Citations:** Maps every returned fact to character-span anchors in retrieved source documents, preserving cryptographic SHA-256 provenance hashes.
5. **Premise Validation and Abstention:** Detects false-premise, fictional, and unanswerable queries, explicitly returning abstention signals (`no_reliable_result`) rather than fabricating confidence.
6. **Zero-Trust Egress Defense:** Blocks Server-Side Request Forgery (SSRF) across IPv4 and IPv6 private, link-local, loopback, and cloud metadata addresses with DNS pinning and redirect verification.
7. **Prompt Injection Quarantine:** Scans retrieved web text for indirect prompt injection, instruction overrides, and canary extraction attempts, quarantining malicious payloads into structured data payloads.
8. **Structured Vertical Applications:** Exposes high-level specialized intelligence endpoints (Company Researcher, Market Researcher, Crawl2RAG, Sheets Batch Enrichment, Meeting Prep) directly over MCP.
9. **Keyless and Token-Efficient Architecture:** Minimizes token footprints by returning scored, relevant passages rather than raw multi-megabyte HTML dumps, keeping downstream LLM inference costs minimal.

---

## 4. Operating Principles

- **Evidence Precedes Assertion:** No claim is presented as fact unless backed by a retrievable, verifiable source passage.
- **Abstention over Fabrication:** When reliable evidence is absent or sources contradict without resolution, WebLens reports the gap rather than synthesizing an answer.
- **Surgical Token Footprint:** Output format prioritizes compact JSON schemas, explicit character-level spans, and token-bounded passages to maximize agent context window efficiency.
- **Defense in Depth:** All untrusted web content is treated as potentially adversarial data. Untrusted text is never executed as instructions.
- **Zero Lock-In:** Core search and extraction operate without mandatory paid API keys, providing self-contained independence for any AI agent deployment.

