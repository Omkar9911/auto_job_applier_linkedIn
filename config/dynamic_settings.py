'''
Author: Omkar Jadhav
'''

import json
import os


USER_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "user_settings.json")


def load_user_settings() -> dict:
    if not os.path.exists(USER_SETTINGS_PATH):
        return {}

    try:
        with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as settings_file:
            data = json.load(settings_file)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def apply_overrides(module_globals: dict, section: str) -> None:
    settings = load_user_settings().get(section, {})
    if not isinstance(settings, dict):
        return

    for key, value in settings.items():
        if key in module_globals:
            module_globals[key] = value
