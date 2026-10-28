from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTabWidget, QTextBrowser, QVBoxLayout, QWidget


SECTIONS = {
    "Getting Started": """
<h2>Recommended workflow</h2>
<ol>
<li>Start in <b>Scraper</b>. Sign in to Chrome and choose a link file or Sales Navigator search.</li>
<li>Choose a results workbook, extract leads, then click <b>Add Results to Leads Workspace</b>.</li>
<li>Import or create a campaign profile in <b>Campaign Manager</b>.</li>
<li>Open <b>Leads Workspace</b> and import/paste lead data.</li>
<li>Load TAL/Suppression manually when a campaign package does not provide them.</li>
<li>Run <b>VALIDATE</b>.</li>
<li>Review Validation Summary, row colors and detailed reasons.</li>
<li>Use <b>Find Emails</b> and optional Qwen tools only where needed.</li>
<li>Resolve warnings/manual-review rows, then export.</li>
</ol>
<p>Repeated transfers skip existing LinkedIn profiles and preserve your manual edits. Extraction evidence stays in the original results workbook; Lead Manager exports contain the reviewed leads and QA details.</p>
<p>This combined copy has its own settings and browser profile. Your original applications are unchanged. Use Ctrl+1 for Scraper and Ctrl+2 for Leads Workspace.</p>
""",
    "Leads Workspace": """
<h2>Excel-style workspace</h2>
<p>Double-click or press F2 to edit. Tab/Enter/Arrow keys navigate cells. Ctrl+C/X/V/A are supported.</p>
<p>Right-click a column header to open Excel-style value filtering. Search and status filters can be combined.</p>
""",
    "Campaign & Validation": """
<h2>Campaign Manager</h2>
<p>Imports campaign folders/ZIPs, classifies files, extracts rules and retains source traceability. PDF campaign specifications are intentionally excluded.</p>
<h2>Validation</h2>
<p>Uploaded TAL and suppression lists are saved with the portable workspace and restored at startup, even if the original upload is moved. The saved file names and row counts appear under Reference lists. Uploading a replacement changes only that list and enables its matching rule. Manual uploads take priority over the corresponding campaign lists.</p>
<p>Click <b>Validate</b> to update <b>QA Status</b> and <b>Primary Reason</b>. Rows outside the TAL show <b>Disqualified / Tal not Mapped</b>. Confirmed suppression matches show <b>Disqualified / Suppression matched</b>; suppression takes priority when both rules fail. These columns are saved and exported with the leads.</p>
<p>Deterministic rules handle TAL, suppression, duplicates, required fields and confirmed campaign rules. Fuzzy matching produces review signals instead of silently accepting/rejecting records.</p>
""",
    "Local Qwen / AI": """
<h2>Local Qwen</h2>
<p>Qwen is optional and runs as a separate localhost process. The desktop application stays usable when it is off.</p>
<p>AI is used for ambiguous requirement reading, rule suggestions, normalization, QA assistance, explanations and campaign intelligence. Exact validation remains deterministic.</p>
""",
    "Status & Colors": """
<h2>Validation colors</h2>
<p><b>Outside TAL</b> defaults to red and <b>Suppressed</b> defaults to orange. Both can be changed in Settings.</p>
<p>Rows are never silently deleted because of a validation failure.</p>
""",
}


class InfoPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        title = QLabel("Info. & User Guide")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        tabs = QTabWidget()
        for name, html in SECTIONS.items():
            browser = QTextBrowser()
            browser.setHtml(html)
            tabs.addTab(browser, name)
        root.addWidget(tabs, 1)
