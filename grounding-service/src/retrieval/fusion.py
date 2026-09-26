def reciprocal_rank_fusion(rankings, top_k, k=60):
    scores, documents = {}, {}
    for ranking in rankings:
        seen = set()
        for rank, doc in enumerate(ranking, 1):
            key = doc["_id"]
            if key in seen:
                continue
            seen.add(key)
            scores[key] = scores.get(key, 0) + 1 / (k + rank)
            documents[key] = doc
    return [documents[key] for key in sorted(scores, key=lambda x: (-scores[x], str(x)))[:top_k]]
