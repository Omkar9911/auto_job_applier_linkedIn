'''
Author: Omkar Jadhav
'''

import os

first_name = os.environ.get("LINKEDIN_FIRST_NAME", "")
middle_name = os.environ.get("LINKEDIN_MIDDLE_NAME", "")
last_name = os.environ.get("LINKEDIN_LAST_NAME", "")

phone_number = os.environ.get("LINKEDIN_PHONE_NUMBER", "")
current_city = os.environ.get("LINKEDIN_CURRENT_CITY", "")
street = os.environ.get("LINKEDIN_STREET", "")
state = os.environ.get("LINKEDIN_STATE", "")
zipcode = os.environ.get("LINKEDIN_ZIPCODE", "")
country = os.environ.get("LINKEDIN_COUNTRY", "")

ethnicity = os.environ.get("LINKEDIN_ETHNICITY", "Decline")
gender = os.environ.get("LINKEDIN_GENDER", "")
disability_status = os.environ.get("LINKEDIN_DISABILITY_STATUS", "Decline")
veteran_status = os.environ.get("LINKEDIN_VETERAN_STATUS", "Decline")

from config.dynamic_settings import apply_overrides
apply_overrides(globals(), "personals")
