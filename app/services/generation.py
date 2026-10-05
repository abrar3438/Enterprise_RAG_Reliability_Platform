"""LLM answer generation over retrieved chunks, with a verification pass (CraftX, OpenAI-compatible)."""
import logging
import re
import time
import unicodedata

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v4"
REQUEST_TIMEOUT = 90.0
FIRST_MAX_TOKENS = 2000
RETRY_MAX_TOKENS = 4000
VERIFY_MAX_TOKENS = 1500
VERIFY_RETRY_MAX_TOKENS = 4000
LOW_BALANCE_BDT = 5.0
VERIFY_WITH_ALL_CHUNKS = False  # True: the verifier sees every retrieved chunk, not just the cited ones

SYSTEM_PROMPT = (
    "You answer questions about SEC 10-K filings using only the numbered sources provided. "
    "Rules: (1) Use only information in the sources. Never use outside knowledge or guess. "
    "(2) Cite every factual statement with its source number in plain square brackets with ASCII digits, like [1] or [2][3]. "
    "(3) Copy numbers exactly as written, with units, and always say which company and which filing date the figure comes from. "
    "(4) If the sources discuss a related topic but do not state the answer (for example a cost is mentioned but not the revenue asked for), do not infer or estimate it. "
    "(5) If the sources do not contain the answer, reply with exactly this sentence and nothing else: I could not find this in the provided filings. "
    "(6) Keep the answer to a few sentences. "
    "(7) Write plain text only: no markdown, no bold, no special bracket characters. "
    "(8) For every number, write the exact line-item name from the source next to it, for example 'Net income'. If the source shows a number without its line-item name, or the name does not match what was asked, do not use that number. "
    "(9) If the question asks for a specific measure, such as net income, total revenue or total assets, use only a figure labelled with that measure. "
    "(10) A table about a subset of the company, such as variable interest entities, a segment, a business line, a parent company alone, an average balance sheet or a single footnote, must not be used for a question about the whole company's total. Use only the consolidated statements for the fiscal year asked. "
    "(11) On a consolidated balance sheet, 'Total liabilities and stockholders' equity' equals total assets, so it may be used to answer a total assets question."
)

VERIFY_SYSTEM_PROMPT = (
    "You check an answer against source text. Reply with exactly one word: SUPPORTED or UNSUPPORTED. "
    "Say SUPPORTED only if every number in the answer appears in the sources, is labelled with the measure the question asks for "
    "(on a consolidated balance sheet, 'Total liabilities and stockholders' equity' counts as total assets), "
    "and refers to the scope the question asks about: the whole company on a consolidated basis and the fiscal year asked, "
    "not a subset such as a variable interest entity, a parent company alone, a segment, an average balance sheet, a single note or a different period. "
    "The company name, filing date and source numbers shown in each source label count as part of the sources."
)

REFUSAL_TEXT = "I could not find this in the provided filings."
REFUSAL_SENTENCE = "i could not find this in the provided filings"

_HEADER_RE = re.compile(r"\([A-Z][A-Z.\-]{0,7}\)\s+[^|]*\|")
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
_DAGGER_CITE_RE = re.compile(r"\[(\d+)\u2020[^\]]*\]")
_CITE_GROUP_RE = re.compile(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]")
_PARSE_ERRORS = (ValueError, KeyError, IndexError, TypeError, AttributeError)


