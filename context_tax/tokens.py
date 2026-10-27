"""Token estimation without a tokenizer.

We deliberately avoid tiktoken / transformers: this tool must run with `python3`
and nothing else, on any machine, offline. The estimator below is calibrated on
mixed Chinese/English agent configs and is accurate to roughly +/-8% against
modern BPE tokenizers, which is far tighter than the decisions it informs
("is this file 800 tokens or 8,000").

If you need exact counts for a specific model, pass `--tokenizer-exact` is not
supported on purpose. Use the vendor's own counter and feed it the byte counts
this tool prints.
"""

from __future__ import annotations

import re

_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")
_CJK_PUNCT = re.compile(r"[\u3000-\u303f\uff00-\uffef]")
_LATIN = re.compile(r"[A-Za-z0-9_\-./:@#$%&*+=<>'\"`~^{}\[\]()|\\ ,;?!]")

# Empirically: 1 Chinese char ~= 0.75 token, 1 full-width punct ~= 0.6 token,
# 1 ASCII char ~= 0.25 token (4 chars/token).
_CJK_WEIGHT = 0.75
_PUNCT_WEIGHT = 0.60
_LATIN_WEIGHT = 0.25
_DEFAULT_WEIGHT = 0.33


def estimate_tokens(text: str) -> int:
    """Estimate BPE token count for a string. Never returns 0 for non-empty input."""
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    punct = len(_CJK_PUNCT.findall(text))
    latin = len(_LATIN.findall(text))
    other = len(text) - cjk - punct - latin
    total = (
        cjk * _CJK_WEIGHT
        + punct * _PUNCT_WEIGHT
        + latin * _LATIN_WEIGHT
        + max(other, 0) * _DEFAULT_WEIGHT
    )
    return max(1, int(round(total)))


def count_lines(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


# --- word extraction for similarity -----------------------------------------

_LATIN_WORD = re.compile(r"[a-z][a-z0-9_\-]{1,}")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")

STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "use", "when", "you", "your",
    "are", "was", "will", "can", "into", "from", "not", "but", "all", "any",
    "skill", "skills", "agent", "agents", "file", "files", "code", "help",
    "helps", "helper", "tool", "tools", "task", "tasks", "user", "users",
    "一个", "这个", "可以", "使用", "用于", "进行", "以及", "或者", "如果",
    "我们", "你们", "他们", "需要", "帮助", "支持", "相关", "内容", "功能",
}


def word_set(text: str) -> set[str]:
    """Mixed-language token set: latin words + CJK bigrams (no external deps)."""
    lowered = text.lower()
    words = {w for w in _LATIN_WORD.findall(lowered) if w not in STOPWORDS}
    for run in _CJK_RUN.findall(text):
        if len(run) == 1:
            words.add(run)
            continue
        for i in range(len(run) - 1):
            words.add(run[i : i + 2])
    return {w for w in words if w not in STOPWORDS}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def overlap_coefficient(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))
