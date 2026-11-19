"""The business runs on India time: «today» everywhere in the app is the date in Asia/Kolkata."""
import datetime as dt
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now() -> dt.datetime:
    return dt.datetime.now(IST)


def today() -> dt.date:
    return now().date()
