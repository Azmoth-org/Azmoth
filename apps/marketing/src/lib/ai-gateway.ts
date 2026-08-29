/**
 * Chat completions through the Vercel AI Gateway — free tier.
 *
 * Why this exists: the previous backend (opencode.ai OpenAI-compatible
 * endpoint + third-party key) is being retired. Every Vercel team account
 * gets free AI Gateway Credits usable on a subset of models ("free-tier
 * eligible"), with per-model rate limits that are lower than the paid
 * tier. To absorb rate limits and provider outages we route every chat
 * request to an ordered chain of free-eligible models — the gateway itself
 * tries the fallbacks in order when the primary fails.
 *
 * Auth:
 *   - AI_GATEWAY_API_KEY  — dashboard-created key (local dev / CI)
 *   - VERCEL_OIDC_TOKEN   — auto-injected on Vercel deployments (production)
 *
 * Endpoint: https://ai-gateway.vercel.sh/v1 (OpenAI-compatible). The AI SDK
 * routes a plain "provider/model" string to the gateway integration and
 * forwards `providerOptions.gateway.models` as the per-request failover list.
 *
 * Chain — ALL free-tier eligible on the gateway (verified against
 * vercel.com/ai-gateway/models Aug 2026). Costs are what free credits are
 * charged per 1M tokens (input/output); they are NOT out-of-pocket until
 * the free credit balance is exhausted:
 *   deepseek/deepseek-v3.1            $0.25 / $0.95   ← primary (closest to the old deepseek-v4-flash behaviour)
 *   google/gemini-2.5-flash           $0.30 / $2.50
 *   openai/gpt-5-nano                 $0.05 / $0.40
 *   mistral/mistral-small             $0.10 / $0.30
 *   deepseek/deepseek-v3              $0.27 / $1.12
 *   xai/grok-4.1-fast-non-reasoning   $0.20 / $0.50
 *   alibaba/qwen3.7-flash             $0.03 / $0.13
 *   zai/glm-4.5-air                   $0.20 / $1.10
 *
 * NOTE: deepseek/deepseek-v4-flash is NOT free-tier eligible on the gateway.
 */

import { createOpenAI } from "@ai-sdk/openai";
import { isStepCount, streamText } from "ai";
import type { ModelMessage, ToolSet } from "ai";

/** Default free-tier chat chain, best quality first. */
export const FREE_CHAT_MODELS: readonly string[] = [
  "deepseek/deepseek-v3.1",
  "google/gemini-2.5-flash",
  "openai/gpt-5-nano",
  "mistral/mistral-small",
  "deepseek/deepseek-v3",
  "xai/grok-4.1-fast-non-reasoning",
  "alibaba/qwen3.7-flash",
  "zai/glm-4.5-air",
];

/**
 * Chain to use. An operator can override the order/content with
 * AI_GATEWAY_MODELS (comma-separated "provider/model" ids).
 */
export function modelChain(): readonly string[] {
  const pinned = process.env.AI_GATEWAY_MODELS?.split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return pinned && pinned.length > 0 ? pinned : FREE_CHAT_MODELS;
}

export function gatewayApiKey(): string {
  // Prefer the dashboard key; OIDC covers Vercel deployments (fresh token
  // injected at runtime). A stale local OIDC copy is harmless — it loses
  // the race to AI_GATEWAY_API_KEY and is never sent when the key exists.
  return process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN || "";
}

/**
 * Backend switch. The Vercel AI Gateway free tier is the target, but it
 * requires a credit card on file to unlock the free credits. Until that's
 * done we keep the legacy opencode path live as a drop-in fallback.
 *
 * Gateway is used when AI_GATEWAY_API_KEY is set AND AI_GATEWAY_ENABLED is
 * not explicitly "false". Set AI_GATEWAY_ENABLED=false to keep the legacy
 * backend; delete the flag (or set it to anything else) to go gateway-first.
 */
export function gatewayEnabled(): boolean {
  return Boolean(gatewayApiKey()) && process.env.AI_GATEWAY_ENABLED !== "false";
}

export class NoGatewayKeyError extends Error {
  constructor() {
    super(
      "AI_GATEWAY_API_KEY is not configured. Create one at " +
        "https://vercel.com/[team]/~/ai-gateway/api-keys and set it in the environment.",
    );
    this.name = "NoGatewayKeyError";
  }
}

/**
 * Stream a chat completion through the active backend with a fallback
 * chain. Returns a UIMessage stream Response (assistant-ui / useChat
 * compatible).
 *
 * - Gateway enabled: AI Gateway free-tier chain (primary + per-request
 *   gateway failover via providerOptions.gateway.models).
 * - Gateway disabled: legacy opencode backend (AI_API_KEY / AI_BASE_URL /
 *   AI_MODEL).
 *
 * @throws NoGatewayKeyError when the gateway is enabled but no key exists.
 */
export async function streamChatWithFallback(opts: {
  system: string;
  messages: ModelMessage[];
  tools?: ToolSet;
  maxSteps?: number;
  onFinish?: (result: { text: string }) => void | Promise<void>;
}): Promise<Response> {
  if (gatewayEnabled()) {
    const [primary, ...fallbacks] = modelChain();
    const result = streamText({
      model: primary, // "provider/model" → Vercel AI Gateway integration
      // Auth: the AI SDK reads AI_GATEWAY_API_KEY (or OIDC on Vercel) from
      // the environment automatically — gatewayApiKey() above only pre-flights.
      system: opts.system,
      messages: opts.messages,
      tools: opts.tools,
      stopWhen: opts.maxSteps ? isStepCount(opts.maxSteps) : undefined,
      onFinish: opts.onFinish,
      providerOptions:
        fallbacks.length > 0 ? { gateway: { models: fallbacks } } : undefined,
    });
    return result.toUIMessageStreamResponse();
  }

  // Legacy backend (opencode.ai OpenAI-compatible endpoint).
  const apiKey = process.env.AI_API_KEY;
  const baseUrl = process.env.AI_BASE_URL || "https://opencode.ai/zen/go/v1";
  const modelName = process.env.AI_MODEL || "deepseek-v4-flash";

  if (!apiKey) {
    throw new NoGatewayKeyError();
  }

  const provider = createOpenAI({ baseURL: baseUrl, apiKey });
  const result = streamText({
    model: provider.chat(modelName),
    system: opts.system,
    messages: opts.messages,
    tools: opts.tools,
    stopWhen: opts.maxSteps ? isStepCount(opts.maxSteps) : undefined,
    onFinish: opts.onFinish,
  });
  return result.toUIMessageStreamResponse();
}
