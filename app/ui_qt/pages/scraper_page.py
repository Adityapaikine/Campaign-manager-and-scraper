"""Qt presentation for the copied Scraper engine; all browsing stays in its worker."""
from __future__ import annotations

import json
from pathlib import Path
import queue
import shutil
import threading
import time
from urllib.parse import urlsplit

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from suite_bootstrap import ROOT, configure
from app.ui_qt.module_guard import authorized
configure()
import Scraper as engine


class SuiteSearchWorker(engine.SearchWorker):
    def run(self):
        try:
            super().run()
        except Exception as exc:
            self.log(f"Scraper worker stopped: {type(exc).__name__}: {exc}")
            self.status("Error — see activity log")
            self.callbacks["done"]()


class ScraperPage(QWidget):
    transfer_requested = Signal(str)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.worker = None
        self.workbook = None
        self.processing = False
        self.events = queue.Queue()
        self.activity_log_path = ""
        self.activity_log_lock = threading.Lock()
        self._shutdown_callback = None
        self._closing = False
        self._clear_requested = False
        self._last_status = "Ready"
        self._file_loading = False
        self._loaded_links = None
        self._file_signature = None
        self._input_total = 0
        self._browser_opening = False
        self._benchmark_running = False
        self._preparing = False
        self._cancel_preparation = False
        self._run_started = None
        self._elapsed_shown = -1
        self._run_progress = (0, 0, 0, 0, 0)
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._drain_events)
        self.timer.start(80)

    def _build_ui(self):
        from app.ui_qt.pages.scraper_layout import build
        build(self)

    def _mode_changed(self, *_):
        links = self.mode.currentText() == "Link Scraper"
        self.input_path.setVisible(links); self.choose_input_button.setVisible(links)
        self.search_url.setVisible(not links)
        self.file_info.setVisible(links)
        self.all_links.setVisible(links)
        self.max_records.setEnabled(not (self.processing or self._file_loading or self._browser_opening or self._closing or self._clear_requested) and not (links and self.all_links.isChecked()))
        self.start_button.setText("Start Link Scraper" if links else "Start Sales Navigator")

    def _ensure_worker(self):
        if self.worker and self.worker.is_alive():
            return self.worker
        callbacks = {name: (lambda *args, event=name: self.events.put((event, args)))
                     for name in ("log", "status", "progress", "record", "harvest", "done", "input_total", "email_progress")}
        callbacks["trace"] = self._trace
        self.worker = SuiteSearchWorker(callbacks)
        self.worker.start()
        return self.worker

    def _trace(self, category, payload):
        if not self.activity_log_path:
            return
        entry = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "category": category, **payload}
        try:
            with self.activity_log_lock:
                with open(self.activity_log_path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass

    def _log(self, message):
        self.activity_stack.setCurrentWidget(self.log_box)
        self.log_box.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {message}")
        self._trace("ACTIVITY", {"message": message})

    def _drain_events(self):
        for _ in range(250):
            try:
                kind, args = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log": self._log(str(args[0]))
            elif kind == "status":
                self._last_status = str(args[0]); self.status.setText(self._last_status)
                self.phase_progress.setVisible(self.processing and self._last_status.lower() not in {"paused", "stopped", "finished", "error"})
                if "chrome" in self._last_status.lower() or "browser" in self._last_status.lower():
                    self.browser_status.setText(self._last_status)
                if self._browser_opening and any(word in self._last_status.lower() for word in ("ready", "sign-in", "error")):
                    self._browser_opening = False
                    self.browser_progress.hide(); self._set_running(self.processing)
                if self.processing and "saving results" in self._last_status.lower():
                    self.progress.setRange(0, 0)
                    self.percent_label.setText("Saving workbook…")
            elif kind == "progress":
                processed, saved, duplicates, failed, total = args
                for name, value in zip(("Processed", "Saved", "Duplicates", "Failed"), (processed, saved, duplicates, failed)):
                    self.metric_values[name].setText(f"{value:,}")
                self._run_progress = args
                self._show_run_progress()
            elif kind == "email_progress":
                done, total = args
                self.phase_progress.setRange(0, max(1, total))
                self.phase_progress.setValue(done)
                self.progress.setRange(0, max(1, total)); self.progress.setValue(done)
                self.percent_label.setText(f"Emails: {done:,} / {total:,} saved")
            elif kind == "input_total": self._input_total = args[0]
            elif kind == "file_progress":
                done, total = args
                self.file_progress.setRange(0, total)
                self.file_progress.setValue(done)
                self.file_info.setText(f"Reading file · {done:,} rows scanned")
            elif kind == "file_loaded":
                items, signature, error = args
                self._file_loading = False
                self._loaded_links = items; self._file_signature = signature
                self.file_progress.setRange(0, 100); self.file_progress.setValue(100 if not error else 0)
                if error:
                    self.file_info.setText("File could not be read")
                    QMessageBox.warning(self, "Link file", error)
                else:
                    valid = len({item.canonical for item in items if item.canonical})
                    self.file_info.setText(f"{valid:,} unique LinkedIn links · {len(items):,} URLs loaded. No row limit.")
                    self._log(f"Loaded {len(items):,} URL entries; {valid:,} unique supported LinkedIn links from {self.input_path.text()}")
                self._set_running(self.processing)
            elif kind == "prepared":
                workbook, error = args
                self._preparing = False
                if error or self._cancel_preparation or self._closing:
                    if workbook: workbook.wb.close()
                    self._set_running(False); self.progress.setRange(0, 100); self.progress.setValue(0)
                    self.status.setText("Could not prepare workbook" if error else "Preparation cancelled")
                    if error: QMessageBox.critical(self, "Cannot prepare workbook", error)
                else:
                    self._begin_extraction(workbook)
            elif kind == "harvest": self.harvest.setText(f"Saved leads: {args[0]:,} / {args[1]:,}")
            elif kind == "record": self.preview.setPlainText("\n".join(f"{key}: {args[0].get(key, '-')}" for key in engine.HEADERS))
            elif kind == "done": self._processing_done()
            elif kind == "benchmark":
                self._benchmark_running = False
                self.benchmark_button.setEnabled(True)
                self.benchmark_progress.hide()
                result, error = args
                if self._closing: continue
                if error: QMessageBox.warning(self, "Benchmark", error)
                else:
                    self._log(f"Offline benchmark saved: {result['output_dir']}")
                    QMessageBox.information(self, "Benchmark complete", f"Saved the sample and review files to:\n{result['output_dir']}")
        if self.processing and self._run_started:
            elapsed = int(time.monotonic() - self._run_started)
            if elapsed != self._elapsed_shown:
                self._elapsed_shown = elapsed
                processed, saved = self._run_progress[:2]
                self.counters.setText(f"{processed:,} checked · {saved:,} saved · {elapsed // 60}m {elapsed % 60:02}s elapsed")
        if self._clear_requested and (not self.worker or not self.worker.is_alive()):
            self.browser_progress.hide()
            self._clear_requested = False
            try:
                if engine.CHROME_PROFILE_DIR.exists(): shutil.rmtree(engine.CHROME_PROFILE_DIR)
                self.browser_status.setText("Browser session cleared. Sign in again before scraping.")
            except OSError as exc:
                QMessageBox.warning(self, "Could not clear session", str(exc))
            self._set_running(False)
        if self._shutdown_callback and not (self._preparing or self._file_loading or self._benchmark_running) and (not self.worker or not self.worker.is_alive()):
            callback, self._shutdown_callback = self._shutdown_callback, None
            self.timer.stop(); QTimer.singleShot(0, callback)

    def _show_run_progress(self):
        processed, saved, duplicates, failed, total = self._run_progress
        self.progress.setRange(0, 100)
        is_links = self.mode.currentText() == "Link Scraper"
        done, goal = (processed, self._input_total) if is_links else (saved, total)
        percent = min(100, int(done / max(goal, 1) * 100))
        self.progress.setValue(percent)
        elapsed = int(time.monotonic() - self._run_started) if self._run_started else 0
        self.counters.setText(f"{processed:,} checked · {saved:,} saved · {elapsed // 60}m {elapsed % 60:02}s elapsed")
        self.percent_label.setText(f"{percent}% · {done:,}/{goal:,} " + ("links" if is_links else "target"))

    @staticmethod
    def _signature(path):
        file = Path(path); stat = file.stat()
        return (str(file.resolve()), stat.st_size, stat.st_mtime_ns)

    def choose_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose profile-link input", str(ROOT), "Excel / CSV (*.xlsx *.xlsm *.csv)")
        if path: self.load_input(path)

    @authorized('scraper')
    def load_input(self, path):
        self.input_path.setText(path); self._file_loading = True
        self._loaded_links = None; self._file_signature = None
        self.file_progress.setRange(0, 0); self.file_progress.show()
        self.file_info.setText("Reading every row and worksheet…")
        self._set_running(False)
        def read():
            try:
                signature = self._signature(path)
                items = engine.SearchWorker._load_link_inputs(None, path,
                    progress_callback=lambda d, t: self.events.put(("file_progress", (d, t))))
                if signature != self._signature(path):
                    raise ValueError("The input file changed while being read. Select it again.")
                self.events.put(("file_loaded", (items, signature, "")))
            except Exception as exc:
                self.events.put(("file_loaded", (None, None, str(exc))))
        threading.Thread(target=read, daemon=True).start()

    def choose_output(self):
        default = ROOT / "Output" / f"Scraper_Results_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Choose new workbook or append to existing", str(default), "Excel workbook (*.xlsx)", options=QFileDialog.Option.DontConfirmOverwrite)
        if path:
            if Path(path).suffix.lower() != ".xlsx": path += ".xlsx"
            self.output_path.setText(path)

    @authorized('scraper')
    def open_browser(self):
        self._browser_opening = True
        self.browser_status.setText("Opening Chrome…")
        self.browser_progress.setRange(0, 0); self.browser_progress.show()
        self._set_running(False)
        self._ensure_worker().send("open_browser")

    def _set_running(self, running):
        self.processing = running
        self.phase_progress.setRange(0, 0)
        self.phase_progress.setVisible(running)
        for control in (self.mode, self.input_path, self.search_url, self.choose_input_button,
                        self.choose_output_button, self.max_records, self.extraction_mode,
                        self.headless, self.parallel, self.local_office, self.refresh_profiles,
                        self.email_dns, self.start_button, self.open_button, self.clear_button,
                        self.transfer_button, self.all_links):
            control.setEnabled(not running and not self._closing and not self._clear_requested and not self._file_loading and not self._browser_opening)
        self._mode_changed()
        self.pause_button.setEnabled(running and not self._closing and not self._preparing)
        self.resume_button.setEnabled(False); self.stop_button.setEnabled(running and not self._closing)

    @authorized('scraper')
    def start_processing(self):
        if self.processing or self._closing or self._file_loading or self._browser_opening: return
        links = self.mode.currentText() == "Link Scraper"
        if links and not Path(self.input_path.text()).is_file():
            QMessageBox.warning(self, "Choose input", "Choose an existing Excel or CSV file containing LinkedIn links."); return
        try:
            parsed = urlsplit(self.search_url.text().strip())
            host = (parsed.hostname or "").lower()
        except ValueError:
            QMessageBox.warning(self, "Search URL", "Enter a valid LinkedIn Sales Navigator URL."); return
        if not links and not (parsed.scheme in {"https", "http"} and (host == "linkedin.com" or host.endswith(".linkedin.com")) and parsed.path.startswith("/sales/")):
            QMessageBox.warning(self, "Search URL", "Paste a LinkedIn Sales Navigator search URL."); return
        if not self.output_path.text(): self.choose_output()
        if not self.output_path.text(): return
        output = Path(self.output_path.text()).resolve()
        if links and output == Path(self.input_path.text()).resolve():
            QMessageBox.warning(self, "Choose another output", "Save the results to a different file from your input links."); return
        if links and self._loaded_links is not None and self._signature(self.input_path.text()) != self._file_signature:
            self.load_input(self.input_path.text())
            self._log("Input file changed. Reloading it; start again when loading finishes.")
            return
        self._preparing = True; self._cancel_preparation = False
        self._set_running(True); self.progress.setRange(0, 0)
        self.status.setText("Preparing workbook…"); self.percent_label.setText("Preparing workbook…")
        def prepare():
            try:
                output.parent.mkdir(parents=True, exist_ok=True)
                workbook = engine.WorkbookManager(str(output), checkpoint_every=engine.EXCEL_CHECKPOINT_EVERY)
                self.events.put(("prepared", (workbook, "")))
            except Exception as exc:
                self.events.put(("prepared", (None, str(exc))))
        threading.Thread(target=prepare, daemon=True).start()

    @authorized('scraper')
    def _begin_extraction(self, workbook):
        if self._cancel_preparation or self._closing:
            workbook.wb.close(); self._set_running(False); self.status.setText('Preparation cancelled'); return
        self.workbook = workbook
        output = Path(self.output_path.text()).resolve()
        links = self.mode.currentText() == "Link Scraper"
        self.activity_log_path = str(output.with_name(output.stem + "_activity.log"))
        worker = self._ensure_worker()
        settings = self.controller.settings
        worker.llm = engine.LocalLLMClient(base_url=f"http://{settings.qwen_host}:{settings.qwen_port}", trace_callback=worker._local_llm_trace)
        worker.llm_available = None; worker.llm_last_check_ts = 0
        payload = {
            "input_path": self.input_path.text(), "search_url": self.search_url.text().strip(),
            "max_records": 0 if links and self.all_links.isChecked() else self.max_records.value(), "workbook": self.workbook,
            "extraction_mode": self.extraction_mode.currentText(), "email_domain_checks": self.email_dns.isChecked(),
            "email_batch_workers": 2 if self.parallel.isChecked() else 1,
            "headless": self.headless.isChecked(), "enrichment_sessions": 2 if self.parallel.isChecked() else 1,
            "prefer_local_office": self.local_office.isChecked(), "persistent_cache": True,
            "refresh_profiles": self.refresh_profiles.isChecked(),
        }
        if links and self._loaded_links is not None:
            payload["link_inputs"] = self._loaded_links
        self._run_started = time.monotonic(); self._input_total = len(self._loaded_links or [])
        self._run_progress = (0, 0, 0, 0, 0)
        self._set_running(True); self.progress.setRange(0, 0)
        self.status.setText("Starting extraction…"); self._last_status = "Starting"
        for value in self.metric_values.values(): value.setText("0")
        self.counters.setText("Processing all uploaded links." if links and self.all_links.isChecked() else f"Target: {self.max_records.value():,} saved leads."); self.harvest.setText("Saved leads: 0")
        self.percent_label.setText("Starting…")
        self._log(f"{self.mode.currentText()} started. Results: {output}")
        worker.send("process_links" if links else "process", payload)

    def pause(self):
        if self.worker and self.processing:
            self.worker.send("pause"); self.pause_button.setEnabled(False); self.resume_button.setEnabled(True)
            self.status.setText("Pause requested")

    @authorized('scraper')
    def resume(self):
        if self.worker and self.processing:
            self.worker.send("resume"); self.pause_button.setEnabled(True); self.resume_button.setEnabled(False)
            self.status.setText("Running")

    def stop(self):
        self._cancel_preparation = True
        if self._preparing:
            self._cancel_preparation = True
            self.status.setText("Cancelling workbook preparation…")
            return
        if self.worker and self.processing:
            self.worker.send("stop"); self.status.setText("Stopping after the current operation; saving results…")
            self.pause_button.setEnabled(False); self.resume_button.setEnabled(False); self.stop_button.setEnabled(False)

    def module_action_denied(self,method,args):
        if method=='_begin_extraction' and args:
            args[0].wb.close()
        self._browser_opening=False; self.browser_progress.hide()

    def _processing_done(self):
        was_processing = self.processing
        self._show_run_progress()
        self._set_running(False)
        if was_processing:
            self._log(f"Extraction ended ({self._last_status}). Review results and the activity log before validation.")
            if self.auto_transfer.isChecked() and not self._closing and "error" not in self._last_status.lower():
                self.transfer()

    @authorized('scraper')
    def transfer(self):
        if self.processing: return
        path = self.output_path.text()
        if not path or not Path(path).is_file():
            path, _ = QFileDialog.getOpenFileName(self, "Choose saved Scraper results", str(ROOT / "Output"), "Excel workbook (*.xlsx *.xlsm)")
        if path: self.transfer_requested.emit(path)

    @authorized('scraper')
    def open_output(self):
        path = Path(self.output_path.text()).parent if self.output_path.text() else ROOT / "Output"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @authorized('scraper')
    def build_benchmark(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose workbook for offline benchmark", str(ROOT / "Output"), "Excel workbook (*.xlsx)")
        if not path: return
        sample = self.sample_size.value(); self.benchmark_button.setEnabled(False)
        self._benchmark_running = True
        self.benchmark_progress.setRange(0, 0); self.benchmark_progress.show()
        def work():
            try:
                from benchmark import build_benchmark
                result = build_benchmark(path, Path(path).parent / "benchmarks", sample_size=sample)
                self.events.put(("benchmark", (result, "")))
            except Exception as exc: self.events.put(("benchmark", (None, str(exc))))
        threading.Thread(target=work, daemon=True).start()

    @authorized('scraper')
    def clear_browser(self):
        if self.processing: return
        if QMessageBox.question(self, "Clear saved browser session", "Remove this combined app's saved browser login? You will need to sign in again.") != QMessageBox.StandardButton.Yes: return
        self._clear_requested = True; self._set_running(False)
        self.browser_progress.setRange(0, 0); self.browser_progress.show()
        if self.worker and self.worker.is_alive(): self.worker.send("shutdown")

    def shutdown(self, callback):
        self._closing = True; self._shutdown_callback = callback
        self._set_running(self.processing)
        if self.worker and self.worker.is_alive(): self.worker.send("shutdown")
        self.status.setText("Closing browser and preserving extraction progress…")
