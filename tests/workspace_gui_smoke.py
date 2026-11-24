"""Native workspace/jobs dialog and real inventory QThread on disposable media."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import shutil
import threading
import time
from unittest.mock import patch

import main
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication
from core.jobs import JobStore
from core.settings_manager import SettingsManager
from core.workspace import Workspace
from gui.main_window import MainWindow
from gui.workspace_jobs_dialog import WorkspaceJobsDialog


def run():
    root=Path(__file__).resolve().parents[1]
    evidence=root/".cache/durable-verification"; evidence.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([])
    errors=[]
    import sys
    def handler(kind,value,tb):
        errors.append(str(value)); sys.__excepthook__(kind,value,tb)
    sys.excepthook=handler
    with tempfile.TemporaryDirectory(prefix="cyne-workspace-ui-") as tmp:
        base=Path(tmp); project=base/"project"; media=base/"media"; generated=base/"generated"
        for folder in (project,media,generated): folder.mkdir()
        (project/"sample.cyne").write_text('{"files":[],"custom_editor_state":{"keep":true}}')
        settings=SettingsManager(str(project)); settings.set("auto_index_on_change",False); settings.save()
        source=media/"C0001.mp4"
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","color=red:s=160x90:d=0.5","-c:v","libx264",str(source)],check=True,timeout=20)
        Workspace.configure(project,[media],generated,root/".cache/huggingface",64*1024**2)
        window=MainWindow(str(project),"sample"); window.show()
        dialog=WorkspaceJobsDialog(window,[str(source)]); dialog.show()
        loop=QEventLoop()
        QTimer.singleShot(100,dialog.submit)
        timeout=QTimer(); timeout.setSingleShot(True); timeout.timeout.connect(loop.quit); timeout.start(20000)
        poll=QTimer()
        def inspect():
            rows=JobStore(project).list_jobs()
            if rows and rows[0]["state"] in ("completed","failed","waiting_capacity","waiting_media") and window.worker is None:
                loop.quit()
        poll.timeout.connect(inspect); poll.start(100)
        loop.exec(); poll.stop(); timeout.stop()
        rows=JobStore(project).list_jobs(); assert len(rows)==1,rows
        status=JobStore(project).status(rows[0]["id"])
        assert status["state"]=="completed",status
        assert status["counts"]=={"completed":1}
        # Primary configured GUI queue: persist both scopes before starting.
        # Use a small publication adapter to isolate UI/Qt ownership from AI;
        # durable_runtime_smoke separately exercises the real model algorithms.
        second=media/"C0002.mp4"; shutil.copyfile(source,second)
        from core.workflow_manager import OperationType
        from core.processing import AppProcessor
        from core.source_state import source_signature
        def publish(processor,item,allowed,log):
            stage="visual" if item["stage"]=="index_visuals" else "transcript"
            with window.db.publication_context(processor.checkpoint(item),allowed):
                with window.db.reprocess(item["path"],stage,source_signature(item["path"])) as staged:
                    if stage=="visual": staged.save_tags(item["path"],["synthetic"],"GUI queue fixture")
                    else: staged.save_transcript(item["path"],[{"start":0,"end":.4,"text":"I do"}])
            return processor.reconcile(item)
        window.workflow_manager.add_operation(OperationType.INDEX_VISUALS,[str(source)],smart_filter=False)
        window.workflow_manager.add_operation(OperationType.TRANSCRIBE_AUDIO,[str(second)],smart_filter=False)
        with patch.object(window,"show_workspace_jobs"),patch.object(AppProcessor,"execute",publish):
            window.start_workflow()
            assert window.workflow_manager.queue==[]
            rows=JobStore(project).list_jobs(); assert len(rows)==2,rows
            queue_job=rows[0]["id"]
            pending=JobStore(project).status(queue_job)
            assert len(pending["items"])==2
            assert [(i["path"],i["stage"]) for i in pending["items"]]==[(str(source),"index_visuals"),(str(second),"transcribe_audio")]
            timeout.start(20000)
            def queue_done():
                if window.worker is None: loop.quit()
            poll.timeout.disconnect(inspect); poll.timeout.connect(queue_done); poll.start(100)
            loop.exec(); poll.stop(); timeout.stop()
        queued=JobStore(project).status(queue_job)
        assert queued["state"]=="completed",queued
        assert queued["counts"]=={"completed":2}
        dialog.refresh(queue_job)
        window.tree.add_files_flat([str(source),str(second)])
        assert window.save_project()
        project_before=(project/"sample.cyne").read_bytes()
        relocated=base/"SSD new mount";media.rename(relocated)
        new_output=base/"next output";new_output.mkdir()
        dialog.relink_target.setText(str(relocated));dialog.output.setText(str(new_output))
        def wait_change():
            timeout.start(20000)
            poll.timeout.disconnect();poll.timeout.connect(lambda:loop.quit() if dialog.change_worker is None else None)
            poll.start(50);loop.exec();poll.stop();timeout.stop()
            assert dialog.change_worker is None,dialog.status.toPlainText()
        dialog.configure();wait_change()
        assert dialog.pending_change,dialog.status.toPlainText()
        dialog.apply_reviewed();wait_change()
        assert dialog.pending_change is None,dialog.status.toPlainText()
        current=Workspace.load(project)
        assert current.data['revision']==1
        assert current.reserve==64*1024**2,'Relinking must not silently round/reduce the reserve'
        window.embedded_player.load_video(str(source))
        assert window.embedded_player.media_player.source().toLocalFile()==current.resolve_source(str(source))
        window.embedded_player.stop()
        from gui.media_tree import MediaLoaderWorker
        loader=MediaLoaderWorker(str(source),str(project));technical=[]
        loader.signals.finished.connect(lambda *args:technical.append(args))
        loader.run();assert technical[0][1]=='160x90',technical
        from core import workspace_changes
        external=workspace_changes.plan(project,reserve_bytes=65*1024**2)
        workspace_changes.apply(project,external['id'])
        warnings=[]
        with patch('gui.workspace_jobs_dialog.QMessageBox.warning',side_effect=lambda *args:warnings.append(args[-1])):
            dialog.configure()
        assert warnings and 'reopen' in warnings[0],warnings
        assert dialog.change_worker is None
        dialog.close();dialog=WorkspaceJobsDialog(window,[str(source)]);dialog.show()
        relocated.rename(base/'offline SSD')
        assert set(window.tree.get_all_file_paths())=={str(source),str(second)}
        assert window.save_project()
        assert (project/'sample.cyne').read_bytes()==project_before
        assert dialog.height()<=dialog.screen().availableGeometry().height()
        dialog.grab().save(str(evidence/"workspace-jobs.png"))
        # Real Qt cancellation/lifetime; only the long hashing work is a double.
        before_cancel=Workspace.path(project).read_bytes();started=threading.Event()
        def slow_plan(*args,allowed,**kwargs):
            started.set()
            while allowed(): time.sleep(.01)
            raise RuntimeError('verification cancelled')
        with patch('core.workspace_changes.plan',side_effect=slow_plan):
            dialog.begin_change('plan',{'reserve_bytes':66*1024**2})
            assert started.wait(2)
            dialog.reject();wait_change()
            assert Workspace.path(project).read_bytes()==before_cancel
            dialog.show();dialog.closing_after_change=False;started.clear()
            dialog.begin_change('plan',{'reserve_bytes':66*1024**2})
            assert started.wait(2)
            verifier=dialog.change_worker
            window.is_dirty=False;window.close()
            assert not verifier.isRunning(),'Parent shutdown must join configuration verification'
            assert Workspace.path(project).read_bytes()==before_cancel
            app.processEvents()
        assert not errors,errors
        report={"platform":QApplication.platformName(),"native_dialog":"rendered and fits display",
                "inventory_job":status["state"],"counts":status["counts"],"worker_retired":window.worker is None,
                "configured_gui_queue":queued["state"],"queue_counts":queued["counts"],
                "queue_test_uses_publication_adapter_double":True,"stage_scopes_preserved":True,
                "gui_background_preview_apply_relink":"passed","original_key_preview_and_technical_metadata":"passed",
                "offline_save_keeps_sources_and_custom_project_fields":True,
                "stale_gui_editor_rejected":True,"exact_reserve_preserved_during_relink":True,
                "escape_cancel_and_parent_shutdown_join_verifier":True,
                "qt_errors":errors}
        (evidence/"gui.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__": run()
