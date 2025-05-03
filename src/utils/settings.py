from pydantic_settings import BaseSettings
from datetime import datetime
import yaml
from pydantic import BaseModel
from typing import List

from .constants import Interval


class SignalSettings(BaseModel):
    intervals: List[Interval]
    tickers: List[str]
    strategies: List[str]


class Settings(BaseSettings):
    mode: str
    start_date: datetime
    end_date: datetime
    primary_interval: Interval
    initial_cash: int
    margin_requirement: float
    show_reasoning: bool
    signals: SignalSettings


def load_settings(yaml_path: str = "config.yaml") -> Settings:
    with open(yaml_path, "r") as f:
        yaml_data = yaml.safe_load(f)
    return Settings(**yaml_data)


# Load and use
settings = load_settings()

print(settings.mode)
print(settings.primary_interval)
print(settings.start_date)
print(settings.end_date)
print(settings.signals)
