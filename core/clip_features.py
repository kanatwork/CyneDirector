"""Keep CLIP feature extraction compatible with Transformers 4 and 5."""


def as_clip_tensor(features):
    """Return projected features from either a tensor or a model output."""
    if hasattr(features, "pooler_output"):
        return features.pooler_output
    if isinstance(features, tuple):
        return features[1]
    return features
