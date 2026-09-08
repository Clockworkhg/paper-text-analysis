# -*- coding: utf-8 -*-
"""Analysis run controller: owns the lifecycle of one GUI analysis/sanity run.

Runs the frozen shared/ workflow in a subprocess against an isolated work
copy (``runs/work_<run_id>/``), streams JSON-line events, enforces the
sanity gate and single-writer rule, publishes outputs only on success, and
journals every run for the Runs page and crash recovery.

The controller is a QObject living on the GUI thread; QProcess is
event-loop driven, so the UI never blocks.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from gui_next.execution import jobs
from gui_next.execution.events import ACTIVE_STATES, RunState, parse

REPO_ROOT = Path(__file__).resolve().parents[2]


class AnalysisController(QObject):
    state_changed = Signal(str, str)      # RunState value, human message
    log_line = Signal(str)
    finished = Signal(str)                # terminal RunState value
    review_lock_changed = Signal(bool)    # True while a run is active

    def __init__(self, project_dir: str | Path, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.root = Path(project_dir).resolve()
        self.state = RunState.IDLE
        self.run_id: Optional[str] = None
        self.kind = "analyze"
        self.work_dir: Optional[Path] = None
        self.params: dict = {}
        self.logs: list[str] = []
        self.last_error: Optional[dict] = None
        self.outputs: dict = {}
        self.error: Optional[str] = None
        self._corpus_fingerprint = ""
        self.publication_fault_injection: Optional[dict] = None

        self._process: Optional[QProcess] = None
        self._cancel_requested = False
        self._kill_timer = QTimer(self)
        self._kill_timer.setInterval(10_000)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._force_kill)

    # ------------------------------------------------------------------
    # gating (defence in depth — the page gates first)

    def analysis_writer_active(self) -> Optional[dict]:
        return jobs.active_writer(self.root)

    # ------------------------------------------------------------------
    # starting

    def start(self, spec: dict, run_id: str) -> bool:
        from gui_next.execution.publication import recovery_required

        if self.state in ACTIVE_STATES:
            return False
        if recovery_required(self.root):
            self.last_error = "存在 RECOVERY_REQUIRED 的发布事务,完整性解决前禁止新的分析发布。"
            return False
        if jobs.active_writer(self.root):
            return False
        if not jobs.acquire_writer_lock(self.root, run_id):
            return False

        self.run_id = run_id
        self.kind = spec.get("kind", "analyze")
        self.params = dict(spec)
        self.logs = []
        self.last_error = None
        self.outputs = {}
        self.error = None

        self._set_state(RunState.PREPARING, "准备运行 …")
        spec = dict(spec)
        if self.kind == "analyze":
            self._set_state(RunState.PREPARING,
                            "创建隔离工作目录 runs/work_{} …".format(run_id))
            try:
                self.work_dir = jobs.make_work_dir(self.root, run_id)
                spec["project_dir"] = str(self.work_dir)
                spec_path = self.work_dir / "job_spec.json"
                spec_path.write_text(
                    json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as exc:
                self._fail(f"工作目录创建失败: {exc}")
                return False
        else:
            # Sanity inspects the *real* corpus and writes the real report.
            self.work_dir = None
            spec_path = self.root / "runs" / f"{run_id}_spec.json"
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            spec_path.write_text(
                json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

        jobs.append_run(self.root, {
            "run_id": run_id,
            "kind": self.kind,
            "status": RunState.PREPARING.value,
            "pid": 0,
            "started_at": spec.get("created_at") or "",
            "params": {k: spec.get(k) for k in
                       ("targets", "group_by", "mi_threshold", "pos_translate", "sanity")},
            "work_dir": str(self.work_dir),
        })

        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(REPO_ROOT))
        env = self._process.processEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        self._process.setProcessEnvironment(env)
        self._process.readyReadStandardOutput.connect(self._drain_stdout)
        self._process.readyReadStandardError.connect(self._drain_stderr)
        self._process.started.connect(self._on_started)
        self._process.finished.connect(self._on_finished)

        import json as _json
        self._process.start(sys.executable, [
            "-m", "gui_next.execution.runner", str(spec_path)])
        if not self._process.waitForStarted(10_000):
            self._fail("分析子进程启动失败")
            return False

        pid = self._process.processId()
        try:
            from shared.corpus_sanity import corpus_fingerprint
            self._corpus_fingerprint = corpus_fingerprint(self.root / "corpus")["sha256"]
        except Exception:
            self._corpus_fingerprint = ""
        jobs.update_run(self.root, run_id, pid=pid, corpus_fingerprint=self._corpus_fingerprint)
        return True

    # ------------------------------------------------------------------
    # process plumbing

    def _on_started(self) -> None:
        self._set_state(RunState.RUNNING, "分析子进程已启动")

    def _drain_stdout(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            if not line.strip():
                continue
            event = parse(line)
            if event["event"] == "stage":
                # Stage events only drive the initial PREPARING->RUNNING
                # transition; they must never override CANCELLING or a
                # terminal state set by the controller itself.
                if self.state is RunState.PREPARING:
                    self._set_state(RunState.RUNNING, event.get("message", ""))
                else:
                    self.log_line.emit(f"[stage] {event.get('message', '')}")
            elif event["event"] == "error":
                self.last_error = event
                self.logs.append(f"[error] {event.get('type')}: {event.get('message')}")
                self.log_line.emit(f"[error] {event.get('type')}: {event.get('message')}")
            elif event["event"] == "result":
                self.outputs = event.get("outputs", {})
            else:
                self.logs.append(event.get("line", ""))
                self.log_line.emit(event.get("line", ""))
        del self.logs[:-2000]

    def _drain_stderr(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.strip():
                self.logs.append("[stderr] " + line)
                self.log_line.emit("[stderr] " + line)
        del self.logs[:-2000]

    # ------------------------------------------------------------------
    # cancellation

    def cancel(self) -> None:
        if self.state not in (RunState.PREPARING, RunState.RUNNING):
            return
        self._cancel_requested = True
        self._set_state(RunState.CANCELLING, "正在等待当前步骤安全结束……(输出已隔离,不会影响既有结果)")
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            self._process.terminate()
            self._kill_timer.start()
        else:
            self._on_finished(0, QProcess.NormalExit)

    def _force_kill(self) -> None:
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            self._process.kill()

    # ------------------------------------------------------------------
    # completion

    def _on_finished(self, exit_code: int, exit_status) -> None:
        self._kill_timer.stop()
        was_cancelling = self._cancel_requested
        # Drain whatever the child wrote before exiting.
        if self._process is not None:
            self._drain_stdout()
            self._drain_stderr()

        if was_cancelling:
            self._set_state(RunState.CANCELLED, "运行已取消;工作目录已保留,既有结果未被修改。")
            jobs.update_run(self.root, self.run_id,
                            status=RunState.CANCELLED.value, finished_at=self._now())
            self._terminate()
            return

        if exit_status != QProcess.NormalExit or exit_code != 0:
            detail = "分析失败"
            if self.last_error:
                detail = f"{self.last_error.get('type', 'Error')}: {self.last_error.get('message', '')}"
            elif self.error:
                detail = self.error
            self._set_state(RunState.FAILED, detail)
            jobs.update_run(self.root, self.run_id,
                            status=RunState.FAILED.value, finished_at=self._now(),
                            error=detail)
            self._terminate()
            return

        if self.kind != "analyze":
            # Sanity ran against the real project; nothing to publish.
            jobs.update_run(self.root, self.run_id,
                            status=RunState.SUCCEEDED.value, finished_at=self._now())
            self._set_state(RunState.SUCCEEDED, "sanity 检查完成。")
            self._terminate()
            return

        self._publish()

    # ------------------------------------------------------------------
    # transactional publication (Phase 2B.1)

    def _publish(self) -> None:
        from gui_next.execution import publication
        from gui_next.execution.publication import PublicationError

        self._set_state(RunState.ANALYSIS_SUCCEEDED,
                        "分析子进程成功完成;准备事务化发布产物")
        jobs.update_run(self.root, self.run_id,
                        status=RunState.ANALYSIS_SUCCEEDED.value)

        pending = publication.recovery_required(self.root)
        if pending:
            self._fail_publish(
                f"存在未恢复的发布事务({', '.join(p['run_id'] for p in pending)}),"
                "在完整性解决前禁止新的发布。")
            return

        try:
            corpus_fp = self._corpus_fingerprint
            previous = publication.last_publication_record(self.root)
            manifest = publication.build_manifest(
                work_dir=self.work_dir, project_dir=self.root, run_id=self.run_id,
                corpus_fingerprint=corpus_fp,
                params={k: self.params.get(k) for k in
                        ("targets", "group_by", "mi_threshold", "pos_translate")},
                produced=self.outputs.get("produced", []),
                previous_record=previous,
            )

            def progress(stage: str, message: str) -> None:
                self._set_state(RunState.PUBLISHING, f"{stage}: {message}")

            record = publication.execute_publication(
                manifest, self.work_dir, self.root, self.run_id,
                progress_cb=progress,
                fault_injection=self.publication_fault_injection,
            )
            publication.write_published_pointer(self.root, record)
            jobs.update_run(self.root, self.run_id,
                            status=RunState.SUCCEEDED.value, finished_at=self._now(),
                            published_count=len(record["owned_paths"]),
                            published_run_id=self.run_id,
                            manifest_sha256=record["manifest_sha256"])
            self._set_state(RunState.SUCCEEDED,
                            f"发布完成({len(record['owned_paths'])} 个 owned outputs 已提交)。")
            self._terminate()
        except PublicationError as exc:
            self._fail_publish(str(exc))
        except Exception as exc:  # noqa: BLE001 - any publish crash -> rollback path
            self._fail_publish(f"发布过程异常: {exc}")

    def _fail_publish(self, message: str) -> None:
        jobs.update_run(self.root, self.run_id,
                        status=RunState.PUBLISH_FAILED.value, finished_at=self._now(),
                        error=message)
        self._set_state(RunState.PUBLISH_FAILED,
                        message + "(旧成功结果保持有效;工作目录与事务现场已保留)")
        self._terminate()

    def _fail(self, message: str) -> None:
        self._set_state(RunState.FAILED, message)
        jobs.update_run(self.root, self.run_id, status=RunState.FAILED.value,
                        finished_at=self._now(), error=message)
        self._terminate()

    def _terminate(self) -> None:
        jobs.release_writer_lock(self.root, self.run_id)
        self.finished.emit(self.state.value)

    # ------------------------------------------------------------------

    def _set_state(self, state: RunState, message: str) -> None:
        self.state = state
        self.log_line.emit(f"[{state.value}] {message}")
        self.state_changed.emit(state.value, message)

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
