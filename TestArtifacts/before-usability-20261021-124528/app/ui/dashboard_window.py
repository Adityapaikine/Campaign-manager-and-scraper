from __future__ import annotations

from collections import Counter

import customtkinter as ctk

from app.constants import MISSING_VALUE


class DashboardWindow(ctk.CTkToplevel):
    """Production QA dashboard derived from the current in-memory worksheet."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Validation Dashboard")
        self.geometry("980x680")
        self.minsize(780, 520)
        self.transient(master)

        ctk.CTkLabel(self, text="Validation Dashboard", font=ctk.CTkFont(size=21, weight="bold")).pack(
            anchor="w", padx=18, pady=(16, 8)
        )
        self.summary_label = ctk.CTkLabel(self, text="", anchor="w")
        self.summary_label.pack(fill="x", padx=18, pady=(0, 8))

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        for name in ("Campaign", "Status", "Validation Reasons", "Email", "Data Completeness"):
            self.tabs.add(name)

        self.boxes: dict[str, ctk.CTkTextbox] = {}
        for name in ("Campaign", "Status", "Validation Reasons", "Email", "Data Completeness"):
            box = ctk.CTkTextbox(self.tabs.tab(name), wrap="none")
            box.pack(fill="both", expand=True, padx=8, pady=8)
            self.boxes[name] = box

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(footer, text="Refresh", width=100, command=self.refresh).pack(side="right")
        self.refresh()

    @staticmethod
    def _render_counts(title: str, counts: Counter[str], total: int) -> str:
        lines = [title, "=" * len(title), ""]
        if not counts:
            lines.append("No results available yet.")
            return "\n".join(lines)
        width = max(len(str(key)) for key in counts)
        for key, count in counts.most_common():
            pct = (count / total * 100.0) if total else 0.0
            lines.append(f"{str(key):<{width}}  {count:>8,}  {pct:>6.1f}%")
        return "\n".join(lines)

    def _set_box(self, name: str, text: str) -> None:
        box = self.boxes[name]
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")

    def refresh(self) -> None:
        records = list(getattr(self.master.data_manager, "records", []))
        total = len(records)
        row_states = getattr(self.master, "row_states", {})
        reasons = getattr(self.master, "validation_reasons", {})

        status_counts: Counter[str] = Counter()
        for index in range(total):
            status_counts[row_states.get(index, "Not Validated")] += 1
        self._set_box("Status", self._render_counts("Final Status", status_counts, total))

        reason_counts: Counter[str] = Counter()
        for values in reasons.values():
            for reason in values:
                reason_counts[str(reason)] += 1
        self._set_box("Validation Reasons", self._render_counts("Validation Reasons", reason_counts, max(1, total)))

        email_counts: Counter[str] = Counter()
        missing_email = 0
        for row in records:
            status = str(row.get("Email Status", MISSING_VALUE) or MISSING_VALUE)
            email_counts[status] += 1
            if str(row.get("Business Email ID", MISSING_VALUE)).strip() in {"", MISSING_VALUE}:
                missing_email += 1
        email_text = self._render_counts("Email Status", email_counts, total)
        email_text += f"\n\nMissing Business Email ID: {missing_email:,}"
        self._set_box("Email", email_text)

        important = (
            "First Name", "Last Name", "Company Name", "Company Website", "Business Email ID",
            "Prospect LinkedIn Link", "Job Title", "Country", "Phone Number",
        )
        completeness: Counter[str] = Counter()
        lines = ["Field Completeness", "==================", ""]
        for field in important:
            present = sum(1 for row in records if str(row.get(field, MISSING_VALUE)).strip() not in {"", MISSING_VALUE})
            missing = total - present
            pct = (present / total * 100.0) if total else 0.0
            lines.append(f"{field:<28} Present {present:>7,} | Missing {missing:>7,} | {pct:>6.1f}% complete")
            completeness[field] = present
        self._set_box("Data Completeness", "\n".join(lines))

        profile = getattr(self.master, "active_campaign_profile", None)
        campaign_lines = ["Campaign Dashboard", "==================", ""]
        if profile is None:
            campaign_lines.append("No campaign profile is active.")
        else:
            campaign_lines.extend([
                f"Campaign ID: {profile.campaign_id}",
                f"Campaign Name: {profile.campaign_name}",
                f"Active rules: {sum(1 for r in profile.rules if r.status in {'Confirmed', 'Extracted'})}",
                f"Rules needing review: {sum(1 for r in profile.rules if r.status == 'Needs Review')}",
                f"Source files: {len(profile.files)}",
                "",
                "Current data impact",
                "-------------------",
            ])
            for status, count in status_counts.most_common():
                pct = (count / total * 100.0) if total else 0.0
                campaign_lines.append(f"{status:<26} {count:>8,}  {pct:>6.1f}%")
            if reason_counts:
                campaign_lines.extend(["", "Top validation constraints", "--------------------------"])
                for reason, count in reason_counts.most_common(10):
                    campaign_lines.append(f"{count:>7,}  {reason}")
            email_coverage = ((total - missing_email) / total * 100.0) if total else 0.0
            campaign_lines.extend(["", f"Business email coverage: {email_coverage:.1f}%"])
        self._set_box("Campaign", "\n".join(campaign_lines))

        validated = sum(count for status, count in status_counts.items() if status != "Not Validated")
        self.summary_label.configure(
            text=f"Records: {total:,}   •   Validated results: {validated:,}   •   Missing email: {missing_email:,}"
        )
