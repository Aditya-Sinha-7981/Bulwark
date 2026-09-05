from typing import Literal
from pydantic import BaseModel, Field


class PolicyDecision(BaseModel):
    decision: Literal["allow", "deny"]
    reason: str
    rule: str