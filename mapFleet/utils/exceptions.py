class MapsAPIError(Exception):
    """Google Maps API failure or missing configuration."""

    pass


class OptimizationError(Exception):
    """Optimization solver failed or invalid input."""

    pass
