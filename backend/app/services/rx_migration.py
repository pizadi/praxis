"""Legacy free-text Rx parsing (v1.3 structured-prescriptions migration).

Pure logic, deliberately free of app/settings/DB imports so it can be used
from THREE places without drift:
- the Alembic data migration (converts the live ``appointments.rx`` column
  into prescriptions + prescription_item links),
- ``scripts/migrate_sqlite.py`` (legacy Django import does the same
  conversion for fresh installs), and
- the unit tests that pin these rules down.

Semantics (frozen — historical data was migrated with exactly these rules):

- Prescription items are split on commas and newlines (CR or LF).
- Persian/Arabic digits are normalized to ASCII first.
- A trailing standalone INTEGER token is the prescribed quantity
  ("P1 20" → name "P1", quantity 20); decimals ("0.5"), fractions ("1/2")
  and strength+dose pairs ("Azithromycin 250 12" → quantity 12, name
  "Azithromycin 250") are handled by the same last-token rule. No trailing
  integer → quantity stays NULL (never guessed).
- Names are normalized (casefold, whitespace collapse, edge punctuation
  stripped) only as a DEDUPLICATION key; the most frequent original
  spelling becomes the display name.
- Only names seen at least RX_MIN_FREQUENCY times across the whole corpus
  become ``prescription_items`` (the autocomplete dictionary). Everything
  rarer is preserved VERBATIM in the prescription's ``notes`` — the
  migration must never fill the dictionary with one-off sentences
  ("i should see ct for bx and repeat pft") or misspellings.
"""

import dataclasses
import datetime as dt
import re
from collections import Counter
from collections.abc import Iterable

RX_MIN_FREQUENCY = 3
PARSER_VERSION = 1
QUANTITY_MAX = 10**6  # sanity cap for a parsed trailing quantity

# Persian and Arabic-Indic digits → ASCII
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_ITEMS_SPLIT = re.compile(r"[,\n\r]+")
# last whitespace-separated token is a pure integer (after digit normalization)
_QUANTITY_TAIL = re.compile(r"^(.*\S)\s+(\d{1,7})$")
_EDGE_PUNCT = " \t.;:+*-_|"


def normalize_digits(text: str) -> str:
    return text.translate(_DIGITS)


def split_rx_items(rx: str) -> list[str]:
    """Split a legacy rx text into raw item chunks (dropping empties)."""
    return [c for c in (chunk.strip() for chunk in _ITEMS_SPLIT.split(rx)) if c]


def extract_name_quantity(item: str) -> tuple[str, int | None]:
    """Split one item into (display name, quantity-or-None).

    The last standalone integer becomes the quantity; the remainder is the
    name. If the whole item is a bare number, nothing is extracted (there
    is no name to attach the quantity to).
    """
    text = normalize_digits(item).strip()
    m = _QUANTITY_TAIL.match(text)
    if m:
        quantity = int(m.group(2))
        if quantity <= QUANTITY_MAX:
            name = m.group(1).strip()
            if name:
                return name, quantity
    return text, None


def normalize_item_name(name: str) -> str:
    """Deduplication key for item names (not stored — display keeps case)."""
    normalized = normalize_digits(name).casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.strip(_EDGE_PUNCT)


@dataclasses.dataclass
class PlannedLink:
    """One prescription ← prescription_item link produced by the planner."""

    name: str  # display name (original spelling, whitespace-collapsed)
    quantity: int | None


@dataclasses.dataclass
class PlannedPrescription:
    """One prescription to create for a legacy appointment's rx text."""

    appointment_id: int
    patient_id: int
    prescribed_at: dt.datetime | None
    links: list[PlannedLink]  # admitted dictionary items only, deduped
    notes_overflow: str  # verbatim below-threshold item text ("", if none)


def plan_rx_migration(
    rows: Iterable[tuple[int, int, dt.datetime | None, str]],
    min_frequency: int = RX_MIN_FREQUENCY,
) -> tuple[list[PlannedPrescription], dict[str, str]]:
    """Plan the rx → prescriptions conversion for a corpus.

    ``rows``: (appointment_id, patient_id, prescribed_at, rx_text) — only
    rows with non-empty rx text need to be passed.

    Returns ``(prescriptions, dictionary)`` where ``dictionary`` maps the
    normalized name of every admitted item to its display spelling.

    Pass 1 counts normalized-name frequencies over the WHOLE corpus (so a
    name seen 100× across 100 appointments is admitted even though each
    occurrence is in a different prescription). Pass 2 builds one
    prescription per appointment: links for admitted items (deduplicated
    per prescription, first quantity wins) and the verbatim below-threshold
    text in ``notes_overflow``. Appointments whose rx yields neither links
    nor overflow (e.g. rx was only "---") are skipped entirely.
    """
    # --- pass 1: corpus-wide frequency of normalized names -------------------
    rows = list(rows)  # accept generators as well as sequences
    freq: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = {}
    for _aid, _pid, _at, rx in rows:
        for raw in split_rx_items(rx):
            name, _qty = extract_name_quantity(raw)
            key = normalize_item_name(name)
            if not key:
                continue
            freq[key] += 1
            spellings.setdefault(key, Counter())[re.sub(r"\s+", " ", name).strip()] += 1

    dictionary = {
        key: sorted(counter.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]
        for key, counter in spellings.items()
        if freq[key] >= min_frequency
    }

    # --- pass 2: build the per-appointment prescriptions ---------------------
    # rows is a possibly one-shot iterable — re-materialize for pass 2
    planned: list[PlannedPrescription] = []
    for appointment_id, patient_id, prescribed_at, rx in rows:
        links: list[PlannedLink] = []
        seen: set[str] = set()
        overflow: list[str] = []
        for raw in split_rx_items(rx):
            name, quantity = extract_name_quantity(raw)
            key = normalize_item_name(name)
            if not key:
                continue
            if key in dictionary:
                if key not in seen:  # duplicate within one prescription: keep first
                    seen.add(key)
                    links.append(PlannedLink(name=dictionary[key], quantity=quantity))
            else:
                overflow.append(re.sub(r"\s+", " ", raw).strip())
        if not links and not overflow:
            continue
        planned.append(
            PlannedPrescription(
                appointment_id=appointment_id,
                patient_id=patient_id,
                prescribed_at=prescribed_at,
                links=links,
                notes_overflow="\n".join(overflow),
            )
        )
    return planned, dictionary


def overflow_notes(notes_overflow: str, header: str = "سایر موارد نسخه قدیمی:") -> str:
    """Notes text for a migrated prescription (empty when nothing overflows)."""
    if not notes_overflow:
        return ""
    return f"{header}\n{notes_overflow}"
