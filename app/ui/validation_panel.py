from __future__ import annotations

import customtkinter as ctk

from app.core.email_finder import EmailFindingResult


class ValidationPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, width=285)
        self.grid_propagate(False)
        self.labels: dict[str, ctk.CTkLabel] = {}

        title = ctk.CTkLabel(
            self,
            text="Validation Summary",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        title.pack(anchor="w", padx=12, pady=(10, 6))

        for key in (
            "Total Records",
            "Valid",
            "Warnings",
            "Invalid",
            "Suppressed",
            "Outside TAL",
            "Duplicates",
            "Missing Email",
            "Emails Found",
            "Manual Review",
        ):
            label = ctk.CTkLabel(self, text=f"{key}: 0", anchor="w")
            label.pack(fill="x", padx=12, pady=2)
            self.labels[key] = label

        ctk.CTkFrame(self, height=1, fg_color=("#D0D0D0", "#444444")).pack(
            fill="x", padx=10, pady=(10, 8)
        )
        ctk.CTkLabel(
            self,
            text="Reference Lists",
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).pack(fill="x", padx=12, pady=(0, 3))
        self.tal_label = ctk.CTkLabel(self, text="TAL: Not loaded", anchor="w", wraplength=255, justify="left")
        self.tal_label.pack(fill="x", padx=12, pady=1)
        self.suppression_label = ctk.CTkLabel(self, text="Suppression: Not loaded", anchor="w", wraplength=255, justify="left")
        self.suppression_label.pack(fill="x", padx=12, pady=1)

        ctk.CTkFrame(self, height=1, fg_color=("#D0D0D0", "#444444")).pack(
            fill="x", padx=10, pady=(10, 8)
        )
        self.detail_title = ctk.CTkLabel(
            self,
            text="Selected Record",
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        )
        self.detail_title.pack(fill="x", padx=12, pady=(0, 4))

        self.detail_box = ctk.CTkTextbox(self, width=258, height=260, wrap="word")
        self.detail_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.show_record(None, None, [])

    def update_summary(self, summary: dict[str, int]) -> None:
        for key, label in self.labels.items():
            label.configure(text=f"{key}: {summary.get(key, 0):,}")

    def update_reference_lists(
        self,
        *,
        tal_name: str | None = None,
        tal_count: int = 0,
        suppression_name: str | None = None,
        suppression_count: int = 0,
    ) -> None:
        self.tal_label.configure(
            text=(f"TAL: {tal_name} ({tal_count:,})" if tal_name else "TAL: Not loaded")
        )
        self.suppression_label.configure(
            text=(
                f"Suppression: {suppression_name} ({suppression_count:,})"
                if suppression_name
                else "Suppression: Not loaded"
            )
        )

    def show_record(
        self,
        row_number: int | None,
        status: str | None,
        reasons: list[str] | None,
        *,
        tal_status: str | None = None,
        tal_reason: str | None = None,
        suppression_status: str | None = None,
        suppression_reason: str | None = None,
        duplicate_status: str | None = None,
        email_result: EmailFindingResult | None = None,
    ) -> None:
        self.detail_box.configure(state="normal")
        self.detail_box.delete("1.0", "end")
        if row_number is None:
            self.detail_title.configure(text="Selected Record")
            text = "Select a record to view its validation details."
        else:
            self.detail_title.configure(text=f"Selected Record — Row {row_number:,}")
            if status:
                sections = [f"Final Status: {status}"]
                if tal_status:
                    sections.append(f"\nTAL Match: {tal_status}\n{tal_reason or ''}".rstrip())
                if suppression_status:
                    sections.append(
                        f"\nSuppression: {suppression_status}\n{suppression_reason or ''}".rstrip()
                    )
                if duplicate_status:
                    sections.append(f"\nDuplicate: {duplicate_status}")
                if email_result is not None:
                    email_lines = [f"\nEmail Engine: {email_result.status}"]
                    if email_result.candidate and email_result.candidate != "-":
                        email_lines.append(f"Candidate: {email_result.candidate}")
                    if email_result.pattern:
                        email_lines.append(f"Pattern: {email_result.pattern}")
                    email_lines.append(f"Confidence: {email_result.confidence}%")
                    if email_result.evidence_count:
                        email_lines.append(f"Evidence Count: {email_result.evidence_count}")
                    if email_result.source:
                        email_lines.append(f"Source: {email_result.source}")
                    if email_result.discovery_status:
                        cache_text = " (cached)" if email_result.discovery_cached else ""
                        email_lines.append(
                            f"Web Discovery: {email_result.discovery_status}{cache_text}"
                        )
                    if email_result.discovery_provider:
                        email_lines.append(f"Search Provider: {email_result.discovery_provider}")
                    if email_result.web_query_count:
                        email_lines.append(f"Search Queries: {email_result.web_query_count}")
                    if email_result.evidence_sources:
                        email_lines.append("Evidence Sources:")
                        for source_url in email_result.evidence_sources[:5]:
                            email_lines.append(f"  • {source_url}")
                        if len(email_result.evidence_sources) > 5:
                            email_lines.append(
                                f"  • +{len(email_result.evidence_sources) - 5} more source(s)"
                            )
                    if email_result.reason:
                        email_lines.append(f"Reason: {email_result.reason}")
                    sections.append("\n".join(email_lines))
                reason_lines = "\n".join(f"• {reason}" for reason in (reasons or []))
                sections.append(f"\nValidation Reason(s):\n{reason_lines or '• None'}")
                text = "\n".join(sections)
            else:
                text = "This record has not been validated yet. Click VALIDATE to run the current validation checks."
        self.detail_box.insert("1.0", text)
        self.detail_box.configure(state="disabled")


class ValidationSummaryWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Validation Summary")
        self.geometry("360x720")
        self.minsize(320, 560)
        self.transient(master)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.panel = ValidationPanel(self)
        self.panel.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
