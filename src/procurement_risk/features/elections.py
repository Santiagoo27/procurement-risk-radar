"""Colombian election calendar, for features known at signing time.

Ley 996 de 2005 (Ley de Garantías) restricts public contracting in the four months before
an election: direct contracting before presidential elections, and inter-administrative
agreements by territorial entities before any election. Entities facing that window tend to
extend running contracts instead of signing new ones. These features only mark where a
contract's signing and planned end fall relative to the calendar; they describe a pattern,
not a cause.
"""

from __future__ import annotations

from datetime import date, timedelta


def _sunday(year: int, month: int, nth: int) -> date:
    """The nth Sunday of a month; nth=-1 is the last one."""
    if nth > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (nth - 1))
    last = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - 6) % 7)


def election_days(first: int = 2018, last: int = 2040) -> tuple[date, ...]:
    """Ordinary election days by the legal calendar: Congress on the second Sunday of March
    and the President's first round on the last Sunday of May (2018, 2022, ...); regional
    authorities on the last Sunday of October (2019, 2023, ...)."""
    days = []
    for year in range(first, last + 1):
        if (year - 2018) % 4 == 0:
            days += [_sunday(year, 3, 2), _sunday(year, 5, -1)]
        if (year - 2019) % 4 == 0:
            days.append(_sunday(year, 10, -1))
    return tuple(days)


ELECTION_DAYS: tuple[date, ...] = election_days()
RESTRICTION_DAYS = 122  # four months


def _next_election(day_sql: str) -> str:
    """SQL for the first election day on or after `day_sql` (NULL after the calendar).

    A plain CASE, not a subquery: DuckDB decorrelates a per-row subquery by materializing
    the whole outer join, which costs gigabytes on the full contract table."""
    day = f"CAST({day_sql} AS DATE)"
    whens = " ".join(f"WHEN {day} <= DATE '{d.isoformat()}' THEN DATE '{d.isoformat()}'"
                     for d in sorted(ELECTION_DAYS))
    return f"(CASE {whens} END)"


def election_features_sql(signed_sql: str, start_sql: str, duration_sql: str) -> str:
    """SELECT-list SQL for the election features of one contract row."""
    end = f"(CAST(coalesce({start_sql}, {signed_sql}) AS DATE) + CAST({duration_sql} AS INTEGER))"
    to_signed = f"date_diff('day', CAST({signed_sql} AS DATE), {_next_election(signed_sql)})"
    to_end = f"date_diff('day', {end}, {_next_election(end)})"
    return (f"({to_signed} <= {RESTRICTION_DAYS})::INT AS signed_in_restriction,\n"
            f"            ({to_end} <= {RESTRICTION_DAYS})::INT AS planned_end_in_restriction,\n"
            f"            {to_end} AS days_end_to_next_election,")
