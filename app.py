from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import csv
from datetime import datetime
import ast
import json
import os
import subprocess
import sys
import threading
import time

app = Flask(__name__)
CORS(app)

try:
    from config.settings import failed_file_name as SKIPPED_JOBS_CSV
    from config.settings import file_name as APPLIED_JOBS_CSV  # type: ignore
except Exception:
    APPLIED_JOBS_CSV = os.path.join("all excels", "all_applied_applications_history.csv")
    SKIPPED_JOBS_CSV = os.path.join("all excels", "all_failed_applications_history.csv")

APPLIED_JOBS_CSV = os.path.normpath(APPLIED_JOBS_CSV)
SKIPPED_JOBS_CSV = os.path.normpath(SKIPPED_JOBS_CSV)
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
            time.sleep(1)
            code = self._proc.poll()
            if code is not None:
                error_tail = self._read_log_tail(log_path)
                self._cleanup_locked()
                return False, {
                    "error": "Bot failed to start",
                    "exit_code": code,
                    "log": os.path.normpath(log_path),
                    "details": error_tail,
                }
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

    def _read_log_tail(self, log_path: str, max_chars: int = 4000) -> str:
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as log_file:
                log_file.seek(0, os.SEEK_END)
                size = log_file.tell()
                log_file.seek(max(0, size - max_chars))
                return log_file.read().strip()
        except Exception:
            return ""


bot_manager = BotManager()


