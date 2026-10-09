"""The shape Claude must return. Pydantic validates it or raises -
a malformed rulebook never reaches the engine.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class ChoiceOption(BaseModel):
    id: str = Field(description="snake_case id, e.g. 'under_1_day'")
    label: str = Field(description="what the patient reads, e.g. 'Less than one day'")


class Finding(BaseModel):
    id: str = Field(description="snake_case id, e.g. 'joint_swelling'")
    type: Literal["noul", "choice"] = Field(
        description="'noul' = yes/no. 'choice' = pick one of N options.")
    question: str = Field(description="exact words the patient will read")
    definition: str = Field(
        description="one sentence removing ambiguity, shown on 'what does this mean?'")
    options: Optional[List[ChoiceOption]] = Field(
        default=None, description="required for type='choice', omit for 'noul'")


class ChoiceDistribution(BaseModel):
    finding: str = Field(description="id of a type='choice' finding")
    distribution: List[float] = Field(
        description="one probability per option IN ORDER. Must sum to 1.0")


class Cell(BaseModel):
    finding: str = Field(description="id of a type='noul' finding")
    p: float = Field(ge=0, le=1,
        description="of 100 patients with this condition, how many have this finding")
    note: Optional[str] = Field(
        default=None,
        description="why this number, especially for rule-outs")


class Condition(BaseModel):
    id: str = Field(description="snake_case id, e.g. 'rheumatoid_arthritis'")
    name: str = Field(description="name a patient would recognise")
    prior: float = Field(gt=0, le=1,
        description="share of people presenting WITH THIS COMPLAINT who have this")
    must_not_miss: bool = Field(
        description="true if missing it could cause serious harm")
    choices: List[ChoiceDistribution]
    cells: List[Cell]


class GeneratedRulebook(BaseModel):
    category: str
    findings: List[Finding]
    conditions: List[Condition]
