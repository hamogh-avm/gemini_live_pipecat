"""Keyword search over a local markdown knowledge base.

Deliberately not a RAG pipeline: no embeddings, no vector store, no network
call. The KB is a handful of short articles, so scoring query words against
article titles and bodies is enough and costs about a millisecond, which
matters on a voice call where the tool call sits between the customer speaking
and the bot answering.

The file is split on `## KB-nn - Title` headings. Each article is returned
whole, including its closing `**Bot rule:**` line, because that rule is what
keeps the agent from inventing rates and promising approvals.
"""

import math
import os
import re
import time
from typing import Dict, List, Optional, Tuple

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallParams

KB_DIR = os.path.join(os.path.dirname(__file__), "knowledge_base")
KB_FILE = os.getenv("KB_FILE") or os.path.join(KB_DIR, "securelife_lending_kb.md")

# Articles start at "## KB-01 - Title". The separator between number and title
# is a middle dot in the source file, but accept any punctuation so a re-export
# with a plain hyphen doesn't silently produce zero articles.
_ARTICLE_RE = re.compile(r"^##\s+(KB-\d+)\s*[^\w\s]?\s*(.*)$", re.MULTILINE)

_WORD_RE = re.compile(r"[a-z0-9%]+")

_STOPWORDS = {
    "a", "about", "an", "and", "any", "are", "as", "at", "be", "by", "can",
    "do", "does", "for", "from", "get", "give", "has", "have", "how", "i",
    "if", "in", "is", "it", "many", "me", "much", "my", "need", "of", "on",
    "or", "so", "some", "tell", "than", "that", "the", "their", "there",
    "they", "this", "to", "want", "was", "we", "what", "when", "which",
    "will", "with", "would", "you", "your",
}

# Spoken-language terms mapped onto the vocabulary the KB actually uses. This is
# the cheap stand-in for semantic search: a customer says "bike" or "byaaj",
# the KB says "two-wheeler" and "interest".
_SYNONYMS: Dict[str, List[str]] = {
    "bike": ["two", "wheeler", "vehicle"],
    "motorcycle": ["two", "wheeler", "vehicle"],
    "scooter": ["two", "wheeler", "vehicle"],
    "twowheeler": ["two", "wheeler"],
    "byaaj": ["interest", "rate"],
    "interest": ["rate"],
    "roi": ["interest", "rate"],
    "installment": ["emi"],
    "instalment": ["emi"],
    "monthly": ["emi", "tenure"],
    "downpayment": ["down", "payment"],
    "charges": ["fee", "processing"],
    "charge": ["fee", "processing"],
    "hidden": ["fee", "processing", "upfront"],
    "papers": ["documents"],
    "document": ["documents"],
    "kagaz": ["documents"],
    "cibil": ["credit", "score"],
    "sona": ["gold"],
    "jewellery": ["gold"],
    "jeweller": ["gold"],
    "house": ["home", "housing"],
    "property": ["lap", "home"],
    "shares": ["las", "securities"],
    "mutual": ["las", "securities"],
    "business": ["sme", "business"],
    "shop": ["sme", "business"],
    "machine": ["machinery"],
    "transfer": ["balance", "transfer"],
    "shift": ["balance", "transfer"],
    "topup": ["top", "up"],
    "prepay": ["prepayment", "foreclosure"],
    "prepayment": ["foreclosure"],
    "preclose": ["foreclosure", "prepayment"],
    "foreclose": ["foreclosure", "prepayment", "fee"],
    "close": ["foreclosure", "prepayment"],
    "settle": ["foreclosure", "prepayment"],
    "offer": ["products"],
    "types": ["products"],
    "options": ["products"],
    "human": ["specialist", "transfer"],
    "agent": ["specialist"],
    "person": ["specialist"],
    "manager": ["specialist"],
    "robot": ["bot", "virtual", "assistant"],
    "privacy": ["data", "privacy"],
    "aadhaar": ["privacy", "documents"],
    "pan": ["privacy", "documents"],
    "otp": ["privacy"],
    "sahukar": ["moneylender", "local", "lender"],
    "moneylender": ["local", "lender"],
    "financier": ["local", "lender"],
    "dealer": ["showroom", "local"],
    "chit": ["chit", "fund", "local"],
    "eligible": ["eligibility"],
    "eligibility": ["documents"],
    "approve": ["eligibility", "approval"],
    "approval": ["eligibility"],
    "fast": ["disbursal", "speed"],
    "quick": ["disbursal", "speed"],
    "soon": ["disbursal", "speed"],
    "disburse": ["disbursal"],
    "disbursement": ["disbursal"],
    "wedding": ["wedding", "personal"],
    "marriage": ["wedding", "personal"],
    "medical": ["medical", "personal", "emergency"],
    "hospital": ["medical", "emergency"],
    "consolidation": ["consolidation", "debt"],
    "card": ["consolidation", "debt"],
}


def _stem(word: str) -> str:
    """Crude suffix stripping so 'loans' matches 'loan' and 'offered' matches
    'offer'. Linguistic accuracy doesn't matter here - only that the query and
    the KB are reduced the same way."""
    if len(word) > 4:
        if word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        elif word.endswith("ing"):
            word = word[:-3]
        elif word.endswith("ed"):
            word = word[:-2]
    return word


def _tokens(text: str) -> List[str]:
    return [_stem(w) for w in _WORD_RE.findall(text.lower())]


