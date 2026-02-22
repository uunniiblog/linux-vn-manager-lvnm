from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
from PySide6.QtCore import QProcess, QProcessEnvironment, Signal
from PySide6.QtGui import QTextCursor

class ConsoleDialog(QDialog):
    finished_all = Signal() # Signal emitted when the queue is empty

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
            self.current_callback = task["callback"]
            
            self.console.append(f"\n>>> {task['desc']}...")
            
            # Setup environment
            qenv = QProcessEnvironment.systemEnvironment()
            for k, v in task["env"].items():
                qenv.insert(k, str(v))
            self.process.setProcessEnvironment(qenv)
            
            self.process.start(task["cmd"][0], task["cmd"][1:])
        else:
            self.console.append("\n--- All tasks completed successfully ---")
            self.close_btn.setEnabled(True)
            self.finished_all.emit()

    def _on_process_finished(self):
        # Run the internal logic (like updating JSON) before moving to next task
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