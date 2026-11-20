"""Name and role matching for the who's-who scorer."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .formats import Person

DEFAULT_PLACEHOLDER_PATTERN = (
    r"^(?:unknown|unidentified|unnamed|speaker|spk|voice|participant|person|guest)"
    r"(?![^\W\d_])"
)

# Words that make a name a role (a job on the call) rather than a person's name.
# Words that already mean "placeholder" (unknown, participant) are not roles.
ROLE_WORDS = frozenset(
    {
        "operator",
        "moderator",
        "host",
        "presenter",
        "chairman",
        "chairwoman",
        "chair",
        "announcer",
        "analyst",
        "caller",
    }
)

FULL = "full"
PARTIAL = "partial"
PLACEHOLDER = "placeholder"
UNKNOWN = "unknown"
AMBIGUOUS = "ambiguous"


def name_tokens(name: str | None) -> tuple[str, ...]:
    """Lowercase, drop punctuation and split into tokens."""
    if not name:
        return ()
    return tuple(re.sub(r"[^\w\s]", " ", name.lower().replace("_", " ")).split())


def is_placeholder_name(name: str | None, pattern: str = DEFAULT_PLACEHOLDER_PATTERN) -> bool:
    """True when `name` has no words or matches the placeholder pattern."""
    tokens = name_tokens(name)
    if not tokens:
        return True
    regex = re.compile(pattern, re.IGNORECASE)
    return bool(regex.match(" ".join(tokens)) or regex.match(name or ""))


@dataclass(frozen=True)
class Resolution:
    """What a name resolves to.

    ``kind`` is one of:

    - "full": the name is a person's name or alias (or the one role it names);
    - "partial": the name is part of one person's name, such as a first name only;
    - "ambiguous": the name is part of two or more people's names, such as "Dana" when
      Dana Reyes and Dana Cho are both in the call, so it points to no one person;
    - "placeholder": no name, or a placeholder such as "Speaker 2";
    - "unknown": no one in the call has that name.

    For full and partial, ``person`` is the index into ``Roster.names`` and ``person_name``
    is that name; otherwise both are ``None``.
    """

    kind: str
    person: int | None = None
    person_name: str | None = None


class Roster:
    """The people in a conversation, with aliases, and the rules to resolve a name."""

    def __init__(self, people: list[Person], placeholder_pattern: str, role_rule: bool = False):
        self._role_rule = role_rule
        self.names: list[str] = [p.name for p in people]
        self._forms: list[set[tuple[str, ...]]] = []
        for p in people:
            forms = {name_tokens(p.name)} | {name_tokens(a) for a in p.aliases}
            self._forms.append({f for f in forms if f})
        self._placeholder = re.compile(placeholder_pattern, re.IGNORECASE)

    def index_of_exact(self, name: str) -> int | None:
        """Person whose name or alias has the same words as `name`, in any order."""
        tokens = frozenset(name_tokens(name))
        for i, forms in enumerate(self._forms):
            if any(tokens == frozenset(form) for form in forms):
                return i
        return None

    def add(self, name: str) -> int:
        self.names.append(name)
        self._forms.append({f for f in {name_tokens(name)} if f})
        return len(self.names) - 1

    def resolve(self, name: str | None) -> Resolution:
        tokens = name_tokens(name)
        if not tokens:
            return Resolution(PLACEHOLDER)
        exact = self.index_of_exact(name or "")
        if exact is not None:
            return Resolution(FULL, exact, self.names[exact])
        if self._role_rule and set(tokens) <= ROLE_WORDS:
            roles = [
                i
                for i, person_name in enumerate(self.names)
                if (words := set(name_tokens(person_name)))
                and words <= ROLE_WORDS
                and words & set(tokens)
            ]
            if len(roles) == 1:
                return Resolution(FULL, roles[0], self.names[roles[0]])
        if self._placeholder.match(" ".join(tokens)) or self._placeholder.match(name or ""):
            return Resolution(PLACEHOLDER)
        matches = {
            i for i, forms in enumerate(self._forms) for form in forms if set(tokens) < set(form)
        }
        if len(matches) == 1:
            match = next(iter(matches))
            return Resolution(PARTIAL, match, self.names[match])
        return Resolution(AMBIGUOUS if matches else UNKNOWN)
