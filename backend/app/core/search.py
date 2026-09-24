"""Shared helpers for user-supplied SQL LIKE searches."""

LIKE_ESCAPE = "\\"


def like_contains(value: str) -> str:
    """Build a contains pattern whose user text is matched literally.

    SQLAlchemy still parameterizes the value; escaping only prevents ``%`` and
    ``_`` in the search text from becoming unintended SQL wildcards.
    """

    escaped = (
        value.strip()
        .replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"
