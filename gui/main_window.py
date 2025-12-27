import os
import json
import cv2 
import datetime
import sys
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QProgressBar, QSplitter, 
                             QFileDialog, QMessageBox, QFrame, QTextBrowser, 
                             QProgressDialog, QStackedWidget, QButtonGroup)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QPixmap, QImage, QIcon

from config import APP_NAME, VERSION, COLORS, FILE_EXT
from gui.media_tree import MediaTree
from gui.faces_tab import FacesTab
from gui.search_tab import SearchTab
from gui.player_window import PlayerWindow
from core.ai_models import AIBackend

class MainWindow(QMainWindow):
    def __init__(self, project_path, project_name):
        super().__init__()
        self.project_path = project_path
        self.project_name = project_name
        self.project_file = os.path.join(self.project_path, f"{self.project_name}{FILE_EXT}")
        self.is_dirty = False
        
        self.setWindowTitle(f"{APP_NAME} - {project_name}")
        self.resize(1600, 950)
        
        from core.database import Database
        self.db = Database()
        self.db.initialize(self.project_path)
        
        from core.face_db import FaceDB
        FaceDB(self.project_path)
        
        self.setup_ui()
        self.create_menu_bar()
        
        self.search_tab.set_project_path(self.project_path)
        self.faces_tab.set_project_path(self.project_path)
        
        self.load_project()
        self.worker = None
        self.player_window = None 
        self.import_worker = None

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 1. SIDEBAR ---
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(110) 
        
        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(10, 20, 10, 20)
        sb_layout.setSpacing(15)

        self.nav_group = QButtonGroup()
        self.nav_group.setExclusive(True)

        def create_nav_btn(text, id):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setFixedSize(90, 50)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none; color: {COLORS['text_dim']};
                    font-size: 10px; font-weight: bold; text-align: center;
                }}
                QPushButton:checked {{
                    color: {COLORS['accent']};
                    border-left: 2px solid {COLORS['accent']};
                }}
                QPushButton:hover {{ color: white; }}
            """)
            self.nav_group.addButton(btn, id)
            sb_layout.addWidget(btn)
            return btn

        self.btn_nav_media = create_nav_btn("MEDIA\nLIB", 0)
        self.btn_nav_faces = create_nav_btn("PEOPLE\nFACES", 1)
        self.btn_nav_search = create_nav_btn("SMART\nSEARCH", 2)
        
        self.nav_group.buttonClicked.connect(self.switch_tab)
        
        sb_layout.addStretch() 
        
        lbl_ver = QLabel(VERSION)
        lbl_ver.setStyleSheet("color: #444; font-size: 9px;")
        lbl_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_layout.addWidget(lbl_ver)

        main_layout.addWidget(self.sidebar)

        # --- 2. MAIN CONTENT AREA ---
        content_area = QWidget()
        ca_layout = QVBoxLayout(content_area)
        ca_layout.setContentsMargins(0,0,0,0)
        ca_layout.setSpacing(0)

        # A. Top Action Bar
        self.top_bar = QWidget()
        self.top_bar.setStyleSheet(f"background: {COLORS['bg_app']}; border-bottom: 1px solid {COLORS['border']};")
        self.top_bar.setFixedHeight(60)
        tb_layout = QHBoxLayout(self.top_bar)
        tb_layout.setContentsMargins(20, 0, 20, 0)
        
        self.lbl_title = QLabel(self.project_name.upper())
        self.lbl_title.setStyleSheet(f"color: {COLORS['text_main']}; font-weight: 900; font-size: 14px; letter-spacing: 1px;")
        tb_layout.addWidget(self.lbl_title)
        
        tb_layout.addStretch()
        
        # Action Buttons
        self.btn_index = self.create_action_btn("INDEX VISUALS", self.run_indexing)
        self.btn_transcribe = self.create_action_btn("TRANSCRIBE AUDIO", self.run_transcription)
        self.btn_faces = self.create_action_btn("SCAN FACES", self.run_face_scan)
        
        self.btn_cancel = QPushButton("CANCEL")
        self.btn_cancel.clicked.connect(self.cancel_worker)
        self.btn_cancel.hide()
        self.btn_cancel.setStyleSheet("background: #b71c1c; color: white; border: none; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        
        tb_layout.addWidget(self.btn_index)
        tb_layout.addWidget(self.btn_transcribe)
        tb_layout.addWidget(self.btn_faces)
        tb_layout.addWidget(self.btn_cancel)
        
        ca_layout.addWidget(self.top_bar)

        # B. Stacked Pages
        self.pages = QStackedWidget()
        
        self.media_page = QWidget()
        self.setup_media_page()
        self.pages.addWidget(self.media_page)
        
        self.faces_tab = FacesTab()
        self.pages.addWidget(self.faces_tab)
        
        self.search_tab = SearchTab()
        self.pages.addWidget(self.search_tab)
        
        ca_layout.addWidget(self.pages)
        
        # C. Status Bar
        self.status_bar = QWidget()
        self.status_bar.setFixedHeight(25)
        self.status_bar.setStyleSheet(f"background: {COLORS['accent']};") 
        stat_layout = QHBoxLayout(self.status_bar)
        stat_layout.setContentsMargins(10, 0, 10, 0)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: black; font-weight: bold; font-size: 11px;")
        stat_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setStyleSheet("QProgressBar { border: 1px solid #222; background: #333; border-radius: 2px; } QProgressBar::chunk { background: white; }")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        stat_layout.addWidget(self.progress_bar)
        
        ca_layout.addWidget(self.status_bar)

        main_layout.addWidget(content_area)
        
        self.btn_nav_media.setChecked(True)
        self.pages.setCurrentIndex(0)

    def switch_tab(self, btn):
        id = self.nav_group.id(btn)
        self.pages.setCurrentIndex(id)

    def create_action_btn(self, text, func):
        btn = QPushButton(text)
        btn.clicked.connect(func)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{ 
                background: transparent;
                border: 1px solid {COLORS['border']}; 
                color: {COLORS['text_dim']}; padding: 6px 12px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ 
                border-color: {COLORS['accent']};
                color: {COLORS['accent']}; 
            }}
            QPushButton:disabled {{ color: #444; border-color: #333; }}
        """)
        return btn

    def setup_media_page(self):
        layout = QVBoxLayout(self.media_page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        tbar = QHBoxLayout()
        
        btn_add = QPushButton(" + ADD FILE ")
        btn_add.setProperty("class", "accent")
        btn_add.clicked.connect(self.add_files)
        
        btn_folder = QPushButton(" + ADD FOLDER ")
        btn_folder.setStyleSheet(f"background: {COLORS['bg_input']}; color: white;")
        btn_folder.clicked.connect(self.add_folder)
        
        tbar.addWidget(btn_add)
        tbar.addWidget(btn_folder)
        
        btn_sel_all = QPushButton("All")
        btn_sel_all.setFixedWidth(50)
        btn_sel_all.clicked.connect(lambda: self.tree.toggle_all(True))
        
        btn_sel_none = QPushButton("None")
        btn_sel_none.setFixedWidth(50)
        btn_sel_none.clicked.connect(lambda: self.tree.toggle_all(False))
        
        tbar.addStretch()
        tbar.addWidget(btn_sel_all)
        tbar.addWidget(btn_sel_none)
        
        layout.addLayout(tbar)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {COLORS['border']}; }}")
        
        self.tree = MediaTree()
        self.tree.itemSelectionChanged.connect(self.update_preview_panel)
        self.tree.files_dropped_signal.connect(self.handle_dropped_files)
        self.tree.clear_data_signal.connect(self.handle_clear_data)
        
        splitter.addWidget(self.tree)
        
        self.preview_panel = QWidget()
        self.preview_panel.setStyleSheet(f"background: {COLORS['bg_panel']}; border-left: 1px solid {COLORS['border']};")
        pp_layout = QVBoxLayout(self.preview_panel)
        pp_layout.setContentsMargins(0,0,0,0)
        
        self.preview_lbl = QLabel()
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet("background: #000;")
        self.preview_lbl.setMinimumHeight(250)
        pp_layout.addWidget(self.preview_lbl)
        
        self.meta_box = QTextBrowser()
        self.meta_box.setFrameShape(QFrame.Shape.NoFrame)
        self.meta_box.setOpenLinks(False)
        self.meta_box.anchorClicked.connect(self.handle_transcript_click)
        self.meta_box.setStyleSheet(f"background: {COLORS['bg_panel']}; padding: 15px; color: {COLORS['text_dim']}; font-family: 'Segoe UI', sans-serif; font-size: 13px;")
        pp_layout.addWidget(self.meta_box)
        
        splitter.addWidget(self.preview_panel)
        splitter.setSizes([900, 400])
        
        layout.addWidget(splitter)

    def create_menu_bar(self):
        menubar = self.menuBar()
        menubar.setStyleSheet(f"QMenuBar {{ background: {COLORS['bg_panel']}; color: #DDD; }} QMenuBar::item:selected {{ background: #333; }}")
        
        file_menu = menubar.addMenu("File")
        
        act_new = QAction("New Project", self)
        act_new.triggered.connect(self.new_project_handler)
        file_menu.addAction(act_new)
        
        act_save = QAction("Save Project", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self.save_project)
        file_menu.addAction(act_save)
        
        act_save_as = QAction("Save Project As...", self)
        act_save_as.triggered.connect(self.save_project_as)
        file_menu.addAction(act_save_as)

    def update_preview_panel(self):
        paths = self.tree.get_selected_file_paths()
        if not paths: 
            self.preview_lbl.clear()
            self.meta_box.clear()
            self.current_preview_path = None
            return
            
        file_path = paths[0]
        self.current_preview_path = file_path 
        
        try:
            cap = cv2.VideoCapture(file_path)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total > 0:
                target_frame = 100 if total > 120 else total // 2
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                qt_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pix = QPixmap.fromImage(qt_img)
                scaled_pix = pix.scaled(self.preview_lbl.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.preview_lbl.setPixmap(scaled_pix)
            else:
                self.preview_lbl.setText("No Preview")
        except:
            self.preview_lbl.setText("Preview unavailable")

        json_path = f"{file_path}.json"
        html = f"<h3 style='color:{COLORS['accent']}'>{os.path.basename(file_path)}</h3>"
        
        if os.path.exists(json_path):
            try:
                # DATABASE READING IS SAFE NOW (Thread Locked)
                data = self.db.get_video_metadata(file_path)
                
                tags = data.get("tags", [])
                if tags:
                    html += f"<b>[ VISUALS ]</b><br><span style='color:#AAA'>{', '.join(tags)}</span><br><br>"
                
                transcript_data = data.get("transcript", "")
                if isinstance(transcript_data, list):
                    html += "<b>[ AUDIO TRANSCRIPT (Click to Play) ]</b><br>"
                    for seg in transcript_data:
                        start = seg['start']
                        text = seg['text']
                        html += f"<a href='{start}' style='color:{COLORS['accent']}; text-decoration:none;'><b>[{self.fmt_time(start)}]</b></a> {text} "
                elif isinstance(transcript_data, str) and transcript_data:
                    html += f"<b>[ TRANSCRIPT ]</b><br>{transcript_data}"
                    
                summary = data.get("summary", "")
                if summary:
                     html += f"<br><br><b>[ AI CONTEXT ]</b><br>{summary}"
            except Exception as e:
                html += f"<br><i style='color:red'>Error: {e}</i>"
        else:
            html += "<i>Not indexed yet.</i>"
            
        self.meta_box.setHtml(html)

    def fmt_time(self, seconds):
        m, s = divmod(seconds, 60)
        return f"{int(m):02}:{int(s):02}"

    def handle_transcript_click(self, url):
        try:
            timestamp = float(url.toString())
            if self.current_preview_path:
                if not self.player_window:
                    self.player_window = PlayerWindow()
                self.player_window.load_video(self.current_preview_path, timestamp)
        except Exception as e:
            print(f"Jump Error: {e}")

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Video Files", "", "Video (*.mp4 *.mov *.mxf *.braw *.avi)")
        if files:
            self.status_label.setText(f"Adding {len(files)} files...")
            self.tree.add_files_flat(files)
            self.search_tab.engine.build_index(self.tree.get_all_file_paths())
            self.mark_dirty() 
            self.status_label.setText(f"Added {len(files)} files.")

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Import")
        if not folder: return
        self.start_import_worker([folder], is_folder=True)
        
    def handle_dropped_files(self, local_urls):
        valid_files = []
        folders = []
        valid_exts = {'.mp4', '.mov', '.mxf', '.braw', '.avi'}
        
        for path in local_urls:
            if os.path.isdir(path):
                folders.append(path)
            elif os.path.splitext(path)[1].lower() in valid_exts:
                valid_files.append(path)
                
        if valid_files:
            self.tree.add_files_flat(valid_files)
            self.search_tab.engine.build_index(self.tree.get_all_file_paths()) # Update Search
            self.mark_dirty()
        
        if folders:
            self.start_import_worker(folders, is_folder=True)

    def start_import_worker(self, paths, is_folder=False):
        self.import_progress = QProgressDialog("Scanning for media...", "Cancel", 0, 0, self)
        self.import_progress.setWindowTitle("Importing Media")
        self.import_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.import_progress.setMinimumWidth(350)
        self.import_progress.show()

        try:
            from workers.importer import FolderImportWorker
            self.import_worker = FolderImportWorker(paths[0]) 
            self.import_worker.progress_signal.connect(self.update_import_label)
            self.import_worker.finished_signal.connect(self.on_import_finished)
            self.import_worker.start()
        except ImportError:
            QMessageBox.critical(self, "Error", "Could not load workers/importer.py")
            self.import_progress.close()

    def update_import_label(self, text):
        self.import_progress.setLabelText(text)

    def on_import_finished(self, files):
        self.import_progress.close()
        if files:
            self.status_label.setText(f"Importing {len(files)} files into tree...")
            self.tree.add_files_flat(files) 
            self.search_tab.engine.build_index(self.tree.get_all_file_paths()) # Update Search
            self.mark_dirty()
            self.status_label.setText(f"Added {len(files)} files.")
        else:
            QMessageBox.information(self, "Import", "No video files found.")

    def handle_clear_data(self, files, data_type):
        confirm = QMessageBox.question(self, "Confirm Clear", f"Are you sure you want to clear {data_type} data for {len(files)} files?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.No: return
        
        keys_map = {
            'visuals': ['tags', 'summary'],
            'audio': ['transcript', 'summary'],
            'faces': ['faces']
        }
        
        keys = keys_map.get(data_type, [])
        for fpath in files:
            self.db.clear_metadata_keys(fpath, keys)
            self.tree.reset_status(fpath, data_type)
            
        self.update_preview_panel()
        self.status_label.setText(f"Cleared {data_type} for {len(files)} files.")

    def mark_dirty(self):
        self.is_dirty = True
        self.setWindowTitle(f"{APP_NAME} - {self.project_name} *")

    def save_project(self):
        files = self.tree.get_all_file_paths()
        data = {"version": "2.0", "files": files}
        try:
            with open(self.project_file, 'w') as f: json.dump(data, f, indent=4)
            self.status_label.setText(f"Project saved ({len(files)} files).")
            self.is_dirty = False
            self.setWindowTitle(f"{APP_NAME} - {self.project_name}")
            return True
        except Exception as e: 
            QMessageBox.warning(self, "Save Error", str(e))
            return False
            
    def save_project_as(self):
        fpath, _ = QFileDialog.getSaveFileName(self, "Save Project As", self.project_path, f"Cyne Project (*{FILE_EXT})")
        if fpath:
            self.project_file = fpath
            self.project_name = os.path.basename(fpath).replace(FILE_EXT, "")
            self.save_project()

    def new_project_handler(self):
        QMessageBox.information(self, "New Project", "To create a new project, please restart the application.")

    def load_project(self):
        if os.path.exists(self.project_file):
            try:
                with open(self.project_file, 'r') as f:
                    data = json.load(f)
                    files = data.get("files", [])
                    if files: 
                        self.tree.add_files_flat(files)
                        self.search_tab.engine.build_index(files)
            except: pass

    def closeEvent(self, event):
        AIBackend().unload_models()
        if self.is_dirty:
            reply = QMessageBox.question(self, "Unsaved Changes", "Save before quitting?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save:
                if self.save_project(): event.accept()
                else: event.ignore()
            elif reply == QMessageBox.StandardButton.Discard: event.accept()
            else: event.ignore()
        else: event.accept()

    # --- WORKER HANDLERS ---
    def lock_buttons(self, locked):
        self.btn_index.setDisabled(locked)
        self.btn_transcribe.setDisabled(locked)
        self.btn_faces.setDisabled(locked)
        self.btn_cancel.setVisible(locked)

    def cancel_worker(self):
        if self.worker and self.worker.isRunning():
            self.status_label.setText("Stopping worker...")
            self.worker.stop()

    def worker_finished(self):
        self.lock_buttons(False)
        self.progress_bar.hide()
        self.status_label.setText("Task Complete.")
        self.mark_dirty()
        self.search_tab.engine.build_index(self.tree.get_all_file_paths())
        self.worker = None

    def update_log_status(self, msg):
        self.status_label.setText(msg)

    def update_progress(self, val):
        if self.progress_bar.isHidden(): self.progress_bar.show()
        self.progress_bar.setValue(val)
        
    def update_visuals_status(self, path, summary_text):
        self.tree.mark_visuals_done(path, summary_text)

    def update_audio_status(self, path):
        self.tree.mark_audio_done(path)

    def update_faces_status(self, path, count):
        self.tree.mark_faces_done(path)
        
    def add_new_face_to_ui(self, pid, name, img):
        self.faces_tab.add_face_card(pid, name, img)

    def get_files_to_process(self, check_key=None):
        selected = self.tree.get_selected_file_paths()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select specific files in the list to process.")
            return []
        
        if check_key:
            filtered = []
            for path in selected:
                meta = self.db.get_video_metadata(path)
                if check_key == 'tags' and meta.get('tags'): continue
                if check_key == 'transcript' and meta.get('transcript'): continue
                if check_key == 'faces' and meta.get('faces'): continue
                filtered.append(path)
            
            if len(filtered) < len(selected):
                print(f"Skipped {len(selected) - len(filtered)} already indexed files.")
            
            if not filtered:
                QMessageBox.information(self, "Already Done", f"All selected files have already been scanned for {check_key}.")
                return []
            return filtered
            
        return selected

    def run_indexing(self):
        if self.worker and self.worker.isRunning(): return
        # NEW: Check for existing tags
        files = self.get_files_to_process(check_key='tags')
        if not files: return
        
        self.lock_buttons(True)
        from workers.indexer import IndexerWorker
        self.worker = IndexerWorker(files, self.project_path)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.log_signal.connect(self.update_log_status)
        self.worker.finished_signal.connect(self.worker_finished)
        self.worker.summary_signal.connect(self.update_visuals_status)
        self.worker.start()

    def run_transcription(self):
        if self.worker and self.worker.isRunning(): return
        # NEW: Check for existing transcripts
        files = self.get_files_to_process(check_key='transcript')
        if not files: return
        
        self.lock_buttons(True)
        from workers.transcriber import TranscriberWorker
        self.worker = TranscriberWorker(files, self.project_path)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.log_signal.connect(self.update_log_status)
        self.worker.finished_signal.connect(self.worker_finished)
        self.worker.file_finished_signal.connect(self.update_audio_status)
        self.worker.start()

    def run_face_scan(self):
        if self.worker and self.worker.isRunning(): return
        # NEW: Check for existing faces
        files = self.get_files_to_process(check_key='faces')
        if not files: return
        
        self.lock_buttons(True)
        from workers.face_scanner import FaceScannerWorker
        self.worker = FaceScannerWorker(files, self.project_path)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.log_signal.connect(self.update_log_status)
        self.worker.finished_signal.connect(self.worker_finished)
        self.worker.face_count_signal.connect(self.update_faces_status)
        self.worker.new_face_signal.connect(self.add_new_face_to_ui)
        self.worker.start()