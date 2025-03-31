class CriteriaResult:
    key: str
    value: str | bool
    weight: float

    def __init__(self, key: str, value: str | bool, weight: float = 1):
        self.key = key
        self.value = value
        self.weight = weight

    def score(self) -> int:
        """Converts "true"/"false" into a numerical score (1 for "true", 0 for "false")"""
        if isinstance(self.value, bool):
            return 1 if self.value else 0
        elif isinstance(self.value, str):
            return 1 if self.value.lower() == "true" else 0
        else:
            raise ValueError(f"Score value must be true or false, not {self.value}")


class ValidationResult:
    component_name: str
    criteria: list[CriteriaResult]

    def __init__(self, component_name: str) -> None:
        self.component_name = component_name
        self.criteria = []

    def add_criteria(self, criteria_result: CriteriaResult) -> None:
        self.criteria.append(criteria_result)

    def weighted_score(self) -> float:
        total_weighted_score = sum(c.score() * c.weight for c in self.criteria)
        total_weight = sum(c.weight for c in self.criteria)
        return total_weighted_score / total_weight if total_weight != 0 else 0
