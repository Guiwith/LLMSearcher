import sys
from PyQt6.QtWidgets import QApplication
from src.gui.main_window import MainWindow
import os
import logging

# 禁用所有QT日志
os.environ['QT_LOGGING_RULES'] = '*=false'

# 配置Python日志
logging.getLogger('qt.webengine').setLevel(logging.ERROR)
logging.getLogger('qt.network').setLevel(logging.ERROR)

def main():
    app = QApplication(sys.argv + [
        '--disable-gpu',
        '--disable-software-rasterizer',
        '--disable-dev-shm-usage',
        '--disable-webgl',
        '--no-sandbox',
        '--disable-notifications',
        '--disable-background-networking',
        '--disable-default-apps',
        '--no-experiments',
    ])
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 