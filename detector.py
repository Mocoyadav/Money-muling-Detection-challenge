import math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Set

import networkx as nx
import pandas as pd


@dataclass
class AccountScore:
    account_id: str
    risk_score: float
    reasons: List[str]


@dataclass
class FraudRing:
    ring_id: str
    members: List[str]
    pattern_type: str
    risk_score: float
    details: Dict[str, Any]


def _parse_timestamp(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts
    # Try common formats, fall back to pandas parser
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(ts), fmt)
        except ValueError:
            continue
    return pd.to_datetime(ts)


def build_graph(df: pd.DataFrame) -> nx.DiGraph:
    g = nx.DiGraph()
    for _, row in df.iterrows():
        sender = str(row["sender_id"])
        receiver = str(row["receiver_id"])
        amount = float(row["amount"])
        ts = _parse_timestamp(row["timestamp"])
        tx_id = str(row["transaction_id"])

        g.add_node(sender)
        g.add_node(receiver)
        g.add_edge(
            sender,
            receiver,
            transaction_id=tx_id,
            amount=amount,
            timestamp=ts,
        )
    return g


def detect_cycles(
    g: nx.DiGraph, min_len: int = 3, max_len: int = 5
) -> List[FraudRing]:
    rings: List[FraudRing] = []
    seen: Set[Tuple[str, ...]] = set()

    for cycle in nx.simple_cycles(g):
        if min_len <= len(cycle) <= max_len:
            # Normalize cycle representation (rotation-invariant)
            rotated_variants = []
            for i in range(len(cycle)):
                rotated = tuple(cycle[i:] + cycle[:i])
                rotated_variants.append(rotated)
            key = min(rotated_variants)
            if key in seen:
                continue
            seen.add(key)

            # Risk score based on cycle length
            base_score = 60 + (len(cycle) - min_len) * 5
            rings.append(
                FraudRing(
                    ring_id="",
                    members=list(cycle),
                    pattern_type="cycle",
                    risk_score=base_score,
                    details={"length": len(cycle)},
                )
            )
    return rings


def detect_smurfing(
    g: nx.DiGraph,
    fan_threshold: int = 10,
    window_hours: int = 72,
) -> Tuple[List[FraudRing], Dict[str, AccountScore]]:
    rings: List[FraudRing] = []
    account_scores: Dict[str, AccountScore] = {}
    window = timedelta(hours=window_hours)

    def add_reason(acc_id: str, score: float, reason: str) -> None:
        if acc_id not in account_scores:
            account_scores[acc_id] = AccountScore(
                account_id=acc_id, risk_score=0.0, reasons=[]
            )
        acc = account_scores[acc_id]
        acc.risk_score += score
        acc.reasons.append(reason)

    # Fan-in: many senders -> one receiver in short time window
    for node in g.nodes:
        incoming = list(g.in_edges(node, data=True))
        if len(incoming) >= fan_threshold:
            # Check if they are temporally clustered
            timestamps = sorted(
                [_parse_timestamp(d["timestamp"]) for _, _, d in incoming]
            )
            # Sliding window
            i = 0
            j = 0
            while i < len(timestamps):
                while (
                    j < len(timestamps)
                    and timestamps[j] - timestamps[i] <= window
                ):
                    j += 1
                cluster_size = j - i
                if cluster_size >= fan_threshold:
                    senders = {
                        str(incoming[k][0])
                        for k in range(i, j)
                    }
                    members = list(senders | {str(node)})
                    score = 70 + (cluster_size - fan_threshold) * 2
                    rings.append(
                        FraudRing(
                            ring_id="",
                            members=members,
                            pattern_type="smurfing_fan_in",
                            risk_score=score,
                            details={
                                "receiver": str(node),
                                "cluster_size": cluster_size,
                            },
                        )
                    )
                    add_reason(
                        str(node),
                        score * 0.6,
                        f"Fan-in smurfing receiver from {cluster_size} senders",
                    )
                    for s in senders:
                        add_reason(
                            s,
                            score * 0.2,
                            "Fan-in smurfing sender",
                        )
                    break
                i += 1

    # Fan-out: one sender -> many receivers in short time window
    for node in g.nodes:
        outgoing = list(g.out_edges(node, data=True))
        if len(outgoing) >= fan_threshold:
            timestamps = sorted(
                [_parse_timestamp(d["timestamp"]) for _, _, d in outgoing]
            )
            i = 0
            j = 0
            while i < len(timestamps):
                while (
                    j < len(timestamps)
                    and timestamps[j] - timestamps[i] <= window
                ):
                    j += 1
                cluster_size = j - i
                if cluster_size >= fan_threshold:
                    receivers = {
                        str(outgoing[k][1])
                        for k in range(i, j)
                    }
                    members = list(receivers | {str(node)})
                    score = 70 + (cluster_size - fan_threshold) * 2
                    rings.append(
                        FraudRing(
                            ring_id="",
                            members=members,
                            pattern_type="smurfing_fan_out",
                            risk_score=score,
                            details={
                                "sender": str(node),
                                "cluster_size": cluster_size,
                            },
                        )
                    )
                    add_reason(
                        str(node),
                        score * 0.6,
                        f"Fan-out smurfing sender to {cluster_size} receivers",
                    )
                    for r in receivers:
                        add_reason(
                            r,
                            score * 0.2,
                            "Fan-out smurfing receiver",
                        )
                    break
                i += 1

    return rings, account_scores


