"""The godowns the mill actually works out of.

Re-runnable: matched on code, so seeding twice changes nothing the second time.
"""

from apps.core.constants import GODOWN_TYPE_MILL, GODOWN_TYPE_SILO, GODOWN_TYPE_STORE

from ..models import Godown

GODOWNS = (
    ("MG", "Main Godown", GODOWN_TYPE_MILL),
    ("FG", "Finish Goods Godown", GODOWN_TYPE_STORE),
    ("SL", "Silo", GODOWN_TYPE_SILO),
)


def seed_godowns() -> int:
    created = 0
    for code, name, godown_type in GODOWNS:
        _, made = Godown.objects.get_or_create(
            code=code,
            defaults={"name": name, "godown_type": godown_type},
        )
        created += int(made)
    return created
