from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTabWidget, QTextBrowser, QVBoxLayout, QWidget


SECTIONS = {
    "Getting Started": """
<h2>Recommended workflow</h2>
<ol>
<li>Start in <b>Scraper</b>. Sign in to Chrome and choose a link file or Sales Navigator search.</li>
<li>Choose the destination workspace. Activate an imported campaign in <b>Campaign Manager</b>, or use <b>General workspace</b>.</li>
<li>Choose a results workbook, extract leads, then click <b>Add Results to Leads Workspace</b> to add them to the currently selected workspace.</li>
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
<p>Click the dropdown in any column header, right-click the header, or use Alt+Down in that column. Search and select values, include blanks, sort, or apply text, number and date conditions. Multiple column filters work together. A funnel marks filtered columns; Clear Filters removes every filter.</p>
<p>Choose Research, Email Finding or QA Review in View, or save your own selection of columns. Freeze Name / Company keeps identity columns visible. Column widths and saved views are remembered. When pasting into a reduced view, data fills the visible columns; choose All columns and turn off freezing for a complete worksheet paste.</p>
<p>Use Undo / Redo or Ctrl+Z / Ctrl+Y for cell edits, pasted data and cleared cells. Undo history belongs to the current editing session. Imports, reference changes, new worksheets and workspace switches start a new history. QA Status and Primary Reason are calculated by validation.</p>
<p>Import remembers successful column mappings for matching file layouts, including ignored columns. Review the mapping or use Reset to automatic mapping.</p>
<p>Export offers All leads, Qualified only, Disqualified only and Currently filtered rows. The export and its validation details contain the same selected rows, with the complete worksheet columns.</p>
""",
    "Campaign & Validation": """
<h2>Campaign Manager</h2>
<p>Imports campaign folders/ZIPs, classifies files, extracts rules and retains source traceability. PDF campaign specifications are intentionally excluded.</p>
<p>Each campaign has a separate saved worksheet, TAL, suppression and validation/email-search settings. Use Workspace above the grid to switch. The current worksheet is saved before switching and the last active workspace reopens on startup. General workspace keeps leads that have not been assigned to a campaign. Switching does not move leads between workspaces; import or transfer leads into the intended workspace.</p>
<h2>Validation</h2>
<p>Uploaded TAL and suppression lists are saved with the portable workspace and restored at startup, even if the original upload is moved. The saved file names and row counts appear under Reference lists. Uploading a replacement changes only that list and enables its matching rule. Manual uploads take priority over the corresponding campaign lists.</p>
<p>Click <b>Validate</b> to update <b>QA Status</b> and <b>Primary Reason</b>. Rows outside the TAL show <b>Disqualified / Tal not Mapped</b>. Confirmed suppression matches show <b>Disqualified / Suppression matched</b>; suppression takes priority when both rules fail. These columns are saved and exported with the leads.</p>
<p>Deterministic rules handle TAL, suppression, duplicates, required fields and confirmed campaign rules. Fuzzy matching produces review signals instead of silently accepting/rejecting records.</p>
<p>The Rows menu beside Validate checks selected rows or edited/unfinished rows. Related duplicate rows are included; active campaign domain caps require checking all rows. Edits show Needs validation, and these rows cannot enter Qualified exports until checked again.</p>
<p>QA Review opens the review panel for problem rows. Summary also opens it. Read the source list, matched identifier and next step, then use Go to field, Recheck row or Next issue.</p>
<p>Reference lists → Manage saved lists previews and searches uploaded lists, shows upload times, and replaces or removes them. Removing a manual list restores campaign references when available and marks leads for validation again.</p>
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