SETTINGS_SCHEMA = {
    "personals": {
        "label": "Personal Details",
        "module": "config.personals",
        "fields": {
            "first_name": {"label": "First Name", "type": "text"},
            "middle_name": {"label": "Middle Name", "type": "text"},
            "last_name": {"label": "Last Name", "type": "text"},
            "phone_number": {"label": "Phone Number", "type": "text"},
            "current_city": {"label": "Current City", "type": "text"},
            "street": {"label": "Street Address", "type": "text"},
            "state": {"label": "State", "type": "text"},
            "zipcode": {"label": "Zipcode", "type": "text"},
            "country": {"label": "Country", "type": "text"},
            "gender": {"label": "Gender", "type": "select", "options": ["", "Male", "Female", "Other", "Decline"]},
            "disability_status": {"label": "Disability Status", "type": "select", "options": ["", "Yes", "No", "Decline"]},
            "veteran_status": {"label": "Veteran Status", "type": "select", "options": ["", "Yes", "No", "Decline"]},
        },
    },
    "questions": {
        "label": "Application Answers",
        "module": "config.questions",
        "fields": {
            "default_resume_path": {"label": "Default Resume Path", "type": "text"},
            "years_of_experience": {"label": "Years of Experience", "type": "text"},
            "require_visa": {"label": "Need Visa Sponsorship", "type": "select", "options": ["Yes", "No"]},
            "website": {"label": "Website / Portfolio", "type": "text"},
            "linkedIn": {"label": "LinkedIn Profile", "type": "text"},
            "us_citizenship": {"label": "Citizenship Status", "type": "text"},
            "desired_salary": {"label": "Desired Salary / Expected CTC", "type": "number"},
            "current_ctc": {"label": "Current CTC", "type": "number"},
            "notice_period": {"label": "Notice Period Days", "type": "number"},
            "linkedin_headline": {"label": "LinkedIn Headline", "type": "text"},
            "linkedin_summary": {"label": "LinkedIn Summary", "type": "textarea"},
            "cover_letter": {"label": "Cover Letter", "type": "textarea"},
            "user_information_all": {"label": "AI User Information", "type": "textarea"},
            "recent_employer": {"label": "Recent Employer", "type": "text"},
            "confidence_level": {"label": "Confidence Level", "type": "text"},
            "pause_before_submit": {"label": "Pause Before Submit", "type": "boolean"},
            "pause_at_failed_question": {"label": "Pause On Unknown Question", "type": "boolean"},
            "overwrite_previous_answers": {"label": "Overwrite Previous Answers", "type": "boolean"},
        },
    },
    "search": {
        "label": "Search & Filters",
        "module": "config.search",
        "fields": {
            "search_terms": {"label": "Search Terms", "type": "list"},
            "search_location": {"label": "Search Location", "type": "text"},
            "switch_number": {"label": "Applications Per Search", "type": "number"},
            "randomize_search_order": {"label": "Randomize Search Order", "type": "boolean"},
            "sort_by": {"label": "Sort By", "type": "select", "options": ["", "Most recent", "Most relevant"]},
            "date_posted": {"label": "Date Posted", "type": "select", "options": ["", "Any time", "Past month", "Past week", "Past 24 hours"]},
            "easy_apply_only": {"label": "Easy Apply Only", "type": "boolean"},
            "experience_level": {"label": "Experience Levels", "type": "list"},
            "job_type": {"label": "Job Types", "type": "list"},
            "on_site": {"label": "Work Modes", "type": "list"},
            "companies": {"label": "Companies", "type": "list"},
            "location": {"label": "Filter Locations", "type": "list"},
            "bad_words": {"label": "Skip Job Description Words", "type": "list"},
            "about_company_bad_words": {"label": "Skip Company Words", "type": "list"},
            "security_clearance": {"label": "Has Security Clearance", "type": "boolean"},
            "did_masters": {"label": "Has Masters Degree", "type": "boolean"},
            "current_experience": {"label": "Current Experience", "type": "number"},
            "pause_after_filters": {"label": "Pause After Filters", "type": "boolean"},
        },
    },
    "secrets": {
        "label": "Login & AI",
        "module": "config.secrets",
        "fields": {
            "username": {"label": "LinkedIn Username", "type": "text"},
            "password": {"label": "LinkedIn Password", "type": "password"},
            "use_AI": {"label": "Use AI", "type": "boolean"},
            "ai_provider": {"label": "AI Provider", "type": "select", "options": ["openai", "deepseek", "gemini"]},
            "llm_api_url": {"label": "LLM API URL", "type": "text"},
            "llm_api_key": {"label": "LLM API Key", "type": "password"},
            "llm_model": {"label": "LLM Model", "type": "text"},
            "llm_spec": {"label": "LLM Spec", "type": "text"},
            "stream_output": {"label": "Stream AI Output", "type": "boolean"},
        },
    },
    "settings": {
        "label": "Bot Runtime",
        "module": "config.settings",
        "fields": {
            "run_non_stop": {"label": "Run Non Stop", "type": "boolean"},
            "alternate_sortby": {"label": "Alternate Sort By", "type": "boolean"},
            "cycle_date_posted": {"label": "Cycle Date Posted", "type": "boolean"},
            "file_name": {"label": "Applied Jobs CSV", "type": "text"},
            "failed_file_name": {"label": "Skipped/Failed Jobs CSV", "type": "text"},
            "click_gap": {"label": "Click Gap Seconds", "type": "number"},
            "run_in_background": {"label": "Run Browser In Background", "type": "boolean"},
            "safe_mode": {"label": "Safe Mode", "type": "boolean"},
            "stealth_mode": {"label": "Stealth Mode", "type": "boolean"},
            "keep_screen_awake": {"label": "Keep Screen Awake", "type": "boolean"},
            "showAiErrorAlerts": {"label": "Show AI Error Alerts", "type": "boolean"},
        },
    },
}


def get_user_settings_path() -> str:
    from config.dynamic_settings import USER_SETTINGS_PATH
    return USER_SETTINGS_PATH


def load_dashboard_settings() -> dict:
    path = get_user_settings_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as settings_file:
            data = json.load(settings_file)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_dashboard_settings(settings: dict) -> None:
    path = get_user_settings_path()
    with open(path, "w", encoding="utf-8") as settings_file:
        json.dump(settings, settings_file, indent=2)


def coerce_setting_value(value, field_type: str):
    if field_type == "boolean":
        return bool(value)
    if field_type == "number":
        if value == "" or value is None:
            return 0
        return int(value) if float(value).is_integer() else float(value)
    if field_type == "list":
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [item.strip() for item in str(value).split(",") if item.strip()]
    return "" if value is None else str(value)


