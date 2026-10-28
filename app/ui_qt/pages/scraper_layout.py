"""Presentation-only layout for the extraction workspace."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)
from app.ui_qt.widgets.icons import icon


def label(text, style="muted", wrap=False):
    result = QLabel(text); result.setObjectName(style); result.setWordWrap(wrap)
    return result


def button(text, action, symbol=None, primary=False):
    result = QPushButton(text); result.clicked.connect(action)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary: result.setObjectName("primaryButton")
    if symbol: result.setIcon(icon(symbol, "#FFFFFF" if primary else "#71819B"))
    result.setIconSize(QSize(17, 17))
    return result


def section(parent, number, title):
    frame = QFrame(); frame.setObjectName("card")
    layout = QVBoxLayout(frame); layout.setContentsMargins(16, 16, 16, 16); layout.setSpacing(10)
    header = QHBoxLayout(); header.setSpacing(10)
    badge = label(number, "stepNumber"); badge.setFixedSize(28, 28); badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    header.addWidget(badge); header.addWidget(label(title, "sectionTitle")); header.addStretch(1)
    layout.addLayout(header); parent.addWidget(frame)
    return layout


class EmptyActivity(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(0, 0)
        layout = QVBoxLayout(self); layout.setContentsMargins(10, 6, 10, 6); layout.setSpacing(8)
        layout.addStretch(1)
        self.symbol = QLabel(); self.symbol.setPixmap(icon("scraper", "#239B8C", size=44).pixmap(44, 44))
        self.symbol.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(self.symbol)
        self.title = label("A clear view of every run", "sectionTitle", True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(self.title)
        self.note = label("Connect your browser, choose your source, and start extracting.\nLive progress and activity will appear here.", wrap=True)
        self.note.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(self.note)
        layout.addStretch(1)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def resizeEvent(self, event):
        self.symbol.setVisible(self.height() >= 160)
        self.note.setVisible(self.height() >= 110)
        super().resizeEvent(event)


def build(page):
    layout = QVBoxLayout(page); layout.setSpacing(18)
    heading = QHBoxLayout()
    titles = QVBoxLayout(); titles.setSpacing(5)
    titles.addWidget(label("EXTRACT & ENRICH", "eyebrow"))
    titles.addWidget(label("Lead extraction", "pageTitle"))
    titles.addWidget(label("Bring LinkedIn profiles, company details, and evidence into one workflow.", wrap=True))
    heading.addLayout(titles, 1)
    flow = label("01  Extract    /    02  Review    /    03  Validate", "badge")
    heading.addWidget(flow, 0, Qt.AlignmentFlag.AlignTop)
    layout.addLayout(heading)

    splitter = QSplitter(Qt.Orientation.Horizontal); splitter.setChildrenCollapsible(False); splitter.setHandleWidth(18)
    page.splitter = splitter; layout.addWidget(splitter, 1)
    left = QWidget(); left.setMinimumWidth(340); left.setMaximumWidth(440)
    ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(12)
    page.settings_tabs = QTabWidget(); ll.addWidget(page.settings_tabs, 1)
    areas = {}
    for title in ("Setup", "Options", "Tools"):
        body = QWidget(); body.setObjectName("scrollContent")
        body_l = QVBoxLayout(body); body_l.setContentsMargins(0, 14, 5, 2); body_l.setSpacing(12)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(body)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page.settings_tabs.addTab(scroll, title); areas[title] = body_l
    sl, ol, tl = (areas[k] for k in ("Setup", "Options", "Tools"))
    connection = section(sl, "01", "Connect your browser")
    page.browser_status = label("Use your dedicated browser to sign in to LinkedIn.", wrap=True)
    connection.addWidget(page.browser_status)
    page.open_button = button("Open Chrome / Sign In", page.open_browser, "browser")
    connection.addWidget(page.open_button)
    page.browser_progress = QProgressBar(); page.browser_progress.setFixedHeight(5); page.browser_progress.setTextVisible(False)
    page.browser_progress.hide(); connection.addWidget(page.browser_progress)
    source = section(sl, "02", "Choose your source")
    page.mode = QComboBox(); page.mode.addItems(["Link Scraper", "Sales Navigator"]); source.addWidget(page.mode)
    page.input_path = QLineEdit(); page.input_path.setReadOnly(True); page.input_path.setPlaceholderText("No link file selected")
    page.input_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed); source.addWidget(page.input_path)
    page.choose_input_button = button("Choose Excel / CSV Link File", page.choose_input, "upload"); source.addWidget(page.choose_input_button)
    page.file_info = label("All rows and worksheets will be read.", "metricHint", True); source.addWidget(page.file_info)
    page.file_progress = QProgressBar(); page.file_progress.setFixedHeight(5); page.file_progress.setTextVisible(False)
    page.file_progress.hide(); source.addWidget(page.file_progress)
    page.search_url = QLineEdit(); page.search_url.setPlaceholderText("Paste a Sales Navigator search URL")
    source.addWidget(page.search_url); page.mode.currentTextChanged.connect(page._mode_changed)
    output = section(sl, "03", "Set your destination")
    page.output_path = QLineEdit(); page.output_path.setReadOnly(True); page.output_path.setPlaceholderText("Choose a results workbook")
    page.output_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed); output.addWidget(page.output_path)
    page.choose_output_button = button("Choose Save Location", page.choose_output, "folder"); output.addWidget(page.choose_output_button)
    form = QFormLayout(); page.max_records = QSpinBox(); page.max_records.setRange(1, 1000000); page.max_records.setValue(25)
    form.addRow("Lead target", page.max_records); output.addLayout(form)
    page.all_links = QCheckBox("Process all links in the file"); page.all_links.setChecked(True)
    page.all_links.toggled.connect(page._mode_changed); output.addWidget(page.all_links)
    page.auto_transfer = QCheckBox("Add results to Leads Workspace\nwhen finished"); output.addWidget(page.auto_transfer)
    sl.addStretch(1)

    mode = section(ol, "01", "Extraction preferences")
    form = QFormLayout(); page.extraction_mode = QComboBox(); page.extraction_mode.addItems(["FAST", "SMART"])
    form.addRow("Mode", page.extraction_mode); mode.addLayout(form)
    mode.addWidget(label("SMART adds optional Qwen validation. Configure the local model in Settings.", wrap=True))
    page.headless = QCheckBox("Run browsers headless")
    page.parallel = QCheckBox("Parallel enrichment and email searches"); page.parallel.setChecked(True)
    page.parallel.setToolTip("Capture profiles first, then search missing emails with two isolated public-browser workers. Completed rows are saved and reused when you resume the same output workbook.")
    mode.addWidget(page.headless); mode.addWidget(page.parallel)
    quality = section(ol, "02", "Data & enrichment")
    page.local_office = QCheckBox("Find company office near prospect"); page.local_office.setChecked(True)
    page.refresh_profiles = QCheckBox("Refresh saved LinkedIn profiles")
    page.email_dns = QCheckBox("Check email domains (DNS/MX)")
    for control in (page.local_office, page.refresh_profiles, page.email_dns): quality.addWidget(control)
    quality.addWidget(label("Email lookup budget: 15 seconds per person. Incomplete searches can be retried.", wrap=True))
    quality.addWidget(label("DNS/MX checks send domains to Google DNS. They do not verify individual mailboxes.", wrap=True))
    ol.addStretch(1)
    bench = section(tl, "01", "Review data quality")
    page.sample_size = QSpinBox(); page.sample_size.setRange(1, 200); page.sample_size.setValue(150)
    form = QFormLayout(); form.addRow("Sample size", page.sample_size); bench.addLayout(form)
    page.benchmark_button = button("Build Offline Benchmark", page.build_benchmark, "dashboard"); bench.addWidget(page.benchmark_button)
    page.benchmark_progress = QProgressBar(); page.benchmark_progress.setFixedHeight(5); page.benchmark_progress.setTextVisible(False)
    page.benchmark_progress.hide(); bench.addWidget(page.benchmark_progress)
    bench.addWidget(label("Build a review sample from a saved workbook. No website requests.", wrap=True))
    session = section(tl, "02", "Browser session")
    page.clear_button = button("Clear Saved Browser Session", page.clear_browser, "browser"); session.addWidget(page.clear_button)
    session.addWidget(label("Clears the combined app's browser login. Sign in again before your next extraction.", wrap=True))
    tl.addStretch(1)

    footer = QFrame(); footer.setObjectName("card"); fl = QVBoxLayout(footer); fl.setContentsMargins(12, 12, 12, 12); fl.setSpacing(8)
    page.start_button = button("Start Link Scraper", page.start_processing, "play", True); page.start_button.setMinimumHeight(42)
    fl.addWidget(page.start_button)
    controls = QHBoxLayout(); controls.setSpacing(8)
    page.pause_button = button("Pause", page.pause, "pause")
    page.resume_button = button("Resume", page.resume, "play")
    page.stop_button = button("Stop", page.stop, "stop")
    for control in (page.pause_button, page.resume_button, page.stop_button):
        control.setEnabled(False); controls.addWidget(control)
    fl.addLayout(controls); ll.addWidget(footer); splitter.addWidget(left)

    right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(0, 4, 0, 0); rl.setSpacing(14)
    metrics = QHBoxLayout(); metrics.setSpacing(10); page.metric_values = {}
    for key, hint in (("Processed", "Profiles checked"), ("Saved", "Added to workbook"), ("Duplicates", "Already collected"), ("Failed", "Need attention")):
        card = QFrame(); card.setObjectName("metricCard")
        box = QVBoxLayout(card); box.setContentsMargins(16, 13, 16, 13); box.setSpacing(3)
        box.addWidget(label(key, "metricHint"))
        value = label("0", "miniMetric"); box.addWidget(value); page.metric_values[key] = value
        box.addWidget(label(hint, "metricHint", True)); metrics.addWidget(card, 1)
    rl.addLayout(metrics)
    run = QFrame(); run.setObjectName("card"); run_l = QVBoxLayout(run); run_l.setContentsMargins(18, 15, 18, 15); run_l.setSpacing(12)
    line = QHBoxLayout(); line.addWidget(label("Run overview", "sectionTitle")); line.addStretch(1)
    page.status = label("Ready to extract", "statusPill", True); page.status.setMaximumWidth(300); line.addWidget(page.status); run_l.addLayout(line)
    page.phase_progress = QProgressBar(); page.phase_progress.setRange(0, 0)
    page.phase_progress.setFixedHeight(4); page.phase_progress.setTextVisible(False)
    page.phase_progress.setAccessibleName("Current extraction task progress")
    page.phase_progress.hide(); run_l.addWidget(page.phase_progress)
    page.counters = label("Choose a source and destination to begin.", "muted", True); run_l.addWidget(page.counters)
    page.progress = QProgressBar(); page.progress.setRange(0, 100); page.progress.setValue(0)
    page.progress.setFixedHeight(7); page.progress.setTextVisible(False); run_l.addWidget(page.progress)
    line = QHBoxLayout(); page.harvest = label("Saved leads: 0", "metricHint"); line.addWidget(page.harvest); line.addStretch(1)
    page.percent_label = label("0% of target", "metricHint"); line.addWidget(page.percent_label); run_l.addLayout(line)
    rl.addWidget(run)

    activity = QFrame(); activity.setObjectName("card"); al = QVBoxLayout(activity); al.setContentsMargins(12, 5, 12, 12); al.setSpacing(8)
    page.preview_tabs = QTabWidget(); al.addWidget(page.preview_tabs, 1)
    page.activity_stack = QStackedWidget()
    page.activity_stack.addWidget(EmptyActivity())
    page.log_box = QPlainTextEdit(); page.log_box.setReadOnly(True); page.log_box.setMaximumBlockCount(3000); page.log_box.setObjectName("activityLog")
    page.activity_stack.addWidget(page.log_box)
    page.preview = QPlainTextEdit(); page.preview.setReadOnly(True); page.preview.setObjectName("activityLog")
    page.preview.setPlaceholderText("Your latest extracted lead will appear here with its profile and company details.")
    page.preview_tabs.addTab(page.activity_stack, "Activity log"); page.preview_tabs.addTab(page.preview, "Latest lead")
    note = label("Evidence and activity logs stay with your results workbook.", "metricHint"); al.addWidget(note)
    rl.addWidget(activity, 1)
    actions = QHBoxLayout(); actions.setSpacing(10)
    page.transfer_button = button("Add Results to Leads Workspace", page.transfer, "arrow")
    page.transfer_button.setObjectName("accentButton"); actions.addWidget(page.transfer_button, 1)
    page.open_output_button = button("Results Folder", page.open_output, "folder"); actions.addWidget(page.open_output_button)
    rl.addLayout(actions); splitter.addWidget(right); splitter.setStretchFactor(1, 1); splitter.setSizes([385, 800])
    page._mode_changed()
