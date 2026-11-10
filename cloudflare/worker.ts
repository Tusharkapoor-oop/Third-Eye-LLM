import { DurableObject } from "cloudflare:workers";

interface Env {
  WEBLENS_CONTAINER: DurableObjectNamespace<WebLensContainer>;
  WEBLENS_INSTANCE_COUNT: string;
  WEBLENS_CONTAINER_INSTANCE: string;
  WEBLENS_MCP_PROFILE: string;
  WEBLENS_SEARCH_PROVIDERS: string;
  WEBLENS_SUPPLEMENT_PROVIDERS: string;
  WEBLENS_FUSE_SOFT_TIMEOUT_S?: string;
  WEBLENS_FUSE_GRACE_S?: string;
  WEBLENS_FUSE_EARLY_MIN_EXTRA?: string;
  WEBLENS_FUSE_EARLY_MIN_DOMAINS?: string;
  WEBLENS_LOG_LEVEL: string;
  WEBLENS_API_KEY?: string;
  WEBLENS_API_KEYS?: string;
  TAVILY_API_KEY?: string;
  BRAVE_SEARCH_API_KEY?: string;
  SEARXNG_URL?: string;
}

type ContainerSize = "lite" | "basic" | "standard-1" | "standard-2" | "standard-3" | "standard-4";

const PORT = 8080;
const DEFAULT_INSTANCE_COUNT = 3;
const MAX_INSTANCE_COUNT = 10;
const INACTIVITY_TIMEOUT_MS = 2 * 60 * 60 * 1000;
const READY_ATTEMPTS = 100;
const READY_DELAY_MS = 250;

const CORS_HEADERS: Record<string, string> = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, POST, DELETE, OPTIONS",
  "access-control-allow-headers":
    "Authorization, Content-Type, X-API-Key, Mcp-Session-Id, MCP-Protocol-Version, Accept, Last-Event-ID",
  "access-control-expose-headers": "Mcp-Session-Id",
  "access-control-max-age": "86400",
};

function jsonResponse(body: unknown, status = 200, extraHeaders: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...CORS_HEADERS,
      ...extraHeaders,
    },
  });
}

function withCors(response: Response): Response {
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(CORS_HEADERS)) {
    headers.set(name, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function corsPreflight(): Response {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}

function extractToken(request: Request): string {
  const authorization = request.headers.get("authorization");
  if (authorization) {
    const [scheme, ...rest] = authorization.trim().split(/\s+/);
    if (scheme.toLowerCase() === "bearer" && rest.length > 0) {
      return rest.join(" ").trim();
    }
  }
  return request.headers.get("x-api-key")?.trim() ?? "";
}

function parseApiKeys(raw: string | undefined): string[] {
  if (!raw) return [];
  const trimmed = raw.trim();
  if (!trimmed) return [];

  if (trimmed.startsWith("{")) {
    try {
      const parsed = JSON.parse(trimmed) as Record<string, unknown>;
      return [
        ...new Set(
          Object.values(parsed).filter(
            (value): value is string => typeof value === "string" && value.length > 0,
          ),
        ),
      ];
    } catch {
      // Fall through to the tenant=key comma format.
    }
  }

  return [
    ...new Set(
      trimmed
        .split(",")
        .map((part) => {
          const separator = part.indexOf("=");
          return (separator === -1 ? part : part.slice(separator + 1)).trim();
        })
        .filter((value) => value.length > 0),
    ),
  ];
}

function configuredKeys(env: Env): string[] {
  const keys = [env.WEBLENS_API_KEY, ...parseApiKeys(env.WEBLENS_API_KEYS)]
    .filter((value): value is string => typeof value === "string")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
  return [...new Set(keys)];
}

async function sha256(value: string): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
}

function timingSafeEqual(left: Uint8Array, right: Uint8Array): boolean {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let i = 0; i < left.length; i += 1) {
    difference |= left[i] ^ right[i];
  }
  return difference === 0;
}

async function isAuthorized(request: Request, env: Env): Promise<boolean> {
  const token = extractToken(request);
  if (!token) return false;

  const keys = configuredKeys(env);
  if (keys.length === 0) return false;

  const presented = await sha256(token);
  const expected = await Promise.all(keys.map(sha256));
  return expected.some((candidate) => timingSafeEqual(presented, candidate));
}

