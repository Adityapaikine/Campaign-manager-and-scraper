import os
import sys
from PySide6.QtWidgets import QApplication
from app.ui_qt.dialogs.team_dialogs import LoginDialog
from app.ui_qt.qt_theme import build_stylesheet
from app.ui_qt.team_window import TeamWindow

def main():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('Lead Workspace'); app.setOrganizationName('Apex Axis Solutions'); app.setStyle('Fusion')
    app.setStyleSheet(build_stylesheet('Professional Blue',False))
    login=LoginDialog(url=os.getenv('LEAD_TEAM_SERVER','http://127.0.0.1:8765'))
    if login.exec():
        window=TeamWindow(login.client); window.show(); raise SystemExit(app.exec())

if __name__=='__main__':main()
