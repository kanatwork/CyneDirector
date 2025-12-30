# [FILE: gui/toast_notification.py]
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, pyqtProperty, QPoint
from PyQt6.QtGui import QColor
from config import COLORS

class ToastNotification(QWidget):
    """A single toast notification widget."""
    
    def __init__(self, message, toast_type="info", parent=None):
        super().__init__(parent)
        self.toast_type = toast_type
        self.message = message
        self.setup_ui()
        self.setup_animations()
        
    def setup_ui(self):
        """Setup the toast UI."""
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                           Qt.WindowType.WindowStaysOnTopHint |
                           Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Type-specific styling
        type_config = {
            "success": {"color": COLORS['success'], "icon": "✓", "bg": "#1B5E20"},
            "error": {"color": COLORS['error'], "icon": "✗", "bg": "#B71C1C"},
            "warning": {"color": COLORS['warning'], "icon": "⚠", "bg": "#E65100"},
            "info": {"color": "#2196F3", "icon": "ℹ", "bg": "#0D47A1"}
        }
        config = type_config.get(self.toast_type, type_config["info"])
        
        # Main container
        container = QWidget()
        container.setStyleSheet(f"""
            QWidget {{
                background: {config['bg']};
                border-radius: 8px;
                border: 1px solid {COLORS['border']};
            }}
        """)
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(15, 12, 10, 12)
        layout.setSpacing(12)
        
        # Icon
        icon_label = QLabel(config['icon'])
        icon_label.setStyleSheet(f"""
            QLabel {{
                color: {config['color']};
                font-size: 18px;
                font-weight: bold;
                min-width: 24px;
            }}
        """)
        layout.addWidget(icon_label)
        
        # Message
        msg_label = QLabel(self.message)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_main']};
                font-size: 13px;
                font-weight: 500;
            }}
        """)
        layout.addWidget(msg_label, stretch=1)
        
        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.dismiss)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {COLORS['text_dim']};
                font-size: 16px;
                font-weight: bold;
                border-radius: 10px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.1);
                color: white;
            }}
        """)
        layout.addWidget(close_btn)
        
        # Set container as main widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)
        
        # Set fixed width
        self.setFixedWidth(320)
        self.adjustSize()
        
    def setup_animations(self):
        """Setup slide-in and fade animations."""
        # Start position (off-screen to the right)
        self._start_pos = QPoint(0, 0)
        self._end_pos = QPoint(0, 0)
        
        # Opacity animation
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(300)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Position animation (for slide)
        self.pos_anim = QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(300)
        self.pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
    def showEvent(self, event):
        """Animate in when shown."""
        super().showEvent(event)
        # Start off-screen to the right
        parent = self.parent()
        if parent:
            parent_geometry = parent.geometry()
            screen_width = parent_geometry.x() + parent_geometry.width()
            # Use current y position (will be set by ToastManager)
            current_y = self.y()
            self.move(screen_width, current_y)
            self._end_pos = QPoint(self.x(), current_y)
            self._start_pos = QPoint(screen_width, current_y)
        
        # Animate in
        self.setWindowOpacity(0.0)
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        
        if parent:
            self.pos_anim.setStartValue(self._start_pos)
            self.pos_anim.setEndValue(self._end_pos)
            self.pos_anim.start()
        
        self.opacity_anim.start()
        
    def dismiss(self):
        """Animate out and close."""
        # Animate out
        self.opacity_anim.setStartValue(1.0)
        self.opacity_anim.setEndValue(0.0)
        self.opacity_anim.finished.connect(self.close)
        self.opacity_anim.start()
        
        # Slide out
        if self.parent():
            parent_geometry = self.parent().geometry()
            screen_width = parent_geometry.x() + parent_geometry.width()
            self.pos_anim.setStartValue(self.pos())
            self.pos_anim.setEndValue(QPoint(screen_width, self.y()))
            self.pos_anim.start()


class ToastManager:
    """Manages multiple toast notifications with stacking."""
    
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.toasts = []
        self.toast_spacing = 10
        self.auto_dismiss_timer = None
        
    def show_toast(self, message, toast_type="info", duration=4000):
        """
        Show a toast notification.
        
        Args:
            message: Message text to display
            toast_type: "success", "error", "warning", or "info"
            duration: Auto-dismiss duration in milliseconds (0 = no auto-dismiss)
        """
        toast = ToastNotification(message, toast_type, self.parent)
        self.toasts.append(toast)
        
        # Position toast
        self._update_positions()
        
        # Show toast
        toast.show()
        
        # Auto-dismiss timer
        if duration > 0:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._dismiss_toast(toast))
            timer.start(duration)
            toast._dismiss_timer = timer
        
    def _dismiss_toast(self, toast):
        """Remove and dismiss a toast."""
        if toast in self.toasts:
            self.toasts.remove(toast)
            toast.dismiss()
            # Update positions of remaining toasts
            QTimer.singleShot(300, self._update_positions)  # Wait for animation to finish
            
    def _update_positions(self):
        """Update positions of all toasts to stack them vertically from bottom-right."""
        if not self.parent:
            return
            
        # Ensure parent window is visible and has valid geometry
        if not self.parent.isVisible():
            return
            
        # Get parent window's geometry (position and size on screen)
        parent_geometry = self.parent.geometry()
        if parent_geometry.width() == 0 or parent_geometry.height() == 0:
            return
            
        parent_x = parent_geometry.x()
        parent_y = parent_geometry.y()
        parent_width = parent_geometry.width()
        parent_height = parent_geometry.height()
        
        # Position from bottom-right of parent window
        toast_width = 320
        right_margin = 20
        bottom_margin = 20
        start_x = parent_x + parent_width - toast_width - right_margin
        
        # Get visible toasts and calculate their total height
        visible_toasts = [toast for toast in self.toasts if toast.isVisible()]
        if not visible_toasts:
            return
        
        # Ensure all toasts have been sized
        for toast in visible_toasts:
            if toast.height() == 0:
                toast.adjustSize()
        
        # Calculate total height (sum of all toast heights + spacing between them)
        total_height = sum(toast.height() for toast in visible_toasts)
        total_height += self.toast_spacing * (len(visible_toasts) - 1)  # Spacing between toasts
        
        # Start from bottom - newest toast at bottom, older toasts stack above
        start_y = parent_y + parent_height - total_height - bottom_margin
        
        # Ensure toasts don't go above the window top
        if start_y < parent_y:
            start_y = parent_y + bottom_margin
        
        current_y = start_y
        for toast in visible_toasts:
            # Ensure toast stays within window bounds
            toast_x = max(parent_x, min(start_x, parent_x + parent_width - toast_width))
            toast_y = max(parent_y, min(current_y, parent_y + parent_height - toast.height()))
            toast.move(toast_x, toast_y)
            current_y += toast.height() + self.toast_spacing
                
    def clear_all(self):
        """Dismiss all toasts."""
        for toast in list(self.toasts):
            self._dismiss_toast(toast)

