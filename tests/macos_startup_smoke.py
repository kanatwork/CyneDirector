"""Exercise the real main() entry point on a disposable project.

Run with scripts/macos_env.sh sourced. QT_QPA_PLATFORM=offscreen is optional.
Only dialog choices and the timing of closing windows are automated. No original
projects, recent-project settings, or source footage are opened/modified.
"""
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import main
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from core.project_manager import ProjectManager
from core.settings_manager import SettingsManager
from gui.project_dialog import ProjectDialog
from gui.main_window import MainWindow
from gui.model_download_dialog import ModelDownloadDialog


def run():
    output = Path(os.environ.get("CYNE_TEST_OUTPUT", ".cache/mac-verification")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors, stages = [], []
    import sys
    def handler(kind, value, tb):
        errors.append(str(value))
        sys.__excepthook__(kind, value, tb)
        QApplication.instance().quit()
    with tempfile.TemporaryDirectory(prefix="cyne-startup-") as tmp:
        project = Path(tmp)
        (project / "startup.cyne").write_text(json.dumps({"files": []}))
        settings = SettingsManager(tmp)
        settings.set("auto_index_on_change", False)
        settings.save()
        dialog_init, window_init = ProjectDialog.__init__, MainWindow.__init__
        download_init = ModelDownloadDialog.__init__

        def open_dialog(self):
            dialog_init(self)
            def select_project():
                self.grab().save(str(output / "welcome.png"))
                stages.append("welcome rendered")
                self.selected_project_path, self.project_name = tmp, "startup"
                self.accept()
            QTimer.singleShot(500, select_project)

        def skip_downloads(self, *args, **kwargs):
            download_init(self, *args, **kwargs)
            def skip():
                self.grab().save(str(output / "models.png"))
                stages.append("model dialog rendered; downloads skipped")
                self.reject()
            QTimer.singleShot(500, skip)

        def show_window(self, *args, **kwargs):
            window_init(self, *args, **kwargs)
            def finish():
                available = self.screen().availableGeometry()
                if self.height() > available.height():
                    print("Size diagnostics:", {name: (widget.minimumSizeHint().width(), widget.minimumSizeHint().height())
                        for name, widget in [("window", self), ("media", self.media_page),
                            ("search", self.search_tab), ("preview", self.preview_panel),
                            ("metadata_scroll", self.metadata_scroll)]}, flush=True)
                assert self.height() <= available.height(), (self.size(), available)
                assert self.metadata_scroll.widget() is self.meta_panel
                self.metadata_scroll.verticalScrollBar().setValue(self.metadata_scroll.verticalScrollBar().maximum())
                self.grab().save(str(output / "main-window.png"))
                stages.append("main window rendered")
                self.is_dirty = False
                self.close()
                QApplication.instance().quit()
            QTimer.singleShot(1200, finish)
            QTimer.singleShot(20000, QApplication.instance().quit)

        with patch.object(ProjectManager, "_get_config_directory", return_value=str(project / "user-state")), \
             patch.object(ProjectDialog, "__init__", open_dialog), \
             patch.object(MainWindow, "__init__", show_window), \
             patch.object(ModelDownloadDialog, "__init__", skip_downloads), \
             patch.object(sys, "excepthook", handler):
            try:
                main.main()
            except SystemExit as exc:
                assert exc.code in (0, None), exc.code
        assert not errors, errors
        assert "welcome rendered" in stages and "main window rendered" in stages, stages
        report = {"stages": stages, "errors": errors, "platform": QApplication.platformName()}
        (output / "startup.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()
