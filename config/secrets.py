'''
Author: Omkar Jadhav
'''

import os

username = os.environ.get("LINKEDIN_USERNAME", "")
password = os.environ.get("LINKEDIN_PASSWORD", "")

use_AI = os.environ.get("USE_AI", "false").lower() == "true"
ai_provider = os.environ.get("AI_PROVIDER", "openai")

llm_api_url = os.environ.get("LLM_API_URL", "https://api.openai.com/v1")
llm_api_key = os.environ.get("LLM_API_KEY", "")
llm_model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
llm_spec = os.environ.get("LLM_SPEC", "")
stream_output = os.environ.get("STREAM_OUTPUT", "false").lower() == "true"

from config.dynamic_settings import apply_overrides
apply_overrides(globals(), "secrets")