class Article:
    __slots__ = ("id", "title", "body", "_title_words", "_body_counts")

    def __init__(self, article_id: str, title: str, body: str):
        self.id = article_id
        self.title = title
        self.body = body
        self._title_words = set(_tokens(title))
        self._body_counts: Dict[str, int] = {}
        for word in _tokens(body):
            self._body_counts[word] = self._body_counts.get(word, 0) + 1

    def score(self, terms: List[str], idf: Dict[str, float]) -> float:
        total = 0.0
        for term in terms:
            # Rarity weighting. Without it "loan" - which appears in every
            # article - drowns out the term that actually distinguishes them,
            # so "processing fee on a personal loan" lands on the personal-loan
            # article instead of the fees one.
            weight = idf.get(term, 1.0)
            if term in self._title_words:
                total += 5 * weight
            # Cap body hits so one article that merely repeats a common word
            # can't outrank the article actually about it.
            total += min(self._body_counts.get(term, 0), 3) * weight
        return total

    def has(self, term: str) -> bool:
        return term in self._body_counts or term in self._title_words

    def render(self) -> str:
        return f"## {self.id} - {self.title}\n{self.body.strip()}"


_cache: Optional[Tuple[float, List[Article], Dict[str, float]]] = None


def _load() -> Tuple[List[Article], Dict[str, float]]:
    """Parse the KB, re-reading only when the file changes on disk.

    Returns the articles and an inverse-document-frequency table used to weight
    query terms by how much they actually distinguish one article from another.
    """
    global _cache
    try:
        mtime = os.path.getmtime(KB_FILE)
    except OSError:
        logger.warning(f"[KB] Knowledge base file not found: {KB_FILE}")
        return [], {}

    if _cache and _cache[0] == mtime:
        return _cache[1], _cache[2]

    with open(KB_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    matches = list(_ARTICLE_RE.finditer(text))
    articles: List[Article] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip().strip("-").strip()
        articles.append(Article(m.group(1), m.group(2).strip(), body))

    doc_freq: Dict[str, int] = {}
    for a in articles:
        for term in set(a._body_counts) | a._title_words:
            doc_freq[term] = doc_freq.get(term, 0) + 1

    n = len(articles) or 1
    idf = {term: math.log(1 + n / df) for term, df in doc_freq.items()}

    logger.info(f"[KB] Loaded {len(articles)} articles from {os.path.basename(KB_FILE)}")
    _cache = (mtime, articles, idf)
    return articles, idf


def _expand(query: str) -> List[str]:
    """Query words, minus stopwords, plus KB-vocabulary synonyms, all stemmed.

    Synonyms are looked up on the raw word (the table is written in the words
    customers actually say), then everything is stemmed to match the index.
    """
    words = [w for w in _WORD_RE.findall(query.lower()) if w not in _STOPWORDS]
    terms = list(words)
    for w in words:
        terms.extend(_SYNONYMS.get(w, []))
    # Dedupe, keeping order, so repeating a word doesn't inflate its weight.
    return list(dict.fromkeys(_stem(t) for t in terms))


def search(query: str, top_k: int = 3) -> str:
    """Return the best-matching articles as text, or a clear miss message."""
    articles, idf = _load()
    if not articles:
        return "The knowledge base is unavailable. Do not invent facts; offer to connect the customer to a specialist."

    # An explicit article reference ("KB-07") wins outright.
    explicit = re.findall(r"kb[-\s]?(\d{1,2})", query.lower())
    if explicit:
        wanted = {f"KB-{int(n):02d}" for n in explicit}
        hits = [a for a in articles if a.id in wanted]
        if hits:
            return "\n\n---\n\n".join(a.render() for a in hits)

    terms = _expand(query)
    if not terms:
        return "No search terms in the query. Ask the customer to clarify, or state only KB-15 quick facts."

    ranked = sorted(
        ((a.score(terms, idf), a) for a in articles),
        key=lambda pair: pair[0],
        reverse=True,
    )
    hits = [a for score, a in ranked[:top_k] if score > 0]

    if not hits:
        # Better to hand back the always-safe article than nothing at all: it
        # tells the agent what it may state and that everything else is the
        # specialist's to confirm.
        fallback = next((a for a in articles if a.id == "KB-15"), None)
        if fallback:
            return (
                "No article matched that query. Falling back to the quick facts; "
                "anything beyond these must go to a specialist.\n\n" + fallback.render()
            )
        return "No matching article. Do not invent facts; offer to connect the customer to a specialist."

    return "\n\n---\n\n".join(a.render() for a in hits)


kb_search_schema = FunctionSchema(
    name="search_knowledge_base",
    description=(
        "Search the SecureLife Capital lending knowledge base for products, interest rates, "
        "EMI and down-payment rules, processing fees, documents and eligibility, disbursal "
        "speed, specialist handoff, and objection-handling scripts. Call this BEFORE answering "
        "any factual question about lending, and follow the 'Bot rule' line in the result."
    ),
    properties={
        "query": {
            "type": "string",
            "description": (
                "What to look up, in English, in a few words - e.g. 'two-wheeler down payment', "
                "'processing fee', 'customer says local lender gives more money'. Translate from "
                "the customer's language if needed."
            ),
        },
    },
    required=["query"],
)


async def kb_search_handler(params: FunctionCallParams):
    """Handle search_knowledge_base calls against the local markdown KB."""
    query = params.arguments.get("query", "") or ""
    started = time.time()
    try:
        result = search(query)
    except Exception as e:
        logger.error(f"[KB] Search failed for {query!r}: {e}")
        result = "Knowledge base search failed. Do not invent facts; offer a specialist callback."

    elapsed_ms = (time.time() - started) * 1000.0
    logger.info(f"[KB] Query {query!r} -> {len(result)} chars in {elapsed_ms:.1f} ms")
    await params.result_callback({"content": result})
