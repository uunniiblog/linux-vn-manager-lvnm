import threading
import shlex
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
from PySide6.QtCore import QProcess, QProcessEnvironment, Signal, Slot
from PySide6.QtGui import QTextCursor
import logging
from execution_manager import ExecutionManager

logger = logging.getLogger(__name__)

class ConsoleDialog(QDialog):
    finished_all = Signal() # Signal emitted when the queue is empty
    failed = Signal(str)
    task_finished = Signal(bool, str)
    append_text_signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Console Output"))
        self.resize(700, 450)
        
        layout = QVBoxLayout(self)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: #1e1e1e; color: #dcdcdc; font-family: monospace;")
        layout.addWidget(self.console)

        self.close_btn = QPushButton(self.tr("Close"))
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self._on_process_finished)
        self.task_finished.connect(self._on_callable_finished)
        self.append_text_signal.connect(self.console.append)
        self._had_error = False
        self.process.errorOccurred.connect(self._on_process_error)

        self.task_queue = []
        self.current_callback = None
        self.completed_successfully = False

    def add_task(self, cmd, env, description, on_finished_callback=None):
        """Adds a command to the queue."""
        self.task_queue.append({
            "cmd": cmd,
            "env": env,
            "desc": description,
            "callback": on_finished_callback
        })

    def start_queue(self):
        """Starts executing the first task in the queue."""
        self.completed_successfully = False
        if not self.task_queue:
            self.console.append(self.tr("\n[Done] No tasks to execute."))
            self.close_btn.setEnabled(True)
            self.completed_successfully = True
            return
        self._run_next()

    def _run_next(self):
        if self.task_queue:
            task = self.task_queue.pop(0)
            self.current_callback = task["callback"]
            
            self.console.append(self.tr("\n>>> {}...").format(task['desc']))

            cmd = task["cmd"]

            try:
                if isinstance(cmd, list):
                    self.console.append(f"$ {shlex.join(str(part) for part in cmd)}")
                    qenv = QProcessEnvironment()
                    final_env = ExecutionManager._get_verbosity_env(task["env"])
                    for k, v in final_env.items():
                        qenv.insert(k, str(v))
                    self.process.setProcessEnvironment(qenv)
                    self.process.start(cmd[0], cmd[1:])
                elif callable(cmd):
                    def wrapper():
                        try:
                            # Pass the logger to methods queued up so it shows up in the dialog
                            cmd(logger=self.append_text_signal.emit)
                        except Exception as e:
                            self.task_finished.emit(False, str(e))
                            return

                        # Tell the main thread this task is done so it can run the next one
                        self.task_finished.emit(True, "")

                    threading.Thread(target=wrapper, daemon=True).start()
            except Exception as e:
                self._abort_queue(str(e))

        else:
            self.console.append(self.tr("\n--- All tasks completed successfully ---"))
            self.close_btn.setEnabled(True)
            self.completed_successfully = True
            self.finished_all.emit()

    def _on_process_finished(self, exit_code=0, exit_status=QProcess.NormalExit):
        # Drain any final output emitted immediately before process exit.
        self.handle_stdout()
        self.handle_stderr()

        # Check error
        if self._had_error:
            self._had_error = False
            return

        if exit_status != QProcess.NormalExit or exit_code != 0:
            self._abort_queue(self.tr("Process exited with code {}.").format(exit_code))
            return

        # Run callback then move to next task
        if self.current_callback:
            try:
                self.current_callback()
            except Exception as e:
                self._abort_queue(str(e))
                return
        self._run_next()

    @Slot(bool, str)
    def _on_callable_finished(self, success, error_message):
        if not success:
            self._abort_queue(error_message)
            return
        self._on_process_finished()

    def _abort_queue(self, error_message):
        self.task_queue.clear()
        self.current_callback = None
        self.completed_successfully = False
        message = self.tr("\n[ERROR] {}").format(error_message)
        self.console.append(message)
        self.console.append(self.tr("\nTask queue aborted due to error."))
        self.close_btn.setEnabled(True)
        self.failed.emit(error_message)
        logger.error("Console task queue aborted: %s", error_message)

    def _on_process_error(self, error):
        """Captures errors when the process fails to start or crashes."""
        self._had_error = True
        error_msg = self.process.errorString()
        exit_code = self.process.exitCode()
        exit_status = self.process.exitStatus()
        self.append_text_signal.emit(self.tr("\n[FATAL ERROR] Could not start process: {}").format(error_msg))
        logger.error(f"console tasks ERROR: {error_msg} | exitCode={exit_code} | exitStatus={exit_status} | errorCode={error}")
        self._abort_queue(error_msg)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode(errors='replace').strip()
        if data:
            self.console.append(data)
            self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode(errors='replace').strip()
        if data:
            self.console.append(data)
            self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def set_header_info(self, prefix_path, runner_path):
        """Displays initialization info at the top."""
        html = self.tr("""
        <div style='margin-bottom: 10px;'>
            <b style='color: #ff9800;'>[ENVIRONMENT]</b><br>
            <b style='color: #4db6ac;'>Prefix:</b> {prefix_path}<br>
            <b style='color: #4db6ac;'>Runner:</b> {runner_path}
        </div>
        <hr style='border: 1px solid #333;'>
        """).format(prefix_path=prefix_path, runner_path=runner_path)
        self.console.insertHtml(html)
        # Move cursor to end so tasks append after the header
        self.console.moveCursor(QTextCursor.End)