def detect_shell_chains(
    g: nx.DiGraph,
    min_hops: int = 3,
    max_hops: int = 6,
    low_activity_threshold: int = 3,
) -> Tuple[List[FraudRing], Dict[str, AccountScore]]:
    rings: List[FraudRing] = []
    account_scores: Dict[str, AccountScore] = {}

    def add_reason(acc_id: str, score: float, reason: str) -> None:
        if acc_id not in account_scores:
            account_scores[acc_id] = AccountScore(
                account_id=acc_id, risk_score=0.0, reasons=[]
            )
        acc = account_scores[acc_id]
        acc.risk_score += score
        acc.reasons.append(reason)

    # Precompute activity (degree) for each node
    activity = {
        n: g.in_degree(n) + g.out_degree(n)
        for n in g.nodes
    }

    # Limit search space by focusing on low-activity intermediaries
    low_activity_nodes = {
        n for n, deg in activity.items()
        if deg <= low_activity_threshold
    }

    visited_paths: Set[Tuple[str, ...]] = set()

    for start in g.nodes:
        # Simple DFS up to max_hops
        stack: List[Tuple[str, List[str]]] = [(start, [start])]
        while stack:
            current, path = stack.pop()
            if len(path) - 1 > max_hops:
                continue
            if (
                len(path) - 1 >= min_hops
                and len(path) > 2
            ):
                intermediates = path[1:-1]
                if (
                    intermediates
                    and all(
                        node in low_activity_nodes
                        for node in intermediates
                    )
                ):
                    key = tuple(path)
                    if key not in visited_paths:
                        visited_paths.add(key)
                        score = (
                            50
                            + (len(intermediates) - 1) * 5
                        )
                        rings.append(
                            FraudRing(
                                ring_id="",
                                members=list(dict.fromkeys(path)),
                                pattern_type="shell_chain",
                                risk_score=score,
                                details={
                                    "path": path,
                                    "intermediates": intermediates,
                                },
                            )
                        )
                        for mid in intermediates:
                            add_reason(
                                mid,
                                score * 0.4,
                                "Low-activity intermediary in shell chain",
                            )
                        add_reason(
                            path[0],
                            score * 0.2,
                            "Shell chain originator",
                        )
                        add_reason(
                            path[-1],
                            score * 0.2,
                            "Shell chain destination",
                        )

            for _, neigh in g.out_edges(current):
                if neigh not in path:
                    stack.append((neigh, path + [str(neigh)]))

    return rings, account_scores


