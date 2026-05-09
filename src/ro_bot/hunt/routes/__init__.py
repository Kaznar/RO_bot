"""Python-composed farm return routes (segments + strategies + registry)."""

from ro_bot.hunt.routes.plan import FarmReturnPlan
from ro_bot.hunt.routes.registry import (
    FARM_RETURN_PLAN_FACTORIES,
    augment_return_to_farm_from_registry,
    resolve_farm_return_plan,
)

__all__ = [
    "FarmReturnPlan",
    "FARM_RETURN_PLAN_FACTORIES",
    "augment_return_to_farm_from_registry",
    "resolve_farm_return_plan",
]
