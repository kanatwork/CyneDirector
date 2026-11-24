"""Workspace setup and recoverable jobs; uses the same ledger as the local CLI."""
import json
import hashlib
import os
import uuid
from pathlib import Path
from PyQt6.QtCore import QTimer,QThread,pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,QScrollArea)
from core.jobs import JobStore
from core.workspace import GIB, Workspace


class WorkspaceChangeWorker(QThread):
    result=pyqtSignal(object)
    error=pyqtSignal(str)
    def __init__(self,project,action,arguments,parent):
        super().__init__(parent);self.project,self.action,self.arguments=project,action,arguments
    def run(self):
        from core import workspace_changes
        try:
            if self.action=="plan": value=workspace_changes.plan(self.project,allowed=lambda:not self.isInterruptionRequested(),**self.arguments)
            else: value=workspace_changes.apply(self.project,self.arguments,allowed=lambda:not self.isInterruptionRequested())
            self.result.emit(value)
        except Exception as exc: self.error.emit(str(exc))


class WorkspaceJobsDialog(QDialog):
    def __init__(self, window, files):
        super().__init__(window)
        self.window, self.project, self.files = window, window.project_path, files
        self.pending_change=None;self.change_worker=None;self.closing_after_change=False
        self.setWindowTitle("Workspace & Jobs")
        self.resize(760, 730)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Original media is read-only. Choose separate existing folders for generated files."))
        form = QFormLayout()
        self.media = QPlainTextEdit(); self.media.setPlaceholderText("One original-media folder per line")
        self.media.setMaximumHeight(65)
        form.addRow("Media roots", self.media)
        self.output, self.models = QLineEdit(), QLineEdit(os.environ.get("HF_HOME", ""))
        self.location_buttons = []
        for label, field in (("Generated files",self.output),("Model cache",self.models)):
            row = QWidget(); row_layout=QHBoxLayout(row); row_layout.setContentsMargins(0,0,0,0)
            row_layout.addWidget(field)
            button=QPushButton("Choose…")
            self.location_buttons.append(button)
            button.clicked.connect(lambda checked=False, edit=field: self.choose(edit))
            row_layout.addWidget(button); form.addRow(label,row)
        self.reserve=QDoubleSpinBox(); self.reserve.setDecimals(4);self.reserve.setRange(0,2048); self.reserve.setValue(20); self.reserve.setSuffix(" GiB")
        form.addRow("Free-space reserve",self.reserve)
        self.relink_root=QComboBox();self.relink_target=QLineEdit()
        self.relink_root.setMaximumWidth(230)
        self.relink_target.setPlaceholderText("Existing folder at its new location")
        relink=QWidget();relink_layout=QHBoxLayout(relink);relink_layout.setContentsMargins(0,0,0,0)
        relink_layout.addWidget(self.relink_root);relink_layout.addWidget(self.relink_target)
        relink_choose=QPushButton("Choose…");relink_choose.clicked.connect(lambda:self.choose(self.relink_target));relink_layout.addWidget(relink_choose)
        form.addRow("Relink one root",relink)
        self.seal_root=QCheckBox("Record content hashes for this root while it is online")
        form.addRow("Recovery baseline",self.seal_root)
        settings=QWidget();settings_layout=QVBoxLayout(settings);settings_layout.addLayout(form)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(settings);scroll.setMaximumHeight(350)
        layout.addWidget(scroll)
        configure=QPushButton("Save workspace")
        self.configure_button = configure
        configure.clicked.connect(self.configure); settings_layout.addWidget(configure)
        self.apply_change=QPushButton("Apply reviewed workspace update");self.apply_change.setEnabled(False)
        self.apply_change.clicked.connect(self.apply_reviewed);settings_layout.addWidget(self.apply_change)
        config=Workspace.path(self.project)
        configuration_error = None
        if config.exists():
            try:
                data=json.loads(config.read_text())
                self.media.setPlainText("\n".join(r["path"] for r in data["media_roots"]))
                self.output.setText(data["destinations"]["output"]["path"])
                self.models.setText(data["destinations"]["models"]["path"])
                self.reserve.setValue(data["reserve_bytes"]/GIB)
                self.loaded_config_sha256=hashlib.sha256(config.read_bytes()).hexdigest()
                self.loaded_reserve_value=self.reserve.value()
                self.media.setReadOnly(True)
                configure.setText("Preview workspace update")
                for root in data["media_roots"]: self.relink_root.addItem(root["path"],root["id"])
            except Exception as exc:
                configuration_error = f"Workspace configuration could not be read: {exc}. Existing data was preserved."
                configure.setEnabled(False)
        layout.addWidget(QLabel(f"New job: {len(files)} checked sources. Capacity is checked before model loading."))
        stages=QHBoxLayout()
        self.stages={}
        for key,label in (("inventory","Metadata inventory"),("index_visuals","Visual search"),("transcribe_audio","Speech")):
            check=QCheckBox(label); check.setChecked(key=="inventory")
            self.stages[key]=check; stages.addWidget(check)
        layout.addLayout(stages)
        self.force_new=QCheckBox("Force a new analysis of an already completed scope")
        layout.addWidget(self.force_new)
        submit=QPushButton("Submit and run checked sources"); submit.setEnabled(bool(files)); submit.clicked.connect(self.submit)
        layout.addWidget(submit)
        self.jobs=QComboBox(); self.jobs.currentIndexChanged.connect(self.refresh_status); layout.addWidget(self.jobs)
        buttons=QHBoxLayout()
        for action,label in (("run","Run / resume"),("pause","Pause after stage"),("cancel","Cancel"),("retry_failed","Retry failed")):
            button=QPushButton(label); button.clicked.connect(lambda checked=False,a=action:self.control(a)); buttons.addWidget(button)
        layout.addLayout(buttons)
        self.status=QPlainTextEdit(); self.status.setReadOnly(True); layout.addWidget(self.status,1)
        if configuration_error: self.status.setPlainText(configuration_error)
        layout.addWidget(QLabel("Closing this dialog keeps work running. Quitting the app pauses after the current stage."))
        self.timer=QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(1500)
        self.refresh()

    def choose(self, field):
        path=QFileDialog.getExistingDirectory(self,"Choose existing folder",field.text())
        if path: field.setText(path)

    def configure(self):
        try:
            self.require_idle()
            if Workspace.path(self.project).exists():
                if hashlib.sha256(Workspace.path(self.project).read_bytes()).hexdigest()!=self.loaded_config_sha256:
                    raise RuntimeError("Workspace changed since this dialog opened; reopen it before preparing an update")
                current=Workspace.load(self.project,check=False)
                arguments={}
                if self.output.text()!=current.data["destinations"]["output"]["path"]: arguments["output"]=self.output.text()
                if self.models.text()!=current.data["destinations"]["models"]["path"]: arguments["model_cache"]=self.models.text()
                reserve=int(self.reserve.value()*GIB)
                if self.reserve.value()!=self.loaded_reserve_value: arguments["reserve_bytes"]=reserve
                if self.relink_target.text().strip(): arguments["relinks"]={self.relink_root.currentData():self.relink_target.text().strip()}
                if self.seal_root.isChecked(): arguments["seal_roots"]=[self.relink_root.currentData()]
                self.begin_change("plan",arguments)
                return
            Workspace.configure(self.project,self.media.toPlainText().splitlines(),self.output.text(),self.models.text(),int(self.reserve.value()*GIB))
            self.media.setReadOnly(True);self.configure_button.setText("Preview workspace update")
            self.loaded_config_sha256=hashlib.sha256(Workspace.path(self.project).read_bytes()).hexdigest()
            self.loaded_reserve_value=self.reserve.value()
            for root in Workspace.load(self.project).data["media_roots"]: self.relink_root.addItem(root["path"],root["id"])
            QMessageBox.information(self,"Workspace saved","New generated files will use this workspace. Existing project data remains in place.")
        except Exception as exc: QMessageBox.warning(self,"Workspace",str(exc))

    def require_idle(self):
        if self.change_worker is not None or self.window.worker is not None or self.window.background_indexer.is_indexing or self.window.workflow_manager.is_running:
            raise RuntimeError("Finish or pause active processing before changing workspace locations")

    def begin_change(self,action,arguments):
        self.configure_button.setEnabled(False);self.apply_change.setEnabled(False)
        self.status.setPlainText("Verifying workspace locations and source content. Originals remain read-only. Close to cancel verification.")
        self.change_worker=WorkspaceChangeWorker(self.project,action,arguments,self)
        self.change_worker.result.connect(self.change_ready)
        self.change_worker.error.connect(lambda message:self.status.setPlainText(message))
        self.change_worker.finished.connect(self.change_finished)
        self.change_worker.start()

    def change_ready(self,report):
        applied=report.get("state")=="applied"
        self.pending_change=None if applied else report["id"]
        self.status.setPlainText(("Workspace update applied. Existing data stayed in place.\n" if applied else "Review these changes, then apply this saved plan.\n")+
            json.dumps({"change_id":report["id"],"changes":report["changes"]},indent=2))
        if applied:
            current=Workspace.load(self.project,check=False)
            self.media.setPlainText("\n".join(r["path"] for r in current.data["media_roots"]))
            self.relink_target.clear();self.seal_root.setChecked(False)
            self.output.setText(current.data["destinations"]["output"]["path"])
            self.models.setText(current.data["destinations"]["models"]["path"])
            self.reserve.setValue(current.reserve/GIB)
            self.loaded_reserve_value=self.reserve.value();self.loaded_config_sha256=report["after_sha256"]
            self.relink_root.clear()
            for root in current.data["media_roots"]: self.relink_root.addItem(root["path"],root["id"])
            # Existing watchers still point to their prior directories. Rebuild
            # them only through the app's normal restart; do not process stale paths.
            watcher=getattr(self.window,"file_watcher",None)
            if watcher and watcher.isRunning(): watcher.stop();watcher.wait()
            self.status.appendPlainText("Automatic watching is stopped until the project is reopened. Preview and explicit jobs use the new locations now.")

    def change_finished(self):
        worker=self.change_worker;self.change_worker=None
        if worker: worker.deleteLater()
        self.configure_button.setEnabled(True);self.apply_change.setEnabled(bool(self.pending_change))
        if self.closing_after_change: self.accept()

    def apply_reviewed(self):
        try:
            self.require_idle()
            if self.pending_change: self.begin_change("apply",self.pending_change)
        except Exception as exc: QMessageBox.warning(self,"Workspace",str(exc))

    def closeEvent(self,event):
        if self.change_worker is not None:
            self.closing_after_change=True;self.change_worker.requestInterruption();event.ignore()
        else: super().closeEvent(event)

    def reject(self):
        # Escape uses reject() directly rather than closeEvent(). Keep ownership
        # until the background verifier has observed cancellation and retired.
        if self.change_worker is not None:
            self.closing_after_change=True;self.change_worker.requestInterruption()
        else: super().reject()

    def submit(self):
        try:
            if self.change_worker is not None: raise RuntimeError("Wait for workspace verification to finish")
            if self.window.worker is not None or self.window.background_indexer.is_indexing or self.window.workflow_manager.is_running:
                raise RuntimeError("Finish or pause the active workflow before submitting another job")
            selected=[key for key,check in self.stages.items() if check.isChecked()]
            import config
            settings=config._settings.to_dict()
            settings["mode"]="accuracy" if self.window.radio_accuracy.isChecked() else "speed"
            key="gui-force-"+uuid.uuid4().hex if self.force_new.isChecked() else None
            job_id=JobStore(self.project).submit(self.files,selected,settings,request_key=key)
            self.window.run_durable_job(job_id)
            self.refresh(job_id)
        except Exception as exc: QMessageBox.warning(self,"Job",str(exc))

    def control(self, action):
        job_id=self.jobs.currentData()
        if not job_id: return
        try:
            if self.change_worker is not None: raise RuntimeError("Wait for workspace verification to finish")
            store=JobStore(self.project)
            if action=="run":
                state=store.status(job_id)["state"]
                if state not in ("pending","running"): store.control(job_id,"resume")
                self.window.run_durable_job(job_id)
            else:
                store.control(job_id,action)
                if action=="retry_failed": self.window.run_durable_job(job_id)
            self.refresh_status()
        except Exception as exc: QMessageBox.warning(self,"Job",str(exc))

    def refresh(self, selected=None):
        if self.change_worker is not None or self.pending_change: return
        try:
            current=selected or self.jobs.currentData()
            self.jobs.blockSignals(True); self.jobs.clear()
            for row in JobStore(self.project).list_jobs():
                self.jobs.addItem(f"{row['id'][:12]} · {row['state']}",row["id"])
            index=self.jobs.findData(current)
            if index>=0: self.jobs.setCurrentIndex(index)
            self.jobs.blockSignals(False); self.refresh_status()
        except Exception as exc: self.status.setPlainText(str(exc))

    def refresh_status(self):
        job_id=self.jobs.currentData()
        if not job_id: return
        try:
            store=JobStore(self.project); value=store.status(job_id)
            self.status.setPlainText(json.dumps({k:value[k] for k in ("id","state","counts","total","current_file","current_stage","heartbeat","error")},indent=2)+
                "\n\n"+"\n".join(f"{e['kind']}: {e['detail']}" for e in store.events(job_id)[-8:]))
        except Exception as exc: self.status.setPlainText(str(exc))
