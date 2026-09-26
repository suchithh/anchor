def ewma(previous, probabilities, alpha=0.8):
    if not 0 <= alpha < 1:
        raise ValueError("alpha must be in [0, 1)")
    # First observation initializes the distribution; no implicit optimistic prior.
    if previous is None:
        return list(probabilities)
    return [alpha * old + (1 - alpha) * new for old, new in zip(previous, probabilities)]
