import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QScrollArea, QGridLayout, 
                             QFrame, QMessageBox, QInputDialog, QMenu, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QAction, QImage, QMouseEvent
from core.face_db import FaceDB

class FaceCard(QFrame):
    delete_requested = pyqtSignal(str) 
    rename_requested = pyqtSignal(str, str)
    selection_changed = pyqtSignal(str, bool) # NEW: Signal for multi-select

    def __init__(self, person_id, image, name="Unknown"):
        super().__init__()
        self.person_id = person_id
        self.current_name = name
        self.is_selected = False # NEW: Track state
        
        self.setFixedSize(130, 160)
        self.update_style() # NEW: centralized style
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 5)
        
        self.img_lbl = QLabel()
        if isinstance(image, QImage):
            pix = QPixmap.fromImage(image)
        else:
            pix = image
            
        pix = pix.scaled(90, 90, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        self.img_lbl.setPixmap(pix)
        self.img_lbl.setFixedSize(90, 90)
        self.img_lbl.setStyleSheet("border-radius: 45px; background: black; border: 2px solid #333;")
        layout.addWidget(self.img_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.name_lbl = QLabel(name)
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_lbl.setStyleSheet("color: white; font-weight: bold; font-size: 11px; margin-top: 5px; border: none; background: transparent;")
        layout.addWidget(self.name_lbl)

    def update_style(self):
        # Visual feedback for selection
        if self.is_selected:
            self.setStyleSheet("""
                FaceCard { background: #3A3445; border-radius: 8px; border: 2px solid #BEAEDB; }
            """)
        else:
            self.setStyleSheet("""
                FaceCard { background: #252526; border-radius: 8px; border: 1px solid #333; }
                FaceCard:hover { border: 1px solid #666; background: #2A2A2A; }
            """)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # Handle Multi-Select with CTRL
            modifiers = QApplication.keyboardModifiers()
            if modifiers == Qt.KeyboardModifier.ControlModifier:
                self.is_selected = not self.is_selected
                self.update_style()
                self.selection_changed.emit(self.person_id, self.is_selected)
            else:
                # If just clicking, rename (old behavior) or deselect others?
                # For now, let's keep rename on simple click for speed, 
                # but maybe double-click is better? Let's stick to simple click for rename for now.
                new_name, ok = QInputDialog.getText(self, "Rename", f"Rename {self.current_name} to:")
                if ok and new_name:
                    self.name_lbl.setText(new_name)
                    self.current_name = new_name
                    self.rename_requested.emit(self.person_id, new_name)

    def contextMenuEvent(self, event):
        # We handle the menu in the parent to support merging multiple cards
        event.ignore() 

class FacesTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        # Header with instructions
        header_layout = QVBoxLayout()
        lbl_title = QLabel("DETECTED PEOPLE")
        lbl_title.setStyleSheet("color: #DDD; font-weight: 900; font-size: 14px;")
        
        lbl_hint = QLabel("Hold CTRL + Click to select multiple faces to MERGE them.")
        lbl_hint.setStyleSheet("color: #777; font-size: 11px; margin-bottom: 10px;")
        
        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_hint)
        layout.addLayout(header_layout)
        
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
        self.selected_ids = set() # Track multiple selections
        self.project_path = None
        self.face_db = None

    def set_project_path(self, path):
        self.project_path = path
        self.face_db = FaceDB(path)
        self.load_existing_faces()

    def load_existing_faces(self):
        # Clear existing
        for pid in list(self.cards.keys()):
            self.cards[pid].deleteLater()
        self.cards = {}
        self.faces_count = 0
        self.selected_ids.clear()

        if not self.face_db: return
        
        # Sort by name for neatness
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
        # Global context menu for the grid
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
        
        # Ask for target name
        final_name, ok = QInputDialog.getText(self, "Merge Faces", 
            f"Merging {len(ids_to_merge)} entries.\nWhat is the real name?", text=primary_name)
        
        if not ok: return

        # Perform Merge in Backend
        # 1. Update Name of Primary
        self.face_db.rename_person(primary_id, final_name)
        
        # 2. For every other ID, we need to:
        #    a. Remove it from FaceDB
        #    b. Update known_encodings (actually, FaceDB needs a merge function, but for now we'll just delete the duplicates)
        #    NOTE: Real merging is complex (averaging embeddings). 
        #    For V2.0, we will just DELETE the duplicates and rename the Primary. 
        #    The "knowledge" of the deleted faces is lost, but the user gets a clean list.
        
        #    BETTER APPROACH: Re-map the IDs in the FaceDB.
        #    Since we don't have a deep merge function yet, we will just delete the others.
        
        for pid in ids_to_merge[1:]:
            self.delete_face(pid, confirm=False)
            
        # 3. Rename Primary in UI
        self.handle_rename(primary_id, final_name)
        
        # Reset Selection
        self.selected_ids.clear()
        self.load_existing_faces() # Refresh grid to remove gaps
        
        QMessageBox.information(self, "Merge Complete", f"Merged into '{final_name}'.\n(Note: You may need to re-scan to improve recognition for this person in future files.)")

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