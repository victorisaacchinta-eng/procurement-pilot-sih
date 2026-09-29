"""
Reasoning layer: one real tool-calling step over an OpenAI-compatible API.

The model gets the tender spec and one tool, get_requirement_checks. It decides
to call it, reads the real results, and writes a recommendation in plain
language. It never sets the verdict or the score; those come from checks.py.

Provider is configuration, not code. Any OpenAI-compatible chat-completions
endpoint works: a hosted API, a sovereign/Indian provider, or a local model via
Ollama or vLLM. Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL.

If no key is set, or the call fails or times out, the endpoint falls back to a
deterministic summary and says so. The officer always sees every check.
"""
import os
import json
import urllib.request
import urllib.error

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.cerebras.ai/v1").rstrip("/")
LLM_API_KEY = (os.environ.get("LLM_API_KEY") or os.environ.get("CEREBRAS_API_KEY") or "").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-oss-120b")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "25"))

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

SYSTEM_PROMPT = (
    "You are the reasoning layer inside Procurement Pilot, a bid compliance tool used by government procurement "
    "officers. You assist a human officer and never make the decision. Call get_requirement_checks, then write a short, "
    "specific recommendation in plain language. Name every FLAG and FAIL and say what the officer should verify in "
    "person. Use only facts from the check results. Do not invent documents, numbers or history. No markdown."
)


def configured() -> bool:
    return bool(LLM_API_KEY)


def _post(payload: dict) -> dict:
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
    try:
        first = _post({"model": LLM_MODEL, "messages": messages, "tools": TOOLS, "tool_choice": "auto", "max_tokens": 700})
        msg = first["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if calls:
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for call in calls:
                if call.get("function", {}).get("name") == "get_requirement_checks":
                    result = {"checks": [{k: c[k] for k in ("name", "status", "reason")} for c in checks],
                              "compliance_score": score, "verdict": verdict}
                else:
                    result = {"error": "unknown tool"}
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": json.dumps(result)})
            final = _post({"model": LLM_MODEL, "messages": messages, "max_tokens": 500})
            text = (final["choices"][0]["message"].get("content") or "").strip()
        else:
            text = (msg.get("content") or "").strip()
        if not text:
            return fallback
        return {"ai_reasoning": text, "ai_source": f"model:{LLM_MODEL}"}
    except urllib.error.HTTPError as e:
        # Status and the provider's error code only; never the request, which carries the key.
        detail = ""
        try:
            body = json.loads(e.read().decode() or "{}")
            err = body.get("error") if isinstance(body.get("error"), dict) else body  # OpenAI-style or flat
            code = str(err.get("code") or err.get("type") or "")[:60]
            detail = f" {code}" if code else ""
        except (ValueError, OSError):
            pass
        print(f"[llm] HTTP {e.code}{detail} from {LLM_BASE_URL} model={LLM_MODEL}", flush=True)
        fallback["ai_reasoning"] += f"\n(Reasoning layer unavailable this run: HTTP {e.code}{detail}. The checks above are unaffected.)"
        return fallback
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as e:
        print(f"[llm] {type(e).__name__} from {LLM_BASE_URL}", flush=True)
        fallback["ai_reasoning"] += f"\n(Reasoning layer unavailable this run: {type(e).__name__}. The checks above are unaffected.)"
        return fallback
