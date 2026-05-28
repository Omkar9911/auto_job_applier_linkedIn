from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import csv
from datetime import datetime
import os
import subprocess
import sys
import threading
import time

app = Flask(__name__)
CORS(app)

try:
    from config.settings import file_name as APPLIED_JOBS_CSV  # type: ignore
except Exception:
    APPLIED_JOBS_CSV = os.path.join("all excels", "all_applied_applications_history.csv")

APPLIED_JOBS_CSV = os.path.normpath(APPLIED_JOBS_CSV)
BOT_SCRIPT = os.path.normpath("runAiBot.py")
BOT_PID_PATH = os.path.normpath(os.path.join("logs", "bot.pid"))


class BotManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._log_fp = None
        self._last_start_ts: float | None = None

    def status(self) -> dict:
        with self._lock:
            if not self._proc:
                pid = self._read_pid_file()
                if pid and self._pid_is_running(pid):
                    return {"status": "running", "pid": pid, "last_start": self._last_start_ts, "detached": True}

                self._clear_pid_file()
                return {"status": "stopped", "pid": None, "last_start": self._last_start_ts}

            code = self._proc.poll()
            if code is None:
                return {"status": "running", "pid": self._proc.pid, "last_start": self._last_start_ts}

            self._cleanup_locked()
            return {"status": "stopped", "pid": None, "exit_code": code, "last_start": self._last_start_ts}

    def start(self) -> tuple[bool, dict]:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return False, {"error": "Bot is already running", "pid": self._proc.pid}

            if not os.path.exists(BOT_SCRIPT):
                return False, {"error": f"Bot script not found at {BOT_SCRIPT}"}

            os.makedirs("logs", exist_ok=True)
            log_path = os.path.join("logs", "bot.log")
            self._log_fp = open(log_path, "a", encoding="utf-8", buffering=1)

            creationflags = 0
            kwargs: dict = {}
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            else:
                kwargs["start_new_session"] = True

            self._proc = subprocess.Popen(
                [sys.executable, BOT_SCRIPT],
                stdout=self._log_fp,
                stderr=self._log_fp,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                **kwargs,
            )
            self._write_pid_file(self._proc.pid)
            self._last_start_ts = time.time()
            return True, {"status": "running", "pid": self._proc.pid, "log": os.path.normpath(log_path)}

    def stop(self) -> tuple[bool, dict]:
        with self._lock:
            if not self._proc or self._proc.poll() is not None:
                # Handle a detached bot process (e.g., server restarted).
                pid = self._read_pid_file()
                if pid and self._pid_is_running(pid):
                    self._kill_pid(pid)
                    self._cleanup_locked()
                    return True, {"status": "stopped", "pid": pid}

                self._cleanup_locked()
                return False, {"error": "Bot is not running"}

            pid = self._proc.pid

            try:
                self._kill_pid(pid)
            finally:
                self._cleanup_locked()

            return True, {"status": "stopped", "pid": pid}

    def _cleanup_locked(self) -> None:
        if self._proc:
            try:
                self._proc.wait(timeout=0.2)
            except Exception:
                pass
        self._proc = None
        if self._log_fp:
            try:
                self._log_fp.close()
            except Exception:
                pass
        self._log_fp = None
        self._clear_pid_file()

    def _write_pid_file(self, pid: int) -> None:
        try:
            os.makedirs(os.path.dirname(BOT_PID_PATH), exist_ok=True)
            with open(BOT_PID_PATH, "w", encoding="utf-8") as f:
                f.write(str(pid))
        except Exception:
            pass

    def _read_pid_file(self) -> int | None:
        try:
            if not os.path.exists(BOT_PID_PATH):
                return None
            with open(BOT_PID_PATH, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            return int(raw) if raw else None
        except Exception:
            return None

    def _clear_pid_file(self) -> None:
        try:
            if os.path.exists(BOT_PID_PATH):
                os.remove(BOT_PID_PATH)
        except Exception:
            pass

    def _pid_is_running(self, pid: int) -> bool:
        try:
            if os.name == "nt":
                out = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout
                return str(pid) in out

            # POSIX
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    def _kill_pid(self, pid: int) -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
            return

        try:
            os.kill(pid, 15)
        except Exception:
            pass


bot_manager = BotManager()


def formatted_applied_datetime() -> str:
    now = datetime.now()
    return f"{now.strftime('%d')} {now.strftime('%b').lower()} {now.strftime('%Y')}, {now.strftime('%I:%M:%S %p')}"

##> ------ Karthik Sarode : karthik.sarode23@gmail.com - UI for excel files ------
@app.route('/')
def home():
    """Displays the home page of the application."""
    return render_template("index.html", csv_path=APPLIED_JOBS_CSV)


@app.route("/bot/status", methods=["GET"])
def bot_status():
    return jsonify(bot_manager.status())


@app.route("/bot/start", methods=["POST"])
def bot_start():
    ok, payload = bot_manager.start()
    return jsonify(payload), (200 if ok else 409)


@app.route("/bot/stop", methods=["POST"])
def bot_stop():
    ok, payload = bot_manager.stop()
    return jsonify(payload), (200 if ok else 409)

@app.route('/applied-jobs', methods=['GET'])
def get_applied_jobs():
    '''
    Retrieves a list of applied jobs from the applications history CSV file.
    
    Returns a JSON response containing a list of jobs, each with details such as 
    Job ID, Title, Company, HR Name, HR Link, Job Link, External Job link, and Date Applied.
    
    If the CSV file is not found, returns a 404 error with a relevant message.
    If any other exception occurs, returns a 500 error with the exception message.
    '''

    try:
        jobs = []
        with open(APPLIED_JOBS_CSV, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                jobs.append({
                    'Job_ID': row['Job ID'],
                    'Title': row['Title'],
                    'Company': row['Company'],
                    'HR_Name': row['HR Name'],
                    'HR_Link': row['HR Link'],
                    'Job_Link': row['Job Link'],
                    'External_Job_link': row['External Job link'],
                    'Date_Applied': row['Date Applied']
                })
        return jsonify(jobs)
    except FileNotFoundError:
        return jsonify({"error": "No applications history found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/applied-jobs/<job_id>', methods=['PUT'])
def update_applied_date(job_id):
    """
    Updates the 'Date Applied' field of a job in the applications history CSV file.

    Args:
        job_id (str): The Job ID of the job to be updated.

    Returns:
        A JSON response with a message indicating success or failure of the update
        operation. If the job is not found, returns a 404 error with a relevant
        message. If any other exception occurs, returns a 500 error with the
        exception message.
    """
    try:
        data = []
        csvPath = APPLIED_JOBS_CSV
        
        if not os.path.exists(csvPath):
            return jsonify({"error": f"CSV file not found at {csvPath}"}), 404
            
        # Read current CSV content
        with open(csvPath, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldNames = reader.fieldnames
            found = False
            for row in reader:
                if row['Job ID'] == job_id:
                    row['Date Applied'] = formatted_applied_datetime()
                    found = True
                data.append(row)
        
        if not found:
            return jsonify({"error": f"Job ID {job_id} not found"}), 404

        with open(csvPath, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldNames)
            writer.writeheader()
            writer.writerows(data)
        
        return jsonify({"message": "Date Applied updated successfully"}), 200
    except Exception as e:
        print(f"Error updating applied date: {str(e)}")  # Debug log
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Disable the reloader so we don't accidentally create multiple bot managers/processes.
    app.run(host="127.0.0.1", port=8080, debug=True, use_reloader=False)

##<
