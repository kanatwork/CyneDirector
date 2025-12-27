import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QScrollArea, QGridLayout, 
                             QFrame, QMessageBox, QInputDialog, QMenu)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QAction, QImage
from core.face_db import FaceDB

class FaceCard(QFrame):
    delete_requested = pyqtSignal(str) 
    rename_requested = pyqtSignal(str, str)

    def __init__(self, person_id, image, name="Unknown"):
        super().__init__()
        self.person_id = person_id
        self.current_name = name
        
        self.setFixedSize(130, 160)
        self.setStyleSheet("""
            FaceCard { background: #252526; border-radius: 8px; border: 1px solid #333; }
            FaceCard:hover { border: 1px solid #666; background: #2A2A2A; }
        """)
        
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
        self.name_lbl.setStyleSheet("color: white; font-weight: bold; font-size: 11px; margin-top: 5px; border: none;")
        layout.addWidget(self.name_lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            new_name, ok = QInputDialog.getText(self, "Rename", f"Rename {self.current_name} to:")
            if ok and new_name:
                self.name_lbl.setText(new_name)
                self.current_name = new_name
                self.rename_requested.emit(self.person_id, new_name)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #333; color: white; border: 1px solid #555; } QMenu::item:selected { background: #555; }")
        
        delete_action = QAction("Delete Person", self)
        delete_action.triggered.connect(self.request_delete)
        menu.addAction(delete_action)
        menu.exec(event.globalPos())

    def request_delete(self):
        confirm = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to delete '{self.current_name}'?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.person_id)

class FacesTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        header = QLabel("DETECTED PEOPLE")
        header.setStyleSheet("color: #888; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)
        
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

        if not self.face_db: return
        
        for pid in self.face_db.known_ids:
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
        
        self.grid_layout.addWidget(card, row, col)
        self.cards[person_id] = card
        self.faces_count += 1

    def handle_rename(self, person_id, new_name):
        if self.face_db:
            self.face_db.rename_person(person_id, new_name)

    def delete_face(self, person_id):
        if person_id in self.cards:
            # 1. Remove UI
            widget = self.cards[person_id]
            self.grid_layout.removeWidget(widget)
            widget.deleteLater()
            del self.cards[person_id]
            
            # 2. Remove from DB and Disk
            if self.face_db:
                self.face_db.remove_person(person_id)
                
                thumb_path = os.path.join(self.face_db.db_dir, f"{person_id}.jpg")
                if os.path.exists(thumb_path):
                    try:
                        os.remove(thumb_path)
                    except: pass
            
            # Refresh to fix grid holes (optional, but cleaner)
            self.load_existing_faces()