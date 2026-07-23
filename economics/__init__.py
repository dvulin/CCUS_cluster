"""Economic calculations for the CCUS model."""

from .economics import Economics
from .price_scenarios import generate_co2_price_path

__all__ = ["Economics", "generate_co2_price_path"]
