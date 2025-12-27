import sys
import os
import ctypes  # <--- NEW: Required for Windows Taskbar Icon Fix
import traceback
from datetime import datetime
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QIcon  # <--- NEW: Required to load the icon

# Import Config first
import config

# --- Crash Handler ---
def global_exception_handler(exctype, value, tb):
    """Captures crashes and saves them to a log file instead of just closing"""
    if exctype == KeyboardInterrupt:
        sys.__excepthook__(exctype, value, tb)
        return
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = config.LOG_DIR / f"crash_{timestamp}.txt"
    
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    
    with open(log_path, "w") as f:
        f.write(f"CYNEDIRECTOR V20 CRASH REPORT\n{'='*30}\n")
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
    # This separates your app from the generic Python icon in the taskbar
    if sys.platform == 'win32':
        myappid = f'cynedirector.app.main.{config.VERSION}' # Arbitrary string
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # 2. Initialize App
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.VERSION)
    
    # --- SET APPLICATION ICON ---
    # We look for icon.svg in the assets folder
    icon_path = config.ASSETS_DIR / "icon.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    # 3. Apply Global Styles
    app.setStyleSheet(config.STYLESHEET)
    
    # 4. Launch Project Dialog (The "Home Page")
    try:
        from gui.project_dialog import ProjectDialog
    except ImportError:
        QMessageBox.critical(None, "Setup Error", "Could not find 'gui/project_dialog.py'.\nMake sure the 'gui' folder exists.")
        return

    welcome = ProjectDialog()
    
    # Ensure the dialog also gets the icon (sometimes dialogs miss the global setting)
    if icon_path.exists():
        welcome.setWindowIcon(QIcon(str(icon_path)))

    if welcome.exec(): 
        # 5. If user created/opened a project, Launch Main Window
        project_path = welcome.selected_project_path
        project_name = welcome.project_name
        
        print(f"Loading Project: {project_name} at {project_path}")
        
        # IMPORT MAIN WINDOW NOW (Lazy Loading)
        try:
            from gui.main_window import MainWindow
            window = MainWindow(project_path, project_name)
            
            # Ensure Main Window gets the icon
            if icon_path.exists():
                window.setWindowIcon(QIcon(str(icon_path)))
                
            window.show()
            sys.exit(app.exec())
            
        except ImportError as e:
            # Fallback
            msg = QMessageBox()
            msg.setWindowTitle("Work In Progress")
            msg.setText(f"Project '{project_name}' Selected!\n\n(The Main Window file is missing: {e})\n\nCheck 'gui/main_window.py'")
            msg.exec()
            sys.exit()
    else:
        sys.exit()

if __name__ == "__main__":
    main()