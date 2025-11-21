    CLOUD_DASHBOARD_PORT: int = field(
        default_factory=lambda: int(os.getenv("CLOUD_DASHBOARD_PORT", 5006))
    )
    CONFIG_RECOMMENDER_PORT: int = field(
        default_factory=lambda: int(os.getenv("CONFIG_RECOMMENDER_PORT", 8010))
    )
    PROMPT_ROUTER_PORT: int = field(
        default_factory=lambda: int(os.getenv("PROMPT_ROUTER_PORT", 8009))
    )

    # Redis
    REDIS_HOST: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "redis"))