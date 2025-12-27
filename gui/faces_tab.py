# [FILE: gui/faces_tab.py]
import os
import json
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QScrollArea, QGridLayout, 
                             QFrame, QMessageBox, QInputDialog, QMenu, QApplication, QProgressDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QPixmap, QAction, QImage, QMouseEvent, QCursor
from config import COLORS
from core.face_db import FaceDB

# --- WORKER: ASYNC FACE MERGE (Prevents Freeze) ---
class FaceMergeWorker(QThread):
    """
    Scans the entire project for JSON sidecar files and updates Face IDs.
    This is IO-intensive, so it MUST run in a background thread.
    """
    finished_signal = pyqtSignal(int) # Returns number of files updated

    def __init__(self, project_path, primary_id, ids_to_remove):
        super().__init__()
        self.project_path = project_path
        self.primary_id = primary_id
        self.ids_to_remove = set(ids_to_remove)

    def run(self):
        updated_count = 0
        
        # Walk through project to find all .json sidecar files
        for root, dirs, files in os.walk(self.project_path):
            # Optimization: Skip internal DB folders to save time
            if "_cyne_db" in root: continue
            
            for file in files:
                if file.endswith(".json"):
                    meta_path = os.path.join(root, file)
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # Check if this file contains any of the faces we are merging
                        if "faces" in data:
                            faces = data["faces"]
                            changed = False
                            new_faces = []
                            
                            for fid in faces:
                                if fid in self.ids_to_remove:
                                    # Replace old ID with the new Primary ID
                                    new_faces.append(self.primary_id)
                                    changed = True
                                else:
                                    new_faces.append(fid)
                            
                            if changed:
                                # Remove duplicates (in case Primary ID was already present)
                                data["faces"] = list(set(new_faces))
                                
                                # Atomic Write
                                with open(meta_path, 'w', encoding='utf-8') as f:
                                    json.dump(data, f, indent=4)
                                updated_count += 1
                    except:
                        pass
                        
        self.finished_signal.emit(updated_count)

