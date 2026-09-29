"""
Reasoning layer: one real tool-calling step over an OpenAI-compatible API.

The model gets the tender spec and one tool, get_requirement_checks. It decides
to call it, reads the real results, and writes a recommendation in plain
language. It never sets the verdict or the score; those come from checks.py.

Provider is configuration, not code. Any OpenAI-compatible chat-completions
endpoint works. Production uses Sarvam (sarvam-105b, an Indian model):
  LLM_BASE_URL=https://api.sarvam.ai/v1  LLM_MODEL=sarvam-105b  LLM_API_KEY=...
A local model via Ollama or vLLM works the same way.

If no key is set, or the call fails or times out, the endpoint falls back to a
deterministic summary and says so. The officer always sees every check.
"""
import os
import re
import json
import urllib.request
import urllib.error

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.cerebras.ai/v1").rstrip("/")
LLM_API_KEY = (os.environ.get("LLM_API_KEY") or os.environ.get("CEREBRAS_API_KEY") or "").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-oss-120b")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "45"))
MAX_TOOL_ROUNDS = 3
# "on": the model fetches the check results through a tool call (two round trips; best on fast providers).
# "off" (default): the check results go straight into the prompt (one round trip; better for slower models).
LLM_TOOL_CALLING = os.environ.get("LLM_TOOL_CALLING", "off").strip().lower() in ("1", "on", "true", "yes")
# Optional, only sent when set: "low"/"high"/"max", or "none" to send null and switch hidden reasoning off (Sarvam).
LLM_REASONING_EFFORT = os.environ.get("LLM_REASONING_EFFORT", "").strip()

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_requirement_checks",
        "description": ("Returns the ten deterministic compliance checks for this bidder against this tender: EMD, statutory "
                        "documents, financial turnover, price reasonability, entity name consistency, registry verification, "
                        "debarment, public interest screening, shell company indicators and past performance, plus the score."),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}]

SYSTEM_PROMPT_DIRECT = (
    "You are the reasoning layer inside Procurement Pilot, a bid compliance tool used by government procurement "
    "officers. You assist a human officer and never make the decision. You are given the results of ten deterministic "
    "checks. Write a recommendation in plain language, under 110 words, in two short paragraphs. First paragraph: each "
    "check that is FLAG or FAIL, with its status copied exactly, what it found, and what the officer should verify in "
    "person. Do not list checks that passed. If none failed or flagged, say so in one sentence. Second paragraph: any "
    "requirement in the tender specification that no check covers (for example a technical certification). Checks that "
    "passed are covered; never call them unverified. Use only facts given. Do not invent documents, numbers or history. "
    "Do not repeat these instructions. No markdown, no headings."
)

SYSTEM_PROMPT = (
    "You are the reasoning layer inside Procurement Pilot, a bid compliance tool used by government procurement "
    "officers. You assist a human officer and never make the decision. Call get_requirement_checks, then write a short, "
    "specific recommendation in plain language. Name every FLAG and FAIL and say what the officer should verify in "
    "person. Quote each check's status exactly as given (PASS, FLAG or FAIL); never soften or change one. Use only facts "
    "from the check results. Do not invent documents, numbers or history. No markdown."
)


def configured() -> bool:
    return bool(LLM_API_KEY)


