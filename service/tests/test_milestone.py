from datetime import date

from service.channels import milestone
from service.compose import CHARSET, COLS, ROWS


def _decode(grid: list[int]) -> str:
    rows = []
    for r in range(ROWS):
        row = grid[r * COLS : (r + 1) * COLS]
        rows.append("".join(CHARSET.char_for(c) or " " for c in row))
    return "\n".join(rows)


def test_computes_days_since_reference_date(monkeypatch):
    class _FixedDate(date):
        @classmethod
        def today(cls):
            return date(2025, 11, 10)  # 2 days after the reference date

    monkeypatch.setattr(milestone, "date", _FixedDate)

    message = milestone.run()
    text = _decode(message.grid)
    assert "2 DAYS OLD" in text


def test_reference_date_itself_is_zero_days(monkeypatch):
    class _FixedDate(date):
        @classmethod
        def today(cls):
            return milestone.REFERENCE_DATE

    monkeypatch.setattr(milestone, "date", _FixedDate)

    message = milestone.run()
    assert "0 DAYS OLD" in _decode(message.grid)


def test_channel_registered_with_correct_schedule():
    assert milestone.CHANNEL.name == "milestone"
    assert milestone.CHANNEL.cron == "0 8 * * *"  # 8:00am daily, per build plan §11


def test_output_is_a_valid_full_grid():
    message = milestone.run()
    assert len(message.grid) == ROWS * COLS
    assert message.text is None  # uses the banner template, not raw text
