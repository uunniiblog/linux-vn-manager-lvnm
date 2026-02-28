import threading
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
from PySide6.QtCore import QProcess, QProcessEnvironment, Signal, Slot
from PySide6.QtGui import QTextCursor
import logging

logger = logging.getLogger(__name__)

class ConsoleDialog(QDialog):
    finished_all = Signal() # Signal emitted when the queue is empty
    task_finished = Signal()
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
        self.task_finished.connect(self._on_process_finished)
        self.append_text_signal.connect(self.console.append)

        self.task_queue = []
        self.current_callback = None

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
        if not self.task_queue:
            self.console.append("\n[Done] No tasks to execute.")
            self.close_btn.setEnabled(True)
            return
        self._run_next()

    def _run_next(self):
        if self.task_queue:
            task = self.task_queue.pop(0)
            logger.debug(f"[debug] Starting task {task["desc"]}")
            self.current_callback = task["callback"]
            
            self.console.append(f"\n>>> {task['desc']}...")

            cmd = task["cmd"]

            try:
                if isinstance(cmd, list):
                    qenv = QProcessEnvironment.systemEnvironment()
                    for k, v in task["env"].items():
                        qenv.insert(k, str(v))
                    self.process.setProcessEnvironment(qenv)
                    self.process.start(cmd[0], cmd[1:])
                elif callable(cmd):
                    def wrapper():
                        try:
                            # Pass the logger to methods queued up so it shows up in the dialog
                           cmd(logger=self.append_text_signal.emit)
                        except Exception as e:
                            self.append_text_signal.emit(f"[Thread Error] {e}")
                        
                        # Tell the main thread this task is done so it can run the next one
                        self.task_finished.emit()

                    threading.Thread(target=wrapper, daemon=True).start()
            except Exception as e:
                logger.error(f"[Error] Task failed: {e}")

        else:
            self.console.append("\n--- All tasks completed successfully ---")
            self.close_btn.setEnabled(True)
            self.finished_all.emit()

    def _on_process_finished(self):
        # Run callback then move to next task
        logger.debug(f"Task finished")
        if self.current_callback:
            self.current_callback()
        self._run_next()

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
        html = f"""
        <div style='margin-bottom: 10px;'>
            <b style='color: #ff9800;'>[ENVIRONMENT]</b><br>
            <b style='color: #4db6ac;'>Prefix:</b> {prefix_path}<br>
            <b style='color: #4db6ac;'>Runner:</b> {runner_path}
        </div>
        <hr style='border: 1px solid #333;'>
        """
        self.console.insertHtml(html)
        # Move cursor to end so tasks append after the header
        self.console.moveCursor(QTextCursor.End)