def _post(payload: dict) -> dict:
    if LLM_REASONING_EFFORT.lower() in ("none", "null", "off"):
        # Sarvam: an explicit null disables hidden reasoning (their advice for latency-sensitive calls).
        payload = dict(payload, reasoning_effort=None)
    elif LLM_REASONING_EFFORT:
        payload = dict(payload, reasoning_effort=LLM_REASONING_EFFORT)
    req = urllib.request.Request(
        f"{LLM_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode(),
        # A named User-Agent matters: some providers sit behind Cloudflare, which rejects
        # Python's default "Python-urllib" agent with a bare 403 (error 1010).
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {LLM_API_KEY}",
                 "User-Agent": "procurement-pilot/2.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
        return json.loads(r.read().decode())


def _clean(text: str) -> str:
    """Drop any visible chain-of-thought block a reasoning model leaves in the content."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    return text.strip()


def deterministic_summary(bidder_name: str, checks: list, score: int, verdict: str) -> str:
    bad = [c for c in checks if c["status"] != "PASS"]
    if not bad:
        return (f"All ten checks passed for {bidder_name}. Nothing needs officer attention beyond the standard sign-off.")
    lines = [f"{len(bad)} of 10 checks need attention for {bidder_name} (score {score}, {verdict.lower()})."]
    for c in bad:
        lines.append(f"{c['name']} ({c['status']}): {c['reason']}")
    lines.append("Verify these in person before recording a decision.")
    return "\n".join(lines)


def reason(tender: dict, bidder_name: str, checks: list, score: int, verdict: str) -> dict:
    fallback = {"ai_reasoning": deterministic_summary(bidder_name, checks, score, verdict), "ai_source": "deterministic"}
    if not configured():
        return fallback
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (f"Tender: {tender['title']}\nMandatory specification: {tender['spec']}\n"
                                     f"Bidder: {bidder_name}\nEvaluate this bid and give your recommendation.")},
    ]
    step = "first call"
    if not LLM_TOOL_CALLING:
        results = {"checks": [{k: c[k] for k in ("name", "status", "reason")} for c in checks],
                   "compliance_score": score, "verdict": verdict}
        direct = [
            {"role": "system", "content": SYSTEM_PROMPT_DIRECT},
            {"role": "user", "content": (f"Tender: {tender['title']}\nMandatory specification: {tender['spec']}\n"
                                         f"Bidder: {bidder_name}\nCheck results: {json.dumps(results)}\n"
                                         "Write your recommendation.")},
        ]
    try:
        if not LLM_TOOL_CALLING:
            resp = _post({"model": LLM_MODEL, "messages": direct, "max_tokens": 3000})
            choice = resp["choices"][0]
            text = _clean(choice["message"].get("content") or "")
            if not text:
                why = f"finish_reason={choice.get('finish_reason')}"
                fallback["ai_reasoning"] += f"\n(Reasoning layer returned no text this run, {why}. The checks above are unaffected.)"
                return fallback
            return {"ai_reasoning": text, "ai_source": f"model:{LLM_MODEL}"}
        # Tool loop. The tool list is sent on every round: some providers (Sarvam) reject a
        # conversation that contains tool messages unless tools are also provided.
        text, why = "", ""
        for round_no in range(1, MAX_TOOL_ROUNDS + 1):
            step = "first call" if round_no == 1 else f"call {round_no}"
            have_results = any(m["role"] == "tool" for m in messages)
            # Once the check results are in, ask for the written answer only (no more tool calls),
            # with room for a reasoning model's hidden thinking.
            resp = _post({"model": LLM_MODEL, "messages": messages, "tools": TOOLS,
                          "tool_choice": "none" if have_results else "auto",
                          "max_tokens": 3000 if have_results else 1500})
            choice = resp["choices"][0]
            msg = choice["message"]
            calls = msg.get("tool_calls") or []
            if not calls or have_results:
                text = _clean(msg.get("content") or "")
                why = f"finish_reason={choice.get('finish_reason')}"
                break
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for call in calls:
                if call.get("function", {}).get("name") == "get_requirement_checks":
                    result = {"checks": [{k: c[k] for k in ("name", "status", "reason")} for c in checks],
                              "compliance_score": score, "verdict": verdict}
                else:
                    result = {"error": "unknown tool"}
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": json.dumps(result)})
        if not text:
            print(f"[llm] empty answer on {step} ({why or 'tool rounds exhausted'}) model={LLM_MODEL}", flush=True)
            fallback["ai_reasoning"] += f"\n(Reasoning layer returned no text this run, {why or 'tool rounds exhausted'}. The checks above are unaffected.)"
            return fallback
        return {"ai_reasoning": text, "ai_source": f"model:{LLM_MODEL}"}
    except urllib.error.HTTPError as e:
        # Status and the provider's error code only; never the request, which carries the key.
        detail = ""
        try:
            body = json.loads(e.read().decode() or "{}")
            err = body.get("error") if isinstance(body.get("error"), dict) else body  # OpenAI-style or flat
            code = str(err.get("code") or err.get("type") or "")[:60]
            msg = str(err.get("message") or "")[:220]
            detail = (f" {code}" if code else "") + (f" on {step}: {msg}" if msg else f" on {step}")
        except (ValueError, OSError):
            pass
        print(f"[llm] HTTP {e.code}{detail} from {LLM_BASE_URL} model={LLM_MODEL}", flush=True)
        fallback["ai_reasoning"] += f"\n(Reasoning layer unavailable this run: HTTP {e.code}{detail}. The checks above are unaffected.)"
        return fallback
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as e:
        print(f"[llm] {type(e).__name__} from {LLM_BASE_URL}", flush=True)
        fallback["ai_reasoning"] += f"\n(Reasoning layer unavailable this run: {type(e).__name__}. The checks above are unaffected.)"
        return fallback
