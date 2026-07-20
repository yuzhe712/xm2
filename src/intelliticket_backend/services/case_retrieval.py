"""Case Retrieval Service — 纯 Python TF-IDF + 余弦相似度，无外部依赖。

支持中文：使用字符 bigram 分词，对短文本（工单症状）效果足够。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field


def _tokenize(text: str) -> list[str]:
    """中文用字符 bigram + 英文/数字整体切分。"""
    tokens: list[str] = []
    # Split on whitespace first
    parts = re.split(r"[\s]+", text.strip())
    for part in parts:
        if not part:
            continue
        # English/number chunks stay whole
        en_chunks = re.findall(r"[a-zA-Z0-9_.\-/]+", part)
        if en_chunks:
            tokens.extend(en_chunks)
        # Chinese: character bigrams
        cn_text = re.sub(r"[a-zA-Z0-9_.\-/]+", "", part)
        if cn_text:
            tokens.extend(cn_text[i : i + 2] for i in range(len(cn_text) - 1))
            if len(cn_text) == 1:
                tokens.append(cn_text)
    return tokens or [text.strip()]


@dataclass
class CaseRecord:
    """知识库中的一条案例。"""

    ticket_id: str
    text: str  # 原始工单文本
    symptoms: list[str] = field(default_factory=list)
    data_mode: str = "mock"
    root_cause: str = ""  # LLM 诊断的根因
    confirmed_root_cause: str = ""  # 人工确认的根因（有反馈后才有值）
    resolution: str = ""  # 处理方案
    token_counts: Counter[str] = field(default_factory=Counter)


class CaseRetrieval:
    """TF-IDF 案例检索引擎。

    用法::

        retrieval = CaseRetrieval()
        retrieval.index(case)              # 逐个索引
        results = retrieval.search(query, top_k=3)  # 返回 (ticket_id, score)
    """

    def __init__(self) -> None:
        self._cases: dict[str, CaseRecord] = {}
        self._df: Counter[str] = Counter()  # document frequency
        self._dirty: bool = False

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def index(self, case: CaseRecord) -> None:
        """索引或更新一条案例。"""
        self._cases[case.ticket_id] = case
        self._dirty = True

    def rebuild(self) -> None:
        """重建 DF 表（批量索引后调用）。"""
        self._df.clear()
        for case in self._cases.values():
            unique_terms = set(case.token_counts)
            for term in unique_terms:
                self._df[term] += 1
        self._dirty = False

    def _ensure_fresh(self) -> None:
        if self._dirty:
            self.rebuild()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, text: str, symptoms: list[str] | None = None, top_k: int = 3) -> list[tuple[str, float]]:
        """返回 top_k 条最相似案例的 (ticket_id, score) 列表。"""
        self._ensure_fresh()
        query_tokens = _tokenize(text)
        if symptoms:
            for s in symptoms:
                query_tokens.extend(_tokenize(s))
        query_vec = Counter(query_tokens)

        n_docs = len(self._cases)
        if n_docs == 0:
            return []

        scores: list[tuple[str, float]] = []
        for case in self._cases.values():
            score = self._cosine_sim(query_vec, case.token_counts, n_docs)
            # Boost: confirmed root cause → +0.15
            if case.confirmed_root_cause:
                score += 0.15
            scores.append((case.ticket_id, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [(tid, s) for tid, s in scores[:top_k] if s > 0.05]

    def get_case(self, ticket_id: str) -> CaseRecord | None:
        return self._cases.get(ticket_id)

    @property
    def case_count(self) -> int:
        return len(self._cases)

    # ------------------------------------------------------------------
    # TF-IDF internals
    # ------------------------------------------------------------------

    def _tfidf(self, term: str, tf: int, n_docs: int) -> float:
        """计算单个 term 的 TF-IDF 权重。"""
        if tf <= 0:
            return 0.0
        df = self._df.get(term, 0)
        idf = math.log((n_docs + 1) / (df + 1)) + 1.0
        return (1.0 + math.log(tf)) * idf

    def _cosine_sim(self, query_vec: Counter[str], doc_vec: Counter[str], n_docs: int) -> float:
        """TF-IDF 加权的余弦相似度。"""
        dot = 0.0
        q_norm = 0.0
        d_norm = 0.0

        all_terms = set(query_vec) | set(doc_vec)
        for term in all_terms:
            q_w = self._tfidf(term, query_vec.get(term, 0), n_docs)
            d_w = self._tfidf(term, doc_vec.get(term, 0), n_docs)
            dot += q_w * d_w
            q_norm += q_w * q_w
            d_norm += d_w * d_w

        q_norm_sqrt = math.sqrt(q_norm)
        d_norm_sqrt = math.sqrt(d_norm)
        if q_norm_sqrt == 0 or d_norm_sqrt == 0:
            return 0.0
        return dot / (q_norm_sqrt * d_norm_sqrt)

    # ------------------------------------------------------------------
    # Knowledge stats
    # ------------------------------------------------------------------

    def suggest_sops(self, min_cluster_size: int = 3) -> list[dict]:
        """基于症状聚类，建议可从案例中提取的 SOP 主题。

        Returns list of {symptoms, count, ticket_ids}.
        """
        self._ensure_fresh()
        from collections import defaultdict

        clusters: dict[str, list[str]] = defaultdict(list)
        for case in self._cases.values():
            if case.confirmed_root_cause:
                key = "|".join(sorted(case.symptoms[:3]))
                clusters[key].append(case.ticket_id)

        suggestions = []
        for symptom_key, ticket_ids in clusters.items():
            if len(ticket_ids) >= min_cluster_size:
                suggestions.append({
                    "symptoms": symptom_key.split("|"),
                    "ticket_count": len(ticket_ids),
                    "ticket_ids": ticket_ids,
                })
        suggestions.sort(key=lambda x: x["ticket_count"], reverse=True)
        return suggestions

    def stats(self) -> dict:
        """返回知识库统计信息。"""
        self._ensure_fresh()
        total = len(self._cases)
        confirmed = sum(1 for c in self._cases.values() if c.confirmed_root_cause)
        return {
            "total_cases": total,
            "confirmed_cases": confirmed,
            "unconfirmed_cases": total - confirmed,
            "suggested_sops": len(self.suggest_sops()),
        }