def combine_scores(
    graph: nx.DiGraph,
    rings: List[FraudRing],
    pattern_scores: List[Dict[str, AccountScore]],
) -> List[AccountScore]:
    combined: Dict[str, AccountScore] = {}

    def ensure(acc_id: str) -> AccountScore:
        if acc_id not in combined:
            combined[acc_id] = AccountScore(
                account_id=acc_id, risk_score=0.0, reasons=[]
            )
        return combined[acc_id]

    # Base score from degree centrality (suspicious hubs)
    if len(graph) > 0:
        degree_centrality = nx.degree_centrality(graph)
    else:
        degree_centrality = {}
    for acc_id, cent in degree_centrality.items():
        acc = ensure(str(acc_id))
        acc.risk_score += cent * 20
        if cent > 0:
            acc.reasons.append(
                f"High degree centrality ({cent:.3f})"
            )

    # Add scores from patterns
    for pattern_score in pattern_scores:
        for acc_id, acc_score in pattern_score.items():
            acc = ensure(acc_id)
            acc.risk_score += acc_score.risk_score
            acc.reasons.extend(acc_score.reasons)

    # Add ring membership boosts
    for ring in rings:
        for member in ring.members:
            acc = ensure(member)
            acc.risk_score += ring.risk_score * 0.3
            acc.reasons.append(
                f"Member of {ring.pattern_type} ring"
            )

    # Normalize to 0–100
    if not combined:
        return []
    max_score = max(acc.risk_score for acc in combined.values())
    if max_score <= 0:
        return list(combined.values())

    for acc in combined.values():
        acc.risk_score = round(
            min(100.0, (acc.risk_score / max_score) * 100.0), 2
        )

    # Sort descending
    sorted_scores = sorted(
        combined.values(),
        key=lambda a: a.risk_score,
        reverse=True,
    )
    return sorted_scores


def assign_ring_ids(rings: List[FraudRing]) -> List[FraudRing]:
    for i, ring in enumerate(
        sorted(
            rings,
            key=lambda r: r.risk_score,
            reverse=True,
        ),
        start=1,
    ):
        ring.ring_id = f"R{i:04d}"
    return rings


def detect_all_patterns(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Main entry point: given a transaction DataFrame, return
    graph data, account scores, and fraud rings.
    """
    g = build_graph(df)

    # Pattern detections
    cycles = detect_cycles(g)
    smurf_rings, smurf_scores = detect_smurfing(g)
    shell_rings, shell_scores = detect_shell_chains(g)

    all_rings = cycles + smurf_rings + shell_rings
    all_rings = assign_ring_ids(all_rings)

    account_scores = combine_scores(
        g, all_rings, [smurf_scores, shell_scores]
    )

    # Graph for frontend (nodes + edges)
    nodes = [
        {
            "id": str(n),
            "risk_score": next(
                (
                    a.risk_score
                    for a in account_scores
                    if a.account_id == str(n)
                ),
                0.0,
            ),
        }
        for n in g.nodes
    ]
    edges = [
        {
            "source": str(u),
            "target": str(v),
            "transaction_id": d.get("transaction_id"),
            "amount": d.get("amount"),
            "timestamp": d.get("timestamp").isoformat()
            if isinstance(d.get("timestamp"), datetime)
            else str(d.get("timestamp")),
        }
        for u, v, d in g.edges(data=True)
    ]

    rings_json = [
        {
            "ring_id": r.ring_id,
            "members": r.members,
            "pattern_type": r.pattern_type,
            "risk_score": r.risk_score,
            "details": r.details,
        }
        for r in all_rings
    ]

    accounts_json = [
        {
            "account_id": a.account_id,
            "risk_score": a.risk_score,
            "reasons": a.reasons,
        }
        for a in account_scores
    ]

    return {
        "graph": {"nodes": nodes, "edges": edges},
        "accounts": accounts_json,
        "fraud_rings": rings_json,
    }