def normalize_answer(text: str) -> str:
    """Make model output predictable: ASCII-style spaces, brackets and hyphens, no markdown bold."""
    text = unicodedata.normalize("NFKC", text or "")  # non-breaking and narrow spaces become normal spaces
    text = text.translate(_ZERO_WIDTH)
    for src, dst in (("\u3010", "["), ("\u3011", "]"), ("\u3014", "["), ("\u3015", "]")):
        text = text.replace(src, dst)  # lenticular and tortoise-shell brackets
    text = _DAGGER_CITE_RE.sub(r"[\1]", text)  # [1†L5-L9] -> [1]
    text = text.replace("**", "")
    for src in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212"):
        text = text.replace(src, "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_section(label) -> str:
    """Same cleaning as ingest: drop pipes and a trailing page number or range."""
    label = label or ""
    if "|" not in label:
        return re.sub(r"\s+", " ", label).strip()
    parts = [p.strip() for p in label.split("|")]
    while len(parts) > 1 and re.fullmatch(r"\d+(?:-\d+)?", parts[-1]):
        parts.pop()
    return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()


def _strip_header(content: str) -> str:
    """Remove the 'Company (TICKER) 10-K | Section' line that ingest prepends to each chunk."""
    first, sep, rest = (content or "").partition("\n")
    if sep and _HEADER_RE.search(first):
        return rest
    return content or ""


def _format_sources(pairs) -> str:
    """pairs: iterable of (source_number, chunk). Same labelled blocks for the answer and the verifier."""
    blocks = []
    for n, c in pairs:
        blocks.append(
            f"[{n}] {c.get('ticker', '')} | {c.get('filing_date', '')} | "
            f"{_clean_section(c.get('section'))}\n{c.get('content', '')}"
        )
    return "\n\n".join(blocks)


def _build_user_prompt(query: str, chunks: list[dict]) -> str:
    return f"Context:\n{_format_sources(enumerate(chunks, 1))}\n\nQuestion: {query}\n\nAnswer:"


def _parse_citations(answer: str, chunks: list[dict]) -> list[dict]:
    nums = set()
    for group in _CITE_GROUP_RE.findall(answer):  # [1], [2][3], [1, 2]
        nums.update(int(n) for n in re.findall(r"\d+", group))
    citations = []
    for n in sorted(nums):
        if 1 <= n <= len(chunks):
            c = chunks[n - 1]
            citations.append({
                "number": n,
                "ticker": c.get("ticker"),
                "filing_date": str(c.get("filing_date")),
                "section": _clean_section(c.get("section")),
                "preview": _strip_header(c.get("content") or "")[:200],
            })
    return citations


def _result(answer, chunks, *, error=None, usage=None, finish_reason=None, cost=None, balance=None,
            start=0.0, attempts=0, reasoning_chars=0, verification="skipped") -> dict:
    usage = usage or {}
    norm = re.sub(r"^[^a-z]+|[^a-z]+$", "", (answer or "").lower())
    out = {
        "answer": answer or "",
        "citations": _parse_citations(answer or "", chunks) if answer else [],
        "refused": bool(answer) and norm.startswith(REFUSAL_SENTENCE),
        "error": error,
        "prompt_version": PROMPT_VERSION,
        "model": settings.craftx_model,
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "finish_reason": finish_reason,
        "cost_bdt": cost,
        "balance_after": balance,
        "attempts": attempts,
        "reasoning_chars": reasoning_chars,
        "verification": verification,  # skipped | passed | failed | inconclusive
        "verification_error": None,
        "rejected_answer": None,  # log-only: never show this to users
    }
    if isinstance(balance, (int, float)) and balance < LOW_BALANCE_BDT:
        out["warning"] = f"Low CraftX balance: {balance}"
    return out


def _post_with_retry(payload: dict):
    """POST to CraftX. Returns (response, None) on HTTP 200, else (None, error message)."""
    headers = {
        "Authorization": f"Bearer {settings.craftx_api_key}",
        "Content-Type": "application/json",
    }
    retries = 0
    while True:
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                resp = client.post(settings.craftx_endpoint, headers=headers, json=payload)
        except httpx.RequestError as e:
            if retries < 1:
                retries += 1
                logger.warning("CraftX network error, retrying: %s", str(e)[:200])
                time.sleep(1)
                continue
            return None, f"Network error: {str(e)[:300]}"
        status = resp.status_code
        if status == 402:
            return None, "402 Payment Required (CraftX balance exhausted)"
        if status == 429 or status >= 500:
            if retries < 1:
                retries += 1
                logger.warning("CraftX returned %s, retrying", status)
                time.sleep(2 if status == 429 else 1)
                continue
            return None, f"Server or rate-limit error {status}"
        if status != 200:  # 400, 401, 403, 404, 422 and the rest: retrying will not help
            return None, f"Client error {status}"
        return resp, None


def _parse_response(resp) -> dict:
    data = resp.json()
    choice = data["choices"][0]
    message = choice["message"]
    cost = data.get("cost_bdt")
    balance = data.get("balance_after")
    return {
        "content": message.get("content") or "",
        "reasoning_chars": len(message.get("reasoning_content") or ""),
        "finish_reason": choice.get("finish_reason"),
        "usage": data.get("usage") or {},
        "cost": cost if isinstance(cost, (int, float)) else None,
        "balance": balance if isinstance(balance, (int, float)) else None,
    }


def _parse_verdict(raw: str):
    text = (raw or "").upper()
    if "UNSUPPORTED" in text or re.search(r"\bNOT\s+SUPPORTED\b", text):
        return "UNSUPPORTED"  # fail closed if the word appears at all
    if "SUPPORTED" in text:
        return "SUPPORTED"
    return None


def _verify(query: str, answer: str, cited) -> dict:
    """cited: list of (source_number, chunk). Asks the model whether the cited sources support the answer."""
    payload = {
        "model": settings.craftx_model,
        "messages": [
            {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {query}\n\nAnswer: {answer}\n\nSources:\n{_format_sources(cited)}"},
        ],
        "temperature": 0,
        "max_tokens": VERIFY_MAX_TOKENS,
    }
    out = {"verdict": None, "error": None, "cost": None, "balance": None,
           "prompt_tokens": 0, "completion_tokens": 0}
    for attempt in range(2):
        resp, err = _post_with_retry(payload)
        if err:
            out["error"] = err
            return out
        try:
            parsed = _parse_response(resp)
        except _PARSE_ERRORS as e:
            out["error"] = f"Malformed verifier response: {str(e)[:200]}"
            return out
        usage = parsed["usage"]
        out["prompt_tokens"] += usage.get("prompt_tokens") or 0
        out["completion_tokens"] += usage.get("completion_tokens") or 0
        if parsed["cost"] is not None:
            out["cost"] = (out["cost"] or 0.0) + parsed["cost"]
        if parsed["balance"] is not None:
            out["balance"] = parsed["balance"]
        verdict = _parse_verdict(parsed["content"])
        if verdict:
            out["verdict"] = verdict
            return out
        if attempt == 0:  # empty or unclear (often thinking used up the token limit): retry with more room
            payload = {**payload, "max_tokens": VERIFY_RETRY_MAX_TOKENS}
    out["error"] = "Unclear or empty verifier reply"
    return out


def _apply_verification(result: dict, query: str, chunks: list[dict]) -> None:
    if VERIFY_WITH_ALL_CHUNKS:
        cited = list(enumerate(chunks, 1))
    else:
        cited = [(c["number"], chunks[c["number"] - 1]) for c in result["citations"]]
    v = _verify(query, result["answer"], cited)

    result["prompt_tokens"] = (result["prompt_tokens"] or 0) + v["prompt_tokens"]
    result["completion_tokens"] = (result["completion_tokens"] or 0) + v["completion_tokens"]
    if v["cost"] is not None:
        result["cost_bdt"] = (result["cost_bdt"] or 0.0) + v["cost"]
    if v["balance"] is not None:
        result["balance_after"] = v["balance"]
        if v["balance"] < LOW_BALANCE_BDT:
            result["warning"] = f"Low CraftX balance: {v['balance']}"
    result["verification_error"] = v["error"]

    if v["verdict"] == "UNSUPPORTED":
        result["rejected_answer"] = result["answer"]
        result["answer"] = REFUSAL_TEXT
        result["refused"] = True
        result["citations"] = []
        result["verification"] = "failed"
    elif v["verdict"] == "SUPPORTED":
        result["verification"] = "passed"
    else:
        result["verification"] = "inconclusive"  # answer kept; the verifier gave no usable verdict


def generate_answer(query: str, context_chunks: list[dict]) -> dict:
    start = time.perf_counter()

    if not context_chunks:  # nothing retrieved: refuse without calling the model
        res = _result(REFUSAL_TEXT, [], finish_reason="no_context", cost=0.0, start=start)
        res["refused"] = True
        return res

    payload = {
        "model": settings.craftx_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(query, context_chunks)},
        ],
        "temperature": 0,
        "max_tokens": FIRST_MAX_TOKENS,
    }

    length_retries = 0
    attempts = 0
    cost_total = None  # summed over every call so the logged cost is the real cost
    balance = None

    def fail(msg: str) -> dict:
        return _result("", context_chunks, error=msg, cost=cost_total, balance=balance,
                       start=start, attempts=attempts)

    while True:
        attempts += 1
        resp, err = _post_with_retry(payload)
        if err:
            return fail(err)
        try:
            parsed = _parse_response(resp)
        except _PARSE_ERRORS as e:
            return fail(f"Malformed API response: {str(e)[:200]}")

        answer = normalize_answer(parsed["content"])
        finish_reason = parsed["finish_reason"]
        if parsed["cost"] is not None:
            cost_total = (cost_total or 0.0) + parsed["cost"]
        if parsed["balance"] is not None:
            balance = parsed["balance"]

        if not answer or finish_reason == "length":
            if length_retries < 1:
                length_retries += 1
                payload = {**payload, "max_tokens": RETRY_MAX_TOKENS}
                logger.warning("Empty or truncated answer, retrying with %s max_tokens", RETRY_MAX_TOKENS)
                continue
            return _result(answer, context_chunks, error="Truncated or empty answer after retry",
                           usage=parsed["usage"], finish_reason=finish_reason, cost=cost_total,
                           balance=balance, start=start, attempts=attempts,
                           reasoning_chars=parsed["reasoning_chars"])
        break

    result = _result(answer, context_chunks, usage=parsed["usage"], finish_reason=finish_reason,
                     cost=cost_total, balance=balance, start=start, attempts=attempts,
                     reasoning_chars=parsed["reasoning_chars"])

    if getattr(settings, "verify_answers", True) and not result["refused"] and result["citations"]:
        _apply_verification(result, query, context_chunks)

    result["latency_ms"] = int((time.perf_counter() - start) * 1000)  # includes the verification call
    return result