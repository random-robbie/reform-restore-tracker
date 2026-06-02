import re
import json
import requests

LLM_BASE_URL = "http://192.168.1.231:8000/v1"
LLM_MODEL    = "minimax-m2.7"
BILLS_API    = "https://bills-api.parliament.uk/api/v1/Bills"

_bill_cache: dict[str, str] = {}

VALID_IMPACT = {"helps", "hurts", "neutral", "mixed"}

SYSTEM = "Think briefly. Output JSON only. No extra text."

USER_TMPL = """UK Parliament vote: {title}
{context_line}Result: Ayes {aye_count} Noes {no_count} {result}

Output only valid JSON with these exact keys:
{{"plain_explanation":"2-3 sentences explaining the vote in plain English","working_class_impact":"helps|hurts|neutral|mixed","working_class_reason":"1-2 sentences on impact for workers/wages/jobs/housing/NHS","business_impact":"helps|hurts|neutral|mixed","business_reason":"1-2 sentences on impact for businesses","women_children_impact":"helps|hurts|neutral|mixed","women_children_reason":"1-2 sentences on impact for women, children and family safety/welfare","public_impact":"2-3 sentences on day-to-day impact for ordinary people","impact_summary":"one punchy sentence: who wins and who loses"}}"""

PATCH_TMPL = """UK Parliament vote: {title}
{context_line}Result: Ayes {aye_count} Noes {no_count} {result}

Output only valid JSON with these exact keys:
{{"women_children_impact":"helps|hurts|neutral|mixed","women_children_reason":"1-2 sentences on impact for women, children and family safety/welfare"}}"""


def _bill_context(title: str) -> str:
    name = title.split(":")[0].strip()
    if name in _bill_cache:
        return _bill_cache[name]
    try:
        r = requests.get(BILLS_API, params={"SearchTerm": name, "take": 1},
                         headers={"Accept": "application/json"}, timeout=8)
        r.raise_for_status()
        items = r.json().get("items", [])
        long_title = ""
        if items:
            long_title = items[0].get("longTitle", "") or ""
            if not long_title:
                bid = items[0].get("billId")
                r2  = requests.get(f"{BILLS_API}/{bid}", timeout=8)
                long_title = r2.json().get("longTitle", "") or ""
        _bill_cache[name] = long_title.strip()
    except Exception:
        _bill_cache[name] = ""
    return _bill_cache[name]


def _clean_impact(val: str) -> str:
    v = (val or "").lower().strip().split()[0]
    return v if v in VALID_IMPACT else "neutral"


def analyse_division(title: str, date: str, aye_count: int, no_count: int) -> dict:
    result  = "PASSED" if aye_count > no_count else "FAILED"
    context = _bill_context(title)
    ctx_line = f"Bill description: {context}\n" if context else ""

    user_msg = USER_TMPL.format(
        title=title, context_line=ctx_line,
        aye_count=aye_count, no_count=no_count, result=result,
    )

    payload = {
        "model":       LLM_MODEL,
        "messages":    [
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        "temperature": 0.1,
        "max_tokens":  8192,
    }
    resp = requests.post(f"{LLM_BASE_URL}/chat/completions", json=payload, timeout=120)
    resp.raise_for_status()
    raw  = resp.json()["choices"][0]["message"]["content"] or ""

    # Strip <think>...</think> reasoning (MiniMax / DeepSeek-R1 style)
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text).rstrip("`").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]+\}", text, re.DOTALL)
        if not m:
            raise ValueError(f"No JSON in response: {text[:300]}")
        data = json.loads(m.group(0))

    return {
        "plain_explanation":      data.get("plain_explanation", ""),
        "working_class_impact":   _clean_impact(data.get("working_class_impact", "")),
        "working_class_reason":   data.get("working_class_reason", ""),
        "business_impact":        _clean_impact(data.get("business_impact", "")),
        "business_reason":        data.get("business_reason", ""),
        "women_children_impact":  _clean_impact(data.get("women_children_impact", "")),
        "women_children_reason":  data.get("women_children_reason", ""),
        "public_impact":          data.get("public_impact", ""),
        "impact_summary":         data.get("impact_summary", ""),
    }


def patch_women_children(title: str, date: str, aye_count: int, no_count: int) -> dict:
    """Lightweight pass to add women_children fields to already-analysed divisions."""
    result  = "PASSED" if aye_count > no_count else "FAILED"
    context = _bill_context(title)
    ctx_line = f"Bill description: {context}\n" if context else ""

    user_msg = PATCH_TMPL.format(
        title=title, context_line=ctx_line,
        aye_count=aye_count, no_count=no_count, result=result,
    )
    payload = {
        "model":       LLM_MODEL,
        "messages":    [
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        "temperature": 0.1,
        "max_tokens":  4096,
    }
    resp = requests.post(f"{LLM_BASE_URL}/chat/completions", json=payload, timeout=120)
    resp.raise_for_status()
    raw  = resp.json()["choices"][0]["message"]["content"] or ""
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text).rstrip("`").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]+\}", text, re.DOTALL)
        if not m:
            raise ValueError(f"No JSON in response: {text[:300]}")
        data = json.loads(m.group(0))
    return {
        "women_children_impact": _clean_impact(data.get("women_children_impact", "")),
        "women_children_reason": data.get("women_children_reason", ""),
    }
