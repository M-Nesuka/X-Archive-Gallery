STYLE = '''
* { font-family: "Yu Gothic UI", "Segoe UI"; font-size: 14px; }
QMainWindow, QWidget#shell { background:#0b0b0e; color:#eeebf4; }
QDialog { background:#151419; color:#eeebf4; }
QListWidget { background:#151419; color:#eeebf4; border:0; outline:0; }
QListWidget::item { padding:7px 9px; border-radius:4px; }
QListWidget::item:selected { background:#3c3645; color:#ffffff; }
QWidget { color:#eeebf4; }
QFrame#top, QFrame#footer { background:#101013; }
QFrame#toolbar { background:#0b0b0e; }
QFrame#details, QWidget#details { background:#151419; border:0; }
QWidget#discoverySurface { background:#151419; color:#eeebf4; border:0; }
QLabel { background:transparent; }
QLabel#brand { font-size:19px; font-weight:600; letter-spacing:2px; }
QLabel#monogram { color:#c1abed; font-family:Georgia; font-size:29px; }
QLabel#tagline { color:#96909f; font-size:10px; letter-spacing:1px; }
QLabel#muted { color:#b9b2c3; font-size:13px; }
QLabel#field { color:#b9b2c3; font-size:13px; }
QPushButton, QToolButton { background:transparent; border:0; padding:8px 11px; border-radius:5px; color:#bcb5c7; }
QPushButton:hover, QToolButton:hover { background:#242129; color:#fff; }
QPushButton:pressed, QToolButton:pressed { background:#342c40; }
QPushButton:checked, QToolButton:checked { background:#2b2437; color:#e5d4ff; }
QPushButton:disabled, QToolButton:disabled { color:#5c5664; }
QPushButton#tab { border-radius:0; padding:12px 6px; margin-right:16px; }
QPushButton#tab:checked { background:transparent; border-bottom:2px solid #c1abed; }
QPushButton#primary { background:#2b2437; color:#e5d4ff; }
QPushButton#primary:hover { background:#3a304a; }
QLineEdit { background:#201e25; border:1px solid transparent; border-radius:7px; padding:10px 13px; color:#eeeaf5; selection-background-color:#514263; }
QLineEdit:focus { border:1px solid #86709f; }
QComboBox { background:#201e25; border:0; border-radius:4px; padding:8px 10px; min-width:83px; }
QComboBox::drop-down { border:0; width:20px; }
QComboBox QAbstractItemView { background:#25212c; color:#eeeaf5; selection-background-color:#4b3b5d; border:0; }
QMenu { background:#25212c; color:#eeeaf5; border:1px solid #39313f; padding:6px; }
QMenu::item { padding:9px 22px; border-radius:3px; }
QMenu::item:selected { background:#463552; }
QMenu::separator { height:1px; background:#3b3344; margin:5px 10px; }
QToolTip { background:#2a2433; color:#f5edff; border:1px solid #655575; padding:6px; }
QScrollArea { background:transparent; border:0; }
QScrollBar:vertical { background:#111014; width:10px; margin:0; }
QScrollBar::handle:vertical { background:#4b4455; border-radius:4px; min-height:35px; margin:2px; }
QScrollBar::handle:vertical:hover { background:#766586; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QSlider::groove:horizontal { height:3px; background:#332d3c; border-radius:1px; }
QSlider::handle:horizontal { background:#b8a3d4; width:12px; margin:-5px 0; border-radius:6px; }
QMessageBox { background:#1b1821; }
QSplitter::handle { background:#0b0b0e; width:1px; }
QCheckBox#duplicateFilter { spacing:9px; padding:8px 11px; border-radius:6px; background:#211c29; color:#eeeaf5; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:14px; height:14px; border:1px solid #82748f; border-radius:3px; background:#211c29; }
QCheckBox::indicator:checked { background:#70bca9; border:1px solid #b5e9dc; }
QCheckBox#duplicateFilter:hover { background:#2d2637; }
QCheckBox#duplicateFilter::indicator { width:0; height:0; border:0; }
QFrame#fullscreenControls { background:rgba(18,16,22,232); border:1px solid #4b4354; border-radius:10px; }
'''

STYLE += '''
QFrame#backupStrip { background:#131016; }
QLabel#latestPost { color:#dfcfef; font-size:13px; }
QPushButton#analyticsImport { background:#211c29; color:#e5d4ff; padding:7px 10px; }
QPushButton#analyticsImport:hover { background:#342c40; }
QProgressBar { background:#29232f; border:0; border-radius:2px; }
QProgressBar::chunk { background:#b59ccb; border-radius:2px; }
QTextBrowser { background:#100d15; border:0; color:#bfb5ca; padding:8px; }
QPushButton#manualTag { background:#203b3c; color:#cce7e2; padding:7px 9px; text-align:left; }
QPushButton#manualTag:hover { background:#315354; }
QPushButton#manualTag:checked { background:#44726c; color:#ffffff; }
QLabel#tagHeading { color:#b9b2c3; font-size:14px; font-weight:500; }
QLabel#performanceHeading { color:#93849f; font-size:11px; font-weight:400; }
QLabel#performanceTags { color:#b5a4c8; font-size:13px; font-weight:400; padding:0; }
QPushButton#detailTag { background:transparent; color:#a8bdb7; padding:5px 8px; text-align:left; }
QPushButton#detailTag:hover { background:#25272b; color:#d5e3df; }
QPushButton#detailTag:checked { background:#253330; color:#c8dfd7; }
QLabel#tagCloud { color:#b3b9bf; font-size:13px; font-weight:400; padding:0; }
QCheckBox#duplicateSubtle { color:#928a9c; background:transparent; padding:0; font-size:12px; }
QCheckBox#duplicateSubtle::indicator { width:13px; height:13px; border:1px solid #746b7f; border-radius:2px; background:transparent; }
QCheckBox#duplicateSubtle::indicator:checked { background:#2a2630; border:1px solid #928a9c; }
'''

STYLE += 'QPushButton#detailAction, QToolButton#detailAction { padding:7px 6px; font-size:13px; }'

STYLE += 'QPushButton#homeBrand { padding:0; border:0; background:transparent; } QPushButton#homeBrand:hover { background:transparent; } QPushButton#homeBrand:focus { border-bottom:1px solid #766586; }'

STYLE += 'QPushButton:focus, QToolButton:focus { border:1px solid #86709f; } QComboBox:focus { border:1px solid #86709f; }'
STYLE += 'QPushButton#primary:disabled { background:#211f25; color:#827b8d; }'

# Combo popups use the same readable text color when a row is selected.
STYLE += 'QComboBox QAbstractItemView { selection-color:#eeeaf5; }'
