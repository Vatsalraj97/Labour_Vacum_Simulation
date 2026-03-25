# =============================================================================
# app.py  --  Entry point for the Labour Vacuum Simulator desktop app
# =============================================================================
#
# Usage:
#   python app.py              -> launches at default scale 1000
#   python app.py --scale 500  -> uses workforce_scale=500
#
# =============================================================================

import sys
import argparse

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor

from main_window import MainWindow


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor('#0d1117'))
    p.setColor(QPalette.ColorRole.WindowText,      QColor('#e2e8f0'))
    p.setColor(QPalette.ColorRole.Base,            QColor('#161b22'))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor('#21262d'))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor('#1c2128'))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor('#e2e8f0'))
    p.setColor(QPalette.ColorRole.Text,            QColor('#e2e8f0'))
    p.setColor(QPalette.ColorRole.Button,          QColor('#21262d'))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor('#e2e8f0'))
    p.setColor(QPalette.ColorRole.BrightText,      QColor('#ffffff'))
    p.setColor(QPalette.ColorRole.Link,            QColor('#3d9cf5'))
    p.setColor(QPalette.ColorRole.Highlight,       QColor('#1f6feb'))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor('#ffffff'))
    return p


def main():
    parser = argparse.ArgumentParser(description='Labour Vacuum Simulator')
    parser.add_argument('--scale', type=int, default=1000,
                        help='Workforce scale divisor (default 1000)')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName('Labour Vacuum Simulator')
    app.setStyle('Fusion')
    app.setPalette(_dark_palette())
    app.setStyleSheet("""
        QToolTip {
            background: #1c2128; color: #e2e8f0;
            border: 1px solid #374151; padding: 4px;
            font-size: 9pt;
        }
        QScrollBar:vertical {
            background: #111827; width: 8px; border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: #374151; border-radius: 4px; min-height: 20px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QDockWidget::title {
            background: #1f2937; color: #9ca3af;
            padding: 4px 8px; font-size: 9pt;
        }
    """)

    window = MainWindow(default_scale=args.scale)
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
