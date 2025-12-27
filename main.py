import sys
import os
import traceback
from datetime import datetime
from PyQt6.QtWidgets import QApplication, QMessageBox

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
    # 1. Initialize App
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.VERSION)
    
    # 2. Apply Global Styles
    app.setStyleSheet(config.STYLESHEET)
    
    # 3. Launch Project Dialog (The "Home Page")
    # We import GUI classes here to keep launch fast
    try:
        from gui.project_dialog import ProjectDialog
    except ImportError:
        QMessageBox.critical(None, "Setup Error", "Could not find 'gui/project_dialog.py'.\nMake sure the 'gui' folder exists.")
        return

    welcome = ProjectDialog()
    if welcome.exec(): 
        # 4. If user created/opened a project, Launch Main Window
        project_path = welcome.selected_project_path
        project_name = welcome.project_name
        
        print(f"Loading Project: {project_name} at {project_path}")
        
        # IMPORT MAIN WINDOW NOW (Lazy Loading)
        # We assume gui/main_window.py exists. If not, we create a placeholder.
        try:
            from gui.main_window import MainWindow
            window = MainWindow(project_path, project_name)
            window.show()
            sys.exit(app.exec())
            
        except ImportError as e:
            # Fallback if main_window.py isn't created yet (for debugging)
            msg = QMessageBox()
            msg.setWindowTitle("Work In Progress")
            msg.setText(f"Project '{project_name}' Selected!\n\n(The Main Window file is missing: {e})\n\nCheck 'gui/main_window.py'")
            msg.exec()
            sys.exit()
    else:
        # User closed the dialog without selecting a project
        sys.exit()

if __name__ == "__main__":
    main()