function instanceCount(env: Env): number {
  const parsed = Number.parseInt(env.WEBLENS_INSTANCE_COUNT ?? "", 10);
  if (!Number.isFinite(parsed)) return DEFAULT_INSTANCE_COUNT;
  return Math.max(1, Math.min(MAX_INSTANCE_COUNT, parsed));
}

// Stable tenant affinity keeps a token on the same instance. That matters for
// the per-tenant SQLite state used by stateful tools; it is not a global store.
function affinityIndex(token: string, count: number): number {
  let hash = 2166136261;
  for (let i = 0; i < token.length; i += 1) {
    hash ^= token.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) % count;
}

function containerSize(env: Env): ContainerSize {
  const value = env.WEBLENS_CONTAINER_INSTANCE;
  switch (value) {
    case "lite":
    case "basic":
    case "standard-1":
    case "standard-2":
    case "standard-3":
    case "standard-4":
      return value;
    default:
      return "standard-1";
  }
}

function containerEnvironment(env: Env): Record<string, string> {
  const variables: Record<string, string> = {
    WEBLENS_HTTP_HOST: "0.0.0.0",
    WEBLENS_HTTP_PORT: String(PORT),
    WEBLENS_MCP_PROFILE: env.WEBLENS_MCP_PROFILE ?? "full",
    WEBLENS_SEARCH_PROVIDERS:
      env.WEBLENS_SEARCH_PROVIDERS ?? "tavily,mwmbl,wikipedia,bing,yahoo",
    WEBLENS_SUPPLEMENT_PROVIDERS:
      env.WEBLENS_SUPPLEMENT_PROVIDERS ?? "stackexchange",
    // Hosted fast path: stop a short grace after Tavily fills the visible
    // window. Keyless pools never early-stop (see config.py).
    WEBLENS_FUSE_SOFT_TIMEOUT_S: env.WEBLENS_FUSE_SOFT_TIMEOUT_S ?? "2.0",
    WEBLENS_FUSE_GRACE_S: env.WEBLENS_FUSE_GRACE_S ?? "0.25",
    WEBLENS_FUSE_EARLY_MIN_EXTRA: env.WEBLENS_FUSE_EARLY_MIN_EXTRA ?? "0",
    WEBLENS_FUSE_EARLY_MIN_DOMAINS: env.WEBLENS_FUSE_EARLY_MIN_DOMAINS ?? "3",
    WEBLENS_LOG_LEVEL: env.WEBLENS_LOG_LEVEL ?? "INFO",
    WEBLENS_TRUST_PROXY_HEADERS: "true",
    // The container is private to this Worker. The Worker validates the
    // inbound token and rewrites Host, so transport Host/Origin allowlists
    // would only reject the forwarded request.
    WEBLENS_ALLOWED_HOSTS: "",
    WEBLENS_ALLOWED_ORIGINS: "",
    WEBLENS_CACHE_DIR: "/tmp/weblens",
    WEBLENS_CACHE_BACKEND: "sqlite",
    PYTHONUNBUFFERED: "1",
  };

  if (env.WEBLENS_API_KEY) variables.WEBLENS_HTTP_TOKEN = env.WEBLENS_API_KEY;
  if (env.WEBLENS_API_KEYS) variables.WEBLENS_API_KEYS = env.WEBLENS_API_KEYS;
  if (env.TAVILY_API_KEY) variables.TAVILY_API_KEY = env.TAVILY_API_KEY;
  if (env.BRAVE_SEARCH_API_KEY) variables.BRAVE_SEARCH_API_KEY = env.BRAVE_SEARCH_API_KEY;
  if (env.SEARXNG_URL) variables.SEARXNG_URL = env.SEARXNG_URL;

  return variables;
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export class WebLensContainer extends DurableObject<Env> {
  private starting: Promise<void> | undefined;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    const container = ctx.container;
    if (container?.running) {
      void ctx.blockConcurrencyWhile(() => container.setInactivityTimeout(INACTIVITY_TIMEOUT_MS));
    }
  }

  async fetch(request: Request): Promise<Response> {
    this.starting ??= this.startAndWaitForPort().finally(() => {
      this.starting = undefined;
    });
    await this.starting;

    const url = new URL(request.url);
    url.protocol = "http:";
    url.host = "container";
    if (url.pathname === "/mcp/") {
      url.pathname = "/mcp";
    }

    const forwarded = new Request(url, request);
    forwarded.headers.delete("host");
    forwarded.headers.set("x-forwarded-proto", "https");

    // Never trust an inbound X-Forwarded-For. Cloudflare's CF-Connecting-IP is
    // authoritative at the Worker edge.
    const clientIp = request.headers.get("cf-connecting-ip");
    if (clientIp) {
      forwarded.headers.set("x-forwarded-for", clientIp);
    } else {
      forwarded.headers.delete("x-forwarded-for");
    }

    return this.ctx.container!.getTcpPort(PORT).fetch(forwarded);
  }

  private async startAndWaitForPort(): Promise<void> {
    const container = this.ctx.container!;

    if (!container.running) {
      container.start({
        image: container.images.base,
        instance: containerSize(this.env),
        enableInternet: true,
        env: containerEnvironment(this.env),
      });
    }

    await container.setInactivityTimeout(INACTIVITY_TIMEOUT_MS);

    const port = container.getTcpPort(PORT);
    let lastError: unknown;
    for (let attempt = 0; attempt < READY_ATTEMPTS; attempt += 1) {
      try {
        const response = await port.fetch("http://container/healthz", {
          signal: AbortSignal.timeout(2000),
        });
        await response.body?.cancel();
        if (!response.ok) {
          throw new Error(`Container health check returned ${response.status}`);
        }
        return;
      } catch (error) {
        lastError = error;
        await sleep(READY_DELAY_MS);
      }
    }

    throw new Error("WebLens container did not become ready on port 8080", {
      cause: lastError,
    });
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return corsPreflight();
    }

    if (url.pathname === "/healthz") {
      return jsonResponse({
        status: "ok",
        service: "weblens-edge",
        mcp_endpoint: "/mcp",
      });
    }

    if (url.pathname === "/") {
      return jsonResponse({
        service: "weblens-edge",
        status: "ok",
        mcp_endpoint: "/mcp",
        health: "/healthz",
        readiness: "/readyz",
        instances: instanceCount(env),
        auth: "Authorization: Bearer <token> or X-API-Key: <token>",
      });
    }

    if (url.pathname === "/readyz") {
      if (configuredKeys(env).length === 0) {
        return jsonResponse(
          {
            status: "unavailable",
            service: "weblens-edge",
            error: "server_misconfigured",
          },
          503,
        );
      }

      try {
        const readiness = await env.WEBLENS_CONTAINER.getByName("instance-0").fetch(
          new Request("http://weblens/healthz", {
            method: "GET",
            headers: { "x-forwarded-proto": "https" },
          }),
        );
        return withCors(readiness);
      } catch (error) {
        console.error("WebLens readiness check failed", error);
        return jsonResponse({ status: "unavailable", service: "weblens-edge" }, 503);
      }
    }

    const isMcp = url.pathname === "/mcp" || url.pathname === "/mcp/";
    if (!isMcp) {
      return jsonResponse({ error: "not_found" }, 404);
    }

    if (configuredKeys(env).length === 0) {
      return jsonResponse(
        {
          error: "server_misconfigured",
          detail: "Set the WEBLENS_API_KEY or WEBLENS_API_KEYS Worker secret before using /mcp.",
        },
        503,
      );
    }

    if (!(await isAuthorized(request, env))) {
      return jsonResponse(
        { error: "unauthorized" },
        401,
        { "www-authenticate": "Bearer" },
      );
    }

    const token = extractToken(request);
    const index = affinityIndex(token, instanceCount(env));

    try {
      const response = await env.WEBLENS_CONTAINER.getByName(`instance-${index}`).fetch(request);
      return withCors(response);
    } catch (error) {
      console.error("WebLens container request failed", error);
      return jsonResponse({ error: "container_unavailable" }, 503);
    }
  },
} satisfies ExportedHandler<Env>;
