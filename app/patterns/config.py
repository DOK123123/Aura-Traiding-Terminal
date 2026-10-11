from pydantic import BaseModel, ConfigDict, Field, model_validator


class PatternConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    lookback: int = Field(20, ge=5, le=60)
    max_matches: int = Field(100, ge=5, le=500)
    minimum_similarity: float = Field(75, ge=0, le=100)
    signal_threshold: float = Field(60, ge=51, le=95)
    horizons: tuple[int, ...] = (5, 10, 20, 50)
    decision_horizon: int = 20
    minimum_sample: int = Field(20, ge=5, le=200)
    minimum_confidence: float = Field(40, ge=0, le=100)
    round_trip_cost_bps: float = Field(5, ge=0, le=100)

    @model_validator(mode='after')
    def validate_horizons(self):
        if (not self.horizons or len(self.horizons) > 8 or len(set(self.horizons)) != len(self.horizons)
                or any(h < 1 or h > 200 for h in self.horizons)
                or self.decision_horizon not in self.horizons):
            raise ValueError('Unique horizons 1..200 must include decision_horizon')
        return self
