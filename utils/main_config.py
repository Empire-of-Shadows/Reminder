import pytz
from datetime import datetime

# Specify time zone
time_zone = "America/Chicago"
time_zone_obj = pytz.timezone(time_zone)

# Get current time in UTC and then convert to local time
utc_now = datetime.now(pytz.utc)  # Current time in UTC
local_time = utc_now.astimezone(time_zone_obj)