def get_settings_payload() -> dict:
    saved = load_dashboard_settings()
    sections = {}
    for section_key, section in SETTINGS_SCHEMA.items():
        defaults = load_config_defaults(section["module"])
        values = {}
        for field_key, field in section["fields"].items():
            values[field_key] = saved.get(section_key, {}).get(field_key, defaults.get(field_key, ""))
        sections[section_key] = {
            "label": section["label"],
            "fields": section["fields"],
            "values": values,
        }
    return {"sections": sections, "bot_running": bot_manager.status()["status"] == "running"}


def load_config_defaults(module_name: str) -> dict:
    config_path = os.path.join(*module_name.split(".")) + ".py"
    if not os.path.exists(config_path):
        return {}

    defaults = {}
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            tree = ast.parse(config_file.read(), filename=config_path)
    except Exception:
        return defaults

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except Exception:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                defaults[target.id] = value
    return defaults


def formatted_applied_datetime() -> str:
    now = datetime.now()
    return f"{now.strftime('%d')} {now.strftime('%b').lower()} {now.strftime('%Y')}, {now.strftime('%I:%M:%S %p')}"


def csv_value(row: dict, key: str, default: str = "") -> str:
    return (row.get(key) or default).strip()

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


@app.route("/settings", methods=["GET"])
def get_settings():
    return jsonify(get_settings_payload())


@app.route("/settings", methods=["PUT"])
def update_settings():
    payload = request.get_json(silent=True) or {}
    incoming_sections = payload.get("sections", payload)
    saved = load_dashboard_settings()

    for section_key, section_values in incoming_sections.items():
        if section_key not in SETTINGS_SCHEMA or not isinstance(section_values, dict):
            continue

        saved.setdefault(section_key, {})
        fields = SETTINGS_SCHEMA[section_key]["fields"]
        for field_key, value in section_values.items():
            if field_key not in fields:
                continue
            saved[section_key][field_key] = coerce_setting_value(value, fields[field_key]["type"])

    save_dashboard_settings(saved)
    return jsonify({
        "message": "Settings saved successfully. Restart the bot to apply running automation changes.",
        "settings": get_settings_payload(),
    })

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
                    'Record_Type': 'Applied',
                    'Job_ID': csv_value(row, 'Job ID'),
                    'Title': csv_value(row, 'Title', 'N/A'),
                    'Company': csv_value(row, 'Company', 'N/A'),
                    'Work_Location': csv_value(row, 'Work Location', 'N/A'),
                    'Work_Style': csv_value(row, 'Work Style', 'N/A'),
                    'HR_Name': csv_value(row, 'HR Name', 'Unknown'),
                    'HR_Link': csv_value(row, 'HR Link', 'Unknown'),
                    'Job_Link': csv_value(row, 'Job Link'),
                    'External_Job_link': csv_value(row, 'External Job link'),
                    'Date_Applied': csv_value(row, 'Date Applied'),
                    'Date_Tried': csv_value(row, 'Date Applied'),
                    'Reason': 'Applied',
                    'Resume': csv_value(row, 'Resume', 'N/A'),
                    'Details': csv_value(row, 'About Job', '')
                })
        if os.path.exists(SKIPPED_JOBS_CSV):
            with open(SKIPPED_JOBS_CSV, "r", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    reason = csv_value(row, 'Assumed Reason', 'Skipped')
                    status = 'Skipped' if 'skip' in reason.lower() or csv_value(row, 'External Job link') == 'Skipped' else 'Failed'
                    jobs.append({
                        'Record_Type': status,
                        'Job_ID': csv_value(row, 'Job ID'),
                        'Title': csv_value(row, 'Title', 'N/A'),
                        'Company': csv_value(row, 'Company', 'N/A'),
                        'Work_Location': csv_value(row, 'Work Location', 'N/A'),
                        'Work_Style': csv_value(row, 'Work Style', 'N/A'),
                        'HR_Name': 'N/A',
                        'HR_Link': '',
                        'Job_Link': csv_value(row, 'Job Link'),
                        'External_Job_link': csv_value(row, 'External Job link', 'Skipped'),
                        'Date_Applied': 'Pending',
                        'Date_Tried': csv_value(row, 'Date Tried'),
                        'Reason': reason,
                        'Resume': csv_value(row, 'Resume Tried', 'N/A'),
                        'Details': csv_value(row, 'Stack Trace', ''),
                        'Screenshot_Name': csv_value(row, 'Screenshot Name', 'N/A')
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
