# [FILE: gui/animations.py]
# Reusable animation helpers wrapping QPropertyAnimation.
# Each function returns the animation object — caller must keep a reference to prevent GC.

from PyQt6.QtCore import (QPropertyAnimation, QEasingCurve, QParallelAnimationGroup,
                           QSequentialAnimationGroup, QPoint, QAbstractAnimation)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QGraphicsDropShadowEffect

# ── Reduce-motion preference ────────────────────────────────────
_REDUCE_MOTION = False


def set_reduce_motion(enabled: bool):
    """Enable or disable reduced motion globally."""
    global _REDUCE_MOTION
    _REDUCE_MOTION = enabled


def _stop_existing(widget, attr_name):
    """Stop any existing animation stored on widget under attr_name."""
    prev = getattr(widget, attr_name, None)
    if prev is not None and isinstance(prev, QAbstractAnimation):
        prev.stop()


# ── Fade ─────────────────────────────────────────────────────────

def fade_in(widget, duration=200, start=0.0, end=1.0, callback=None):
    """Fade a widget in by animating its opacity effect."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    if _REDUCE_MOTION:
        effect.setOpacity(end)
        if callback:
            callback()
        return effect
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    if callback:
        anim.finished.connect(callback)
    anim.start()
    return anim


def fade_out(widget, duration=200, callback=None):
    """Fade a widget out by animating its opacity effect."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    if _REDUCE_MOTION:
        effect.setOpacity(0.0)
        if callback:
            callback()
        return effect
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InCubic)
    if callback:
        anim.finished.connect(callback)
    anim.start()
    return anim


# ── Slide ────────────────────────────────────────────────────────

def slide_width(widget, start_w, end_w, duration=250, easing=QEasingCurve.Type.OutCubic, callback=None):
    """Animate a widget's maximumWidth (and minimumWidth) between two values."""
    if _REDUCE_MOTION:
        widget.setMinimumWidth(end_w)
        widget.setMaximumWidth(end_w)
        if callback:
            callback()
        return None

    anim_max = QPropertyAnimation(widget, b"maximumWidth")
    anim_max.setDuration(duration)
    anim_max.setStartValue(start_w)
    anim_max.setEndValue(end_w)
    anim_max.setEasingCurve(easing)

    anim_min = QPropertyAnimation(widget, b"minimumWidth")
    anim_min.setDuration(duration)
    anim_min.setStartValue(start_w)
    anim_min.setEndValue(end_w)
    anim_min.setEasingCurve(easing)

    group = QParallelAnimationGroup(widget)
    group.addAnimation(anim_max)
    group.addAnimation(anim_min)
    if callback:
        group.finished.connect(callback)
    group.start()
    return group


def slide_height(widget, start_h, end_h, duration=250, easing=QEasingCurve.Type.OutCubic, callback=None):
    """Animate a widget's maximumHeight between two values."""
    if _REDUCE_MOTION:
        widget.setMaximumHeight(end_h)
        if callback:
            callback()
        return None

    anim = QPropertyAnimation(widget, b"maximumHeight")
    anim.setDuration(duration)
    anim.setStartValue(start_h)
    anim.setEndValue(end_h)
    anim.setEasingCurve(easing)
    if callback:
        anim.finished.connect(callback)
    anim.start()
    return anim


# ── Drift-in (fade + upward slide) ──────────────────────────────

def drift_in(widget, duration=250, distance=8):
    """Fade-in with upward drift — combines opacity + pos animation."""
    if _REDUCE_MOTION:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        effect.setOpacity(1.0)
        return effect

    # Opacity
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    fade_anim = QPropertyAnimation(effect, b"opacity")
    fade_anim.setDuration(duration)
    fade_anim.setStartValue(0.0)
    fade_anim.setEndValue(1.0)
    fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # Position
    start_pos = widget.pos() + QPoint(0, distance)
    end_pos = widget.pos()
    pos_anim = QPropertyAnimation(widget, b"pos")
    pos_anim.setDuration(duration)
    pos_anim.setStartValue(start_pos)
    pos_anim.setEndValue(end_pos)
    pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    group = QParallelAnimationGroup(widget)
    group.addAnimation(fade_anim)
    group.addAnimation(pos_anim)
    group.start()
    return group


# ── Pulse glow (infinite pulsing drop shadow) ───────────────────

def pulse_glow(effect, duration=2000):
    """Animate a QGraphicsDropShadowEffect's blurRadius in a loop (5→15→5).
    Returns the animation. Call .stop() to end the pulse."""
    if _REDUCE_MOTION:
        effect.setBlurRadius(10)
        return None

    anim = QPropertyAnimation(effect, b"blurRadius")
    anim.setDuration(duration)
    anim.setStartValue(5.0)
    anim.setKeyValueAt(0.5, 15.0)
    anim.setEndValue(5.0)
    anim.setEasingCurve(QEasingCurve.Type.InOutSine)
    anim.setLoopCount(-1)  # infinite
    anim.start()
    return anim


# ── Scale bounce (brief size bump) ──────────────────────────────

def scale_bounce(widget, duration=300):
    """Animate widget geometry: normal → 110% → normal for a bounce effect."""
    if _REDUCE_MOTION:
        return None

    geo = widget.geometry()
    cx, cy = geo.center().x(), geo.center().y()
    w, h = geo.width(), geo.height()

    # Expanded geometry (110%)
    ew = int(w * 1.1)
    eh = int(h * 1.1)
    from PyQt6.QtCore import QRect
    expanded = QRect(cx - ew // 2, cy - eh // 2, ew, eh)

    # Up phase
    anim_up = QPropertyAnimation(widget, b"geometry")
    anim_up.setDuration(duration // 2)
    anim_up.setStartValue(geo)
    anim_up.setEndValue(expanded)
    anim_up.setEasingCurve(QEasingCurve.Type.OutCubic)

    # Down phase
    anim_down = QPropertyAnimation(widget, b"geometry")
    anim_down.setDuration(duration // 2)
    anim_down.setStartValue(expanded)
    anim_down.setEndValue(geo)
    anim_down.setEasingCurve(QEasingCurve.Type.InCubic)

    group = QSequentialAnimationGroup(widget)
    group.addAnimation(anim_up)
    group.addAnimation(anim_down)
    group.start()
    return group


# ── Group helpers ────────────────────────────────────────────────

def parallel(*animations):
    """Run multiple animations in parallel."""
    group = QParallelAnimationGroup()
    for a in animations:
        if a is not None:
            group.addAnimation(a)
    group.start()
    return group


def sequential(*animations):
    """Run multiple animations sequentially."""
    group = QSequentialAnimationGroup()
    for a in animations:
        if a is not None:
            group.addAnimation(a)
    group.start()
    return group