# --- UI COMPONENT: FACE CARD ---
class FaceCard(QFrame):
    delete_requested = pyqtSignal(str) 
    rename_requested = pyqtSignal(str, str)
    selection_changed = pyqtSignal(str, bool) 

    def __init__(self, person_id, image, name="Unknown"):
        super().__init__()
        self.person_id = person_id
        self.current_name = name
        self.is_selected = False 
        
        self.setFixedSize(130, 160)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.update_style() 
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 5)
        
        self.img_lbl = QLabel()
        if isinstance(image, QImage):
            pix = QPixmap.fromImage(image)
        else:
            pix = image
            
        # Crisp Thumbnail Scaling
        pix = pix.scaled(90, 90, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        self.img_lbl.setPixmap(pix)
        self.img_lbl.setFixedSize(90, 90)
        self.img_lbl.setStyleSheet("border-radius: 45px; background: black; border: 2px solid #333;") # Circular look
        layout.addWidget(self.img_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.name_lbl = QLabel(name)
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_lbl.setStyleSheet("color: white; font-weight: bold; font-size: 11px; margin-top: 5px; border: none; background: transparent;")
        layout.addWidget(self.name_lbl)

    def update_style(self):
        if self.is_selected:
            self.setStyleSheet(f"""
                FaceCard {{ background: #3A3445; border-radius: 8px; border: 2px solid {COLORS['accent']}; }}
            """)
        else:
            self.setStyleSheet("""
                FaceCard { background: #252526; border-radius: 8px; border: 1px solid #333; }
                FaceCard:hover { border: 1px solid #666; background: #2A2A2A; }
            """)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            modifiers = QApplication.keyboardModifiers()
            if modifiers == Qt.KeyboardModifier.ControlModifier:
                self.is_selected = not self.is_selected
                self.update_style()
                self.selection_changed.emit(self.person_id, self.is_selected)
            else:
                new_name, ok = QInputDialog.getText(self, "Rename", f"Rename {self.current_name} to:")
                if ok and new_name:
                    self.name_lbl.setText(new_name)
                    self.current_name = new_name
                    self.rename_requested.emit(self.person_id, new_name)

# --- MAIN TAB ---
class FacesTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        # Header
        header_layout = QVBoxLayout()
        lbl_title = QLabel("DETECTED PEOPLE")
        lbl_title.setStyleSheet("color: #DDD; font-weight: 900; font-size: 14px;")
        
        lbl_hint = QLabel("Hold CTRL + Click to select multiple faces to MERGE them (e.g., duplicates).")
        lbl_hint.setStyleSheet("color: #777; font-size: 11px; margin-bottom: 10px;")
        
        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_hint)
        layout.addLayout(header_layout)
        
        # Grid Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: #121212; border: none;")
        
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid_layout.setSpacing(15)
        
        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll)
        
        self.faces_count = 0
        self.cards = {} 
        self.selected_ids = set() 
        self.project_path = None
        self.face_db = None
        self.merge_worker = None

    def set_project_path(self, path):
        self.project_path = path
        self.face_db = FaceDB(path)
        self.load_existing_faces()

    def load_existing_faces(self):
        # Clear existing items safely
        for pid in list(self.cards.keys()):
            self.cards[pid].deleteLater()
        self.cards = {}
        self.faces_count = 0
        self.selected_ids.clear()

        if not self.face_db: return
        
        # Sort by name
        sorted_ids = sorted(self.face_db.known_ids, key=lambda x: self.face_db.get_name(x))

        for pid in sorted_ids:
            if pid in self.cards: continue
            
            name = self.face_db.get_name(pid)
            thumb_path = os.path.join(self.face_db.db_dir, f"{pid}.jpg")
            
            if os.path.exists(thumb_path):
                image = QImage(thumb_path)
                if not image.isNull():
                    self.add_face_card(pid, name, image)

    def add_face_card(self, person_id, name, q_image):
        if person_id in self.cards: return

        row = self.faces_count // 5
        col = self.faces_count % 5
        
        card = FaceCard(person_id, q_image, name)
        card.delete_requested.connect(self.delete_face)
        card.rename_requested.connect(self.handle_rename)
        card.selection_changed.connect(self.handle_selection)
        
        self.grid_layout.addWidget(card, row, col)
        self.cards[person_id] = card
        self.faces_count += 1

    def handle_selection(self, pid, is_selected):
        if is_selected:
            self.selected_ids.add(pid)
        else:
            self.selected_ids.discard(pid)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #333; color: white; border: 1px solid #555; } QMenu::item:selected { background: #555; }")
        
        if len(self.selected_ids) > 1:
            merge_action = QAction(f"Merge {len(self.selected_ids)} Selected People", self)
            merge_action.triggered.connect(self.merge_selected_faces)
            menu.addAction(merge_action)
        
        refresh_action = QAction("Refresh Grid", self)
        refresh_action.triggered.connect(self.load_existing_faces)
        menu.addAction(refresh_action)
        
        menu.exec(event.globalPos())

    def merge_selected_faces(self):
        if len(self.selected_ids) < 2: return
        
        ids_to_merge = list(self.selected_ids)
        primary_id = ids_to_merge[0] # The one we keep
        primary_name = self.face_db.get_name(primary_id)
        
        final_name, ok = QInputDialog.getText(self, "Merge Faces", 
            f"Merging {len(ids_to_merge)} entries.\nWhat is the real name?", text=primary_name)
        
        if not ok: return

        # 1. Update Name of Primary locally
        self.face_db.rename_person(primary_id, final_name)
        
        # 2. START BACKGROUND WORKER (The fix)
        self.progress_dialog = QProgressDialog(f"Merging {len(ids_to_merge)} faces into '{final_name}'...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.show()
        
        self.merge_worker = FaceMergeWorker(self.project_path, primary_id, ids_to_merge[1:])
        self.merge_worker.finished_signal.connect(lambda count: self.on_merge_complete(count, primary_id, final_name, ids_to_merge))
        self.merge_worker.start()

    def on_merge_complete(self, count, primary_id, final_name, ids_to_merge):
        self.progress_dialog.close()
        
        # 3. Remove Old IDs from FaceDB & Disk
        for pid in ids_to_merge[1:]:
            self.delete_face(pid, confirm=False)
            
        # 4. Refresh UI
        self.handle_rename(primary_id, final_name)
        self.selected_ids.clear()
        self.load_existing_faces() # Refresh grid to remove gaps
        
        QMessageBox.information(self, "Merge Complete", f"Merged into '{final_name}'.\nUpdated metadata for {count} video files.")

    def handle_rename(self, person_id, new_name):
        if self.face_db:
            self.face_db.rename_person(person_id, new_name)

    def delete_face(self, person_id, confirm=True):
        if confirm:
            name = self.cards[person_id].current_name
            conf = QMessageBox.question(self, "Confirm Delete", f"Delete '{name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if conf == QMessageBox.StandardButton.No: return

        if person_id in self.cards:
            # Remove UI
            widget = self.cards[person_id]
            self.grid_layout.removeWidget(widget)
            widget.deleteLater()
            del self.cards[person_id]
            
            # Remove DB
            if self.face_db:
                self.face_db.remove_person(person_id)
                thumb_path = os.path.join(self.face_db.db_dir, f"{person_id}.jpg")
                if os.path.exists(thumb_path):
                    try: os.remove(thumb_path)
                    except: pass
        
        if person_id in self.selected_ids:
            self.selected_ids.discard(person_id)