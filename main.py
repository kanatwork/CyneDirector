# [FILE: main.py]
import sys
import os
import ctypes  # Required for Windows Taskbar Icon Fix
import traceback
from datetime import datetime
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt 

# Import Config first
import config

# --- Crash Handler ---
def global_exception_handler(exctype, value, tb):
    """Captures crashes and saves them to a log file instead of just closing"""
    if exctype == KeyboardInterrupt:
        sys.__excepthook__(exctype, value, tb)
        return
    
    # Ensure log directory exists
    os.makedirs(config.LOG_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = config.LOG_DIR / f"crash_{timestamp}.txt"
    
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    
    with open(log_path, "w") as f:
        f.write(f"CYNEDIRECTOR V{config.VERSION} CRASH REPORT\n{'='*30}\n")
        f.write(error_msg)
        
    print(f"CRITICAL ERROR: {value}")
    print(f"Report saved to: {log_path}")
    
    # Try to show a popup if QApplication is alive
    if QApplication.instance():
        QMessageBox.critical(None, "Critical Error", f"An error occurred.\nLog saved to: {log_path}\n\nError: {value}")

sys.excepthook = global_exception_handler

# --- Main Entry Point ---
def main():
    # 1. WINDOWS TASKBAR FIX (The Professional Touch)
    if sys.platform == 'win32':
        myappid = f'cynedirector.app.main.{config.VERSION}' 
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # 2. Initialize App
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.VERSION)
    
    # --- HIGH DPI SCALING FIX ---
    # Ensures the app looks crisp on 4K monitors
    if hasattr(Qt.HighDpiScaleFactorRoundingPolicy, 'PassThrough'):
        app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    # --- SET APPLICATION ICON ---
    icon_path = config.ASSETS_DIR / "icon.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    # 3. Apply Global Styles
    app.setStyleSheet(config.STYLESHEET)
    
    # 4. Launch Project Dialog (The "Home Page")
    try:
        from gui.project_dialog import ProjectDialog
    except ImportError as e:
        QMessageBox.critical(None, "Setup Error", f"Could not find 'gui/project_dialog.py'.\nError: {e}")
        return

    welcome = ProjectDialog()
    
    if icon_path.exists():
        welcome.setWindowIcon(QIcon(str(icon_path)))

    if welcome.exec(): 
        # 5. If user created/opened a project, Launch Main Window
        project_path = welcome.selected_project_path
        project_name = welcome.project_name
        
        print(f"Loading Project: {project_name} at {project_path}")
        
        # IMPORT MAIN WINDOW NOW (Lazy Loading)
        # This keeps the startup dialog instant, and loads PyTorch/CV2 only after project selection.
        try:
            from gui.main_window import MainWindow
            window = MainWindow(project_path, project_name)
            
            if icon_path.exists():
                window.setWindowIcon(QIcon(str(icon_path)))
                
            window.show()
            sys.exit(app.exec())
            
        except ImportError as e:
            msg = QMessageBox()
            msg.setWindowTitle("Startup Error")
            msg.setText(f"Failed to load Main Window.\n\nError: {e}")
            msg.exec()
            sys.exit()
    else:
        sys.exit()

if __name__ == "__main__":
    main()