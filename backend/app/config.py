"""Subscription / quota config. Designed so billing can be wired in later without refactoring."""

TIERS = {
    "free": {
        "label": "Free",
        "max_generations": 5,
        "max_duration_s": 45,
        "stems": False,
        "priority": "normal",
        "price_usd": 0,
        "price_kes": 0,
    },
    "pro": {
        "label": "Pro",
        "max_generations": None,
        "max_duration_s": 180,
        "stems": True,
        "priority": "high",
        "price_usd": 9,
        "price_kes": 1200,
    },
    "studio": {
        "label": "Studio",
        "max_generations": None,
        "max_duration_s": 600,
        "stems": True,
        "priority": "urgent",
        "price_usd": 29,
        "price_kes": 3900,
    },
}

DEFAULT_TIER = "free"


def tier_for(client_id):
    """Return the active tier for a client, consulting billing subscriptions first."""
    from . import billing  # lazy import avoids a circular dependency

    name = billing.active_tier_name(client_id)
    return TIERS[name]


def generation_count(client_id):
    import os
    from .storage import DATA_DIR, _client_dir
    cdir = _client_dir(client_id)
    return len([f for f in os.listdir(cdir) if f.endswith(".json")])


def assert_quota(client_id):
    tier = tier_for(client_id)
    if tier["max_generations"] is None:
        return tier
    used = generation_count(client_id)
    if used >= tier["max_generations"]:
        raise PermissionError(
            "You have reached the Free plan limit of %d generations. "
            "Subscribe to Pro for unlimited generation." % tier["max_generations"]
        )
    return tier
