"""Campaign delivery plans and source-backed counts across campaign workspaces."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import sqlite3

from app.core.column_filter import date_value
from app.utils.config import DB_PATH

STATUSES = ("Running", "Closed", "Paused")
HEADERS = ("Campaign name", "CID", "Total allocation", "Start date", "End date", "Total leads",
           "Qualified leads", "Disqualified leads", "Delivered leads", "Remaining to deliver",
           "Average leads per day", "Status")


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        parsed = date_value(value)
        return parsed.date() if parsed else None


def count_value(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).replace(",", "").strip())
        if number.is_finite() and 0 <= number <= 1_000_000_000 and number == number.to_integral_value():
            return int(number)
    except InvalidOperation:
        pass
    return None


def daily_target(allocation, start, end):
    if allocation is None or start is None or end is None or end < start:
        return None
    days = (end - start).days + 1
    return (allocation + days - 1) // days


@dataclass
class CampaignProgress:
    campaign_id: str
    campaign_name: str
    allocation: int | None = None
    start: date | None = None
    end: date | None = None
    total: int | None = 0
    qualified: int | None = 0
    disqualified: int | None = 0
    delivered: int | None = None
    status: str | None = None
    warning: str = ""

    @property
    def remaining(self):
        return max(0, self.allocation - self.delivered) if self.allocation is not None and self.delivered is not None else None

    @property
    def average(self):
        return daily_target(self.allocation, self.start, self.end)

    @property
    def pending(self):
        return self.total - self.qualified - self.disqualified if self.total is not None else None

    def pace_note(self, today=None):
        if self.average is None:
            return "Set a total allocation and a valid start/end date to calculate the daily delivery target."
        days = (self.end - self.start).days + 1
        note = f"Required daily target: {self.allocation:,} ÷ {days:,} calendar days, rounded up = {self.average:,} leads/day. Both dates are included."
        if self.remaining is not None:
            today = today or date.today()
            if self.remaining == 0:
                note += " Allocation delivered."
            elif today > self.end:
                note += f" Past the end date with {self.remaining:,} leads remaining."
            else:
                target = daily_target(self.remaining, max(today, self.start), self.end)
                note += f" From {max(today, self.start):%d-%b-%Y}: {target:,}/day is needed to deliver the remaining {self.remaining:,}."
        if self.status in {"Paused", "Closed"}:
            note += f" Campaign is {self.status.lower()}; the original plan target is shown."
        return note


class CampaignTrackingStore:
    def __init__(self, path=None):
        self.path = path or DB_PATH

    def all(self):
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            return {row["campaign_id"]: dict(row) for row in connection.execute("SELECT * FROM campaign_tracking")}

    def save(self, campaign_id, *, allocation, start, end, delivered, status):
        for label, value in (("Total allocation", allocation), ("Delivered leads", delivered)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000_000):
                raise ValueError(f"{label} must be a non-negative whole number.")
        if status is not None and status not in STATUSES:
            raise ValueError("Choose Running, Closed or Paused.")
        for value in (start, end):
            if value is not None and not isinstance(value, date):
                raise ValueError("Choose valid campaign dates.")
        if start and end and end < start:
            raise ValueError("End date cannot be before start date.")
        values = {"allocation": allocation, "start_date": start.isoformat() if start else None,
                  "end_date": end.isoformat() if end else None, "delivered": delivered, "status": status}
        with sqlite3.connect(self.path) as connection:
            if not connection.execute("SELECT 1 FROM campaign_profiles WHERE campaign_id=?", (campaign_id,)).fetchone():
                raise ValueError("This campaign no longer exists. Refresh the dashboard.")
            connection.execute("""INSERT INTO campaign_tracking(campaign_id, allocation, start_date, end_date, delivered, status)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(campaign_id) DO UPDATE SET
                allocation=excluded.allocation, start_date=excluded.start_date, end_date=excluded.end_date,
                delivered=excluded.delivered, status=excluded.status, updated_at=CURRENT_TIMESTAMP""",
                (campaign_id, allocation, values["start_date"], values["end_date"], delivered, status))
            connection.execute("INSERT INTO activity_history(event_type, summary, details_json) VALUES (?, ?, ?)",
                               ("campaign-plan", f"Updated delivery plan for {campaign_id}", json.dumps(values)))


def _record_counts(payload, indices=None):
    records = payload.get("records", [])
    states = payload.get("row_states", {})
    if not isinstance(states, dict):
        raise ValueError("Invalid saved validation states")
    try:
        dirty = {int(i) for i in payload.get("dirty_rows", [])}
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid saved validation state") from exc
    total = qualified = disqualified = 0
    for i in range(len(records)) if indices is None else indices:
        total += 1
        state = states.get(i, states.get(str(i), ""))
        if i in dirty or not isinstance(state, str) or not state or state == "Needs validation":
            continue
        if str(state).startswith("Valid"):
            qualified += 1
        elif records[i].get("QA Status") == "Disqualified":
            disqualified += 1
    return total, qualified, disqualified


def campaign_progress(controller):
    """Open worksheet comes from memory; every closed worksheet is read once."""
    profiles = controller.campaign_store.list()
    tracking = CampaignTrackingStore().all()
    warnings = []
    current = {"records": controller.data_manager.records, "row_states": controller.row_states,
               "dirty_rows": controller.dirty_rows}
    def read(key):
        return current if key == controller.workspace_key else (controller.workspace_store.load(key) or {"records": []})
    try:
        general = read("general")
        _record_counts(general)
    except ValueError:
        general = None
        warnings.append("General workspace could not be read; campaign lead counts are incomplete.")
    names = {}
    ids = {p.campaign_id.casefold(): p.campaign_id for p in profiles}
    for profile in profiles:
        names.setdefault(profile.campaign_name.strip().casefold(), set()).add(profile.campaign_id)
    groups = {profile.campaign_id: [] for profile in profiles}
    unassigned = []
    for i, record in enumerate((general or {}).get("records", [])):
        cid = str(record.get("CID") or record.get("Campaign ID") or "").strip().casefold()
        name = str(record.get("Campaign Name", "")).strip().casefold()
        explicit_cid = cid not in {"", "-"}
        match = ids.get(cid) if explicit_cid else ids.get(name)
        matches = names.get(name, set())
        if not explicit_cid and not match and len(matches) == 1:
            match = next(iter(matches))
        (groups[match] if match in groups else unassigned).append(i)
    output = []
    for profile in profiles:
        def rule(field):
            item = profile.rule(field, include_unconfirmed=False)
            return item.value if item else None
        saved = tracking.get(profile.campaign_id)
        plan = saved if saved is not None else {"allocation": rule("lead_goal"), "start_date": rule("start_date"), "end_date": rule("end_date")}
        item = CampaignProgress(profile.campaign_id, profile.campaign_name,
            allocation=count_value(plan.get("allocation")), start=parse_date(plan.get("start_date")),
            end=parse_date(plan.get("end_date")), delivered=count_value(plan.get("delivered")), status=plan.get("status"))
        try:
            own = read(controller.workspace_store.key(profile.campaign_id))
            own_counts = _record_counts(own)
            if general is None:
                raise ValueError("General workspace is unavailable.")
            general_counts = _record_counts(general, groups[profile.campaign_id])
            item.total, item.qualified, item.disqualified = (a+b for a, b in zip(own_counts, general_counts))
        except ValueError:
            item.total = item.qualified = item.disqualified = None
            item.warning = "Saved lead counts could not be read. Existing workspace files have been preserved."
            warnings.append(f"{profile.campaign_name}: lead counts unavailable.")
        output.append(item)
    if unassigned:
        item = CampaignProgress("", "Unassigned · General workspace")
        item.total, item.qualified, item.disqualified = _record_counts(general, unassigned)
        item.warning = "Set Campaign Name to a unique campaign name or CID to link these General workspace leads."
        warnings.append(f"{len(unassigned):,} General workspace leads are not linked to a unique saved campaign.")
        output.append(item)
    return output, warnings
