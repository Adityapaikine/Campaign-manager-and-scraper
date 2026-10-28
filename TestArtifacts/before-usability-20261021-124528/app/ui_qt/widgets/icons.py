"""Small vector icons that do not depend on installed symbol fonts."""
from functools import lru_cache
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "scraper": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5M8 10.5h5m-2.5-2.5v5"/>',
    "home": '<path d="m3 10 9-7 9 7v10H3zM9 20v-7h6v7"/>',
    "leads": '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18M9 9v11M3 14h18"/>',
    "campaigns": '<path d="M3 7V5a2 2 0 0 1 2-2h5l3 4h6a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "validation": '<path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6zM8 12l3 3 5-6"/>',
    "ai": '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>',
    "dashboard": '<path d="M4 20V10h4v10m4 0V4h4v16m4 0v-7h1v7M3 21h19"/>',
    "tools": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "settings": '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="{bg}"/><circle cx="15" cy="17" r="3" fill="{bg}"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v.1"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "arrow": '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    "play": '<path d="m8 4 12 8-12 8z"/>',
    "pause": '<path d="M8 5v14M16 5v14"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "folder": '<path d="M3 7V5h7l3 3h8v12H3z"/>',
    "upload": '<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',
    "download": '<path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    "plus": '<path d="M12 4v16M4 12h16"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m3 7 9 6 9-6"/>',
    "browser": '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="M3 9h18M7 6h.1M10 6h.1"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "copy": '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
    "document": '<path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h5"/>',
    "filter": '<path d="M3 5h18l-7 8v6l-4 2v-8z"/>',
}


@lru_cache(maxsize=160)
def icon(name, color="#71819B", active_color=None, size=20):
    result = QIcon()
    for mode, state, stroke in (
        (QIcon.Mode.Normal, QIcon.State.Off, color),
        (QIcon.Mode.Normal, QIcon.State.On, active_color or color),
        (QIcon.Mode.Disabled, QIcon.State.Off, "#91A0B4"),
    ):
        body = PATHS.get(name, PATHS["document"]).replace("{bg}", "none")
        source = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{stroke}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(source.encode())).render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        result.addPixmap(pixmap, mode, state)
    return result
