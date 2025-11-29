"""
Entity hierarchy model for PolicyEngine calculations.

PolicyEngine has complex entity relationships:
- Households contain people
- Tax units contain people (US)
- Benefit units contain people (UK)

This module provides:
- Situation: Data structure mirroring PE's situation format
- EntityModel: Runtime model for calculations
- Aggregation: Sum/any/max/min from person → household
- Broadcasting: Household values → person level

The model enables generated code to correctly handle:
- person("variable", period) - get person-level values
- household("variable", period) - get household-level values
- person.household("variable", period) - person gets household's value
- household.sum(household.members("variable", period)) - aggregate
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Situation:
    """
    A situation describing people and entities for calculation.

    Mirrors PolicyEngine's situation dictionary format:
    {
        "people": {
            "adult1": {"employment_income": 50000, "age": 35},
            "adult2": {"employment_income": 30000, "age": 32},
        },
        "households": {
            "household": {"members": ["adult1", "adult2"]},
        }
    }
    """

    people: dict[str, dict[str, Any]] = field(default_factory=dict)
    households: dict[str, dict[str, Any]] = field(default_factory=dict)
    # US entities
    tax_units: dict[str, dict[str, Any]] = field(default_factory=dict)
    spm_units: dict[str, dict[str, Any]] = field(default_factory=dict)
    families: dict[str, dict[str, Any]] = field(default_factory=dict)
    # UK entities
    benunits: dict[str, dict[str, Any]] = field(default_factory=dict)


class EntityModel:
    """
    Runtime model for entity-aware calculations.

    Provides vectorized access to variables at different entity levels,
    with support for aggregation and broadcasting between levels.

    Usage:
        model = EntityModel(
            people={"p1": {"income": 50000}, "p2": {"income": 30000}},
            households={"hh": {"members": ["p1", "p2"]}},
        )

        # Get person-level array
        incomes = model.get_person_variable("income")  # [50000, 30000]

        # Aggregate to household
        hh_income = aggregate_sum(incomes, model.person_to_household_index(), 1)

        # Broadcast back to person
        per_person = broadcast_to_members(hh_income, model.person_to_household_index())
    """

    def __init__(
        self,
        people: dict[str, dict[str, Any]],
        households: dict[str, dict[str, Any]],
        tax_units: Optional[dict[str, dict[str, Any]]] = None,
        benunits: Optional[dict[str, dict[str, Any]]] = None,
        **kwargs,
    ):
        self.people = people
        self.households = households
        self.tax_units = tax_units or {}
        self.benunits = benunits or {}

        # Build indices
        self._person_ids = list(people.keys())
        self._household_ids = list(households.keys())

        # Build person → household mapping
        self._person_to_hh: dict[str, str] = {}
        for hh_id, hh_data in households.items():
            for person_id in hh_data.get("members", []):
                self._person_to_hh[person_id] = hh_id

    @property
    def n_people(self) -> int:
        """Number of people in the model."""
        return len(self._person_ids)

    @property
    def n_households(self) -> int:
        """Number of households in the model."""
        return len(self._household_ids)

    def get_person_variable(self, name: str, default: Any = 0) -> list[Any]:
        """
        Get a person-level variable as a list indexed by person.

        Args:
            name: Variable name
            default: Default value if not specified for a person

        Returns:
            List of values, one per person, in consistent order
        """
        return [
            self.people[pid].get(name, default) for pid in self._person_ids
        ]

    def get_household_variable(self, name: str, default: Any = 0) -> list[Any]:
        """
        Get a household-level variable as a list indexed by household.

        Args:
            name: Variable name
            default: Default value if not specified for a household

        Returns:
            List of values, one per household, in consistent order
        """
        return [
            self.households[hid].get(name, default)
            for hid in self._household_ids
        ]

    def person_to_household_index(self) -> list[int]:
        """
        Get mapping from person index to household index.

        Returns:
            List where result[person_idx] = household_idx
        """
        hh_id_to_idx = {hid: i for i, hid in enumerate(self._household_ids)}
        return [
            hh_id_to_idx[self._person_to_hh[pid]] for pid in self._person_ids
        ]

    def set_person_variable(self, name: str, values: list[Any]) -> None:
        """Set a calculated person-level variable."""
        for pid, value in zip(self._person_ids, values):
            self.people[pid][name] = value

    def set_household_variable(self, name: str, values: list[Any]) -> None:
        """Set a calculated household-level variable."""
        for hid, value in zip(self._household_ids, values):
            self.households[hid][name] = value


def aggregate_sum(
    person_values: list[float],
    person_to_hh: list[int],
    n_households: int,
) -> list[float]:
    """
    Sum person values to household level.

    Equivalent to: household.sum(household.members("variable", period))

    Args:
        person_values: Values for each person
        person_to_hh: Mapping from person index to household index
        n_households: Total number of households

    Returns:
        List of sums, one per household
    """
    result = [0.0] * n_households
    for person_idx, value in enumerate(person_values):
        hh_idx = person_to_hh[person_idx]
        result[hh_idx] += value
    return result


def aggregate_any(
    person_values: list[bool],
    person_to_hh: list[int],
    n_households: int,
) -> list[bool]:
    """
    Check if any person in household has True value.

    Equivalent to: household.any(household.members("is_disabled", period))

    Args:
        person_values: Boolean values for each person
        person_to_hh: Mapping from person index to household index
        n_households: Total number of households

    Returns:
        List of booleans, one per household
    """
    result = [False] * n_households
    for person_idx, value in enumerate(person_values):
        hh_idx = person_to_hh[person_idx]
        if value:
            result[hh_idx] = True
    return result


def aggregate_max(
    person_values: list[float],
    person_to_hh: list[int],
    n_households: int,
) -> list[float]:
    """
    Get maximum person value per household.

    Equivalent to: household.max(household.members("age", period))

    Args:
        person_values: Values for each person
        person_to_hh: Mapping from person index to household index
        n_households: Total number of households

    Returns:
        List of max values, one per household
    """
    result = [float("-inf")] * n_households
    for person_idx, value in enumerate(person_values):
        hh_idx = person_to_hh[person_idx]
        if value > result[hh_idx]:
            result[hh_idx] = value
    return result


def aggregate_min(
    person_values: list[float],
    person_to_hh: list[int],
    n_households: int,
) -> list[float]:
    """
    Get minimum person value per household.

    Equivalent to: household.min(household.members("age", period))

    Args:
        person_values: Values for each person
        person_to_hh: Mapping from person index to household index
        n_households: Total number of households

    Returns:
        List of min values, one per household
    """
    result = [float("inf")] * n_households
    for person_idx, value in enumerate(person_values):
        hh_idx = person_to_hh[person_idx]
        if value < result[hh_idx]:
            result[hh_idx] = value
    return result


def aggregate_count(
    person_to_hh: list[int],
    n_households: int,
) -> list[int]:
    """
    Count people per household.

    Equivalent to: household.nb_persons()

    Args:
        person_to_hh: Mapping from person index to household index
        n_households: Total number of households

    Returns:
        List of counts, one per household
    """
    result = [0] * n_households
    for hh_idx in person_to_hh:
        result[hh_idx] += 1
    return result


def broadcast_to_members(
    household_values: list[Any],
    person_to_hh: list[int],
) -> list[Any]:
    """
    Broadcast household values to person level.

    Equivalent to: person.household("household_income", period)

    Each person gets their household's value.

    Args:
        household_values: Values for each household
        person_to_hh: Mapping from person index to household index

    Returns:
        List of values, one per person (each person gets their household's value)
    """
    return [household_values[hh_idx] for hh_idx in person_to_hh]


def get_entity_index(
    model: EntityModel,
    from_entity: str,
    to_entity: str,
) -> list[int]:
    """
    Get mapping from one entity to another.

    Args:
        model: The entity model
        from_entity: Source entity type (e.g., "person")
        to_entity: Target entity type (e.g., "household")

    Returns:
        List mapping source index to target index
    """
    if from_entity == "person" and to_entity == "household":
        return model.person_to_household_index()

    raise NotImplementedError(
        f"Mapping from {from_entity} to {to_entity} not implemented"
    )
