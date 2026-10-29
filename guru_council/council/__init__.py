"""The Guru Council — four field-specialist analysts + the Chair."""
from .value import ValueAnalyst
from .macro_trends import MacroTrendsAnalyst
from .cross_asset import CrossAssetAnalyst
from .risk_control import RiskControlAnalyst

COUNCIL = [
    ValueAnalyst(),
    MacroTrendsAnalyst(),
    CrossAssetAnalyst(),
    RiskControlAnalyst(),
]

__all__ = ["COUNCIL", "ValueAnalyst", "MacroTrendsAnalyst", "CrossAssetAnalyst", "RiskControlAnalyst"]
