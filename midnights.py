from datetime import datetime, timedelta
import time

WEEKDAYS_DICT = {
    1: "Esmaspäev",
    2: "Teisipäev",
    3: "Kolmapäev",
    4: "Neljapäev",
    5: "Reede",
    6: "Laupäev",
    7: "Pühapäev"
}

MONTHS_DICT = {
    1: "jaanuar",
    2: "veebruar",
    3: "märts",
    4: "aprill",
    5: "mai",
    6: "juuni",
    7: "juuli",
    8: "august",
    9: "september",
    10: "oktoober",
    11: "november",
    12: "detsember",
}

def convert_to_timestamp(input_datetime):
    add_hours = 0  # TODO: TIMEZONE SUPPORT
    timezoned_datetime = input_datetime + timedelta(hours=add_hours)
    return time.mktime(timezoned_datetime.timetuple())*1000


def get(input_datetimes):
    midnight_timestamps = {}
    for date_time in input_datetimes:
        if date_time.hour == 0:
            weekday = WEEKDAYS_DICT[date_time.isoweekday()]
            day = date_time.day
            month = MONTHS_DICT[date_time.month]
            date_text = "{0}, {1}. {2}".format(weekday, day, month)
            timestamp = convert_to_timestamp(date_time)
            midnight_timestamps[timestamp] = date_text
    return midnight_timestamps
