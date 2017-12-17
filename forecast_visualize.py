from bokeh.plotting import figure, ColumnDataSource
from bokeh.models import DatetimeTickFormatter, Range1d, LinearAxis, \
    SingleIntervalTicker, LabelSet, Label, Span
from bokeh.models.widgets import Div, AutocompleteInput
from bokeh.io import curdoc
from bokeh.layouts import layout

import numpy as np
import pandas as pd
from forecast_data import City
import midnights

from default_data import CITY_MAP


def update() -> None:
    """
    Updates the data source based on the city_picker (i.e. user input) value and changes plot title.
    :return: None
    """
    global source, city, temp_plus_dominates
    input_city = city_picker.value
    city = City(input_city)
    forecast = city.union

    temp_emhi = jsonize_values(forecast["temperature_emhi"])
    temp_emhi_plus, temp_emhi_minus = split_temperatures(temp_emhi)

    temp_yrno = jsonize_values(forecast["temperature_yrno"])
    temp_yrno_plus, temp_yrno_minus = split_temperatures(temp_yrno)

    temp_plus_dominates = {  # Compares the amount of ~isnans (i.e. isnotnans), i.e. amount of +/- temps.
        "emhi": sum(~np.isnan(temp_emhi_plus)) >= sum(~np.isnan(temp_emhi_minus)),  # True/False
        "yrno": sum(~np.isnan(temp_yrno_plus)) >= sum(~np.isnan(temp_yrno_minus))  # True/False
    }
    
    source.data = dict(
        start=jsonize_values(forecast["start"]),
        temp_emhi=temp_emhi,
        temp_emhi_plus=temp_emhi_plus,
        temp_emhi_minus=temp_emhi_minus,
        precipitation_emhi=jsonize_values(forecast["precipitation_emhi"]),
        temp_yrno=temp_yrno,
        temp_yrno_plus=temp_yrno_plus,
        temp_yrno_minus=temp_yrno_minus,
        precipitation_yrno=jsonize_values(forecast["precipitation_yrno"]),
        symbol_yrno=jsonize_values(forecast["symbol_yrno"]),
        symbol_emhi=jsonize_values(forecast["symbol_emhi"])
    )
    f.title.text = "Ilmaennustus - {}".format(input_city)


def jsonize_values(series) -> list:
    """
    Converts a Pandas series to JSON-compatible list with specific rules for symbol/start and precipitation.
    :param series: pandas series
    :return: list
    """
    pd_series = series.copy()
    if pd_series.name.startswith('symbol'):
        symbol_path = "symbols/{}.png"
        # Add symbol_path only if the symbol is not Null (2/3 of EMHI symbols are Null); otherwise use None
        jsonized_series = pd_series.apply(lambda x: symbol_path.format(x) if pd.notnull(x) else None)
    elif pd_series.name == "start":
        # Convert Pandas datetime objects to Python datetime objects.
        jsonized_series = pd_series.apply(lambda ts: ts.to_pydatetime())
    else:
        if pd_series.name.startswith('precipitation'):
            # Replace 0 precipitation with NaN, otherwise 0-height bars will be shown.
            pd_series.replace([0.0], [float('NaN')], inplace=True)
        # If not symbols or datetimes, use float('NaN') for empty spaces.
        jsonized_series = pd_series.apply(lambda x: x if pd.notnull(x) else float('NaN'))
    return jsonized_series


def split_temperatures(temperatures):
    """
    Returns a list of positive and a list of negative temperatures, where non-relevant temperatures
    have been replaced with float('NaN'). The lists are created bearing in mind, that these temperatures
    will be used as coordinates to draw lines later on. Thus if a temperatures rises from x = <0 to y = >0,
    then x - a negative value - is also stored in positive temperatures, so that the line could still start from x.
    The opposite stands for negative temperatures.
    Temperatures of 0 degrees will be handled as negatives to avoid line duplication in the visualization stage.
    :param temperatures: list_of_temperatures (or a pandas series of temperatures)
    :return: list_of_positive_temperatures, list_of_negative_temperatures
    """
    plus_temps = []
    for i, temp in enumerate(temperatures):
        # If temperature is below 0, but the following temp is above 0, then append the negative value
        # Needed for coordinates of the line.
        if temp < 0 and i < len(temperatures) - 1 and temperatures[i + 1] > 0:
            plus_temps.append(temp)
        # To avoid duplication of lines at 0 degrees, do not store consecutive (>3) 0s (i.e 1, 0, 0, 0, 2)
        # Non-consecutive zero temperatures are stored normally (i.e -1, 0, 2 and -1, 0, 0, 2)
        elif temp == 0 and 0 < i < len(temperatures) - 1 \
                and temperatures[i-1] == 0 and temperatures[i+1] == 0:
            plus_temps.append(float('NaN'))
        # Otherwise use default logic: temperature or float('NaN')
        else:
            plus_temps.append(temp if temp >= 0 else float('NaN'))

    minus_temps = []
    for i, temp in enumerate(temperatures):
        # See above; needed for coordinates of the line.
        if temp > 0 and i < len(temperatures) - 1 and temperatures[i + 1] < 0:
            minus_temps.append(temp)
        else:
            minus_temps.append(temp if temp <= 0 else float('NaN'))

    return plus_temps, minus_temps


def get_precipitation_bar_width() -> float:
    """
    Returns a responsive size to precipitation bars.
    :return: float
    """
    global source
    mindate = min(source.data['start'])
    maxdate = max(source.data['start'])
    return 0.8 * (maxdate - mindate).total_seconds() * 1000 / len(source.data['start'])


def get_line_position_and_color(provider: str):
    """
    Returns list of two dictionaries with line position (source, x, y) and color. The order of dictionaries in
    the returned list is based on their plotting order, i.e. dominate temperatures (i.e. above or below zero).
    If temperatures above zero dominate, the data regarding "minus line" must be plotted first, thus the data
    of "minus line" will be returned first. Result will be used for unpacking values to line figures.
    :param provider: str in ["emhi", "yrno"]
    :return: [{"y": ..., "x": ..., "source": ..., "color": ...}, same]
    """
    global source
    defaults = {"x": "start", "source": source}
    y_and_color_based_on_plus_dominance = {
        True: {"1y": "minus", "1c": "#48AFE8", "2y": "plus", "2c": "firebrick"},  # True if plus dominates
        False: {"1y": "plus", "1c": "firebrick", "2y": "minus", "2c": "#48AFE8"},  # False if plus does not dominate
    }
    vmap = y_and_color_based_on_plus_dominance[temp_plus_dominates[provider]]
    return [{"y": "temp_{}_{}".format(provider, vmap["1y"]), "color": vmap["1c"], **defaults},
            {"y": "temp_{}_{}".format(provider, vmap["2y"]), "color": vmap["2c"], **defaults}]


city_picker = AutocompleteInput(value="Tartu", title="\n",
                                completions=list(CITY_MAP))
city_picker.on_change("value", lambda attr, old, new: update())

source = ColumnDataSource(
    data=dict(
        start=[],  # Python datetime objects
        temp_emhi=[],  # All EMHI temperatures - needed for the positioning of cloud-symbols.
        temp_emhi_plus=[],  # EMHI temperatures above 0.
        temp_emhi_minus=[],  # EMHI temperatures below 0.
        precipitation_emhi=[],
        temp_yrno=[],
        temp_yrno_plus=[],
        temp_yrno_minus=[],
        precipitation_yrno=[],
        symbol_yrno=[],  # Cloud-symbols
        symbol_emhi=[]
    )
)

f = figure(x_axis_type='datetime', plot_width=1300, responsive=True)
update()  # Create the initial (default) plot based on city_picker default values.

# DISABLE TOOLBAR
f.toolbar_location = None
f.toolbar.logo = None
f.toolbar.active_drag = None


# ADD GLYPHS
# EMHI preciptitation vbar + EMHI above 0 (firebrick) line + EMHI below 0 (#48AFE8) line
f.vbar(x="start", top="precipitation_emhi", bottom=0, width=get_precipitation_bar_width(),
       source=source, y_range_name="precip", alpha=0.5, legend="Ilmateenistus")
line_pos_and_color = get_line_position_and_color("emhi")
f.line(**line_pos_and_color[0], legend="Ilmateenistus", line_width=5)
f.line(**line_pos_and_color[1], legend="Ilmateenistus", line_width=5)

# YRNO preciptitation vbar + YRNO above 0 (firebrick) line + YRNO below 0 (#48AFE8) line
f.vbar(x="start", top="precipitation_yrno", bottom=0, width=get_precipitation_bar_width(),
       source=source, y_range_name="precip", alpha=0.5, color="DarkCyan", legend="yr.no")
line_pos_and_color = get_line_position_and_color("yrno")
f.line(**line_pos_and_color[0], legend="yr.no", line_dash="dashed", line_dash_offset=5, line_width=5)
f.line(**line_pos_and_color[1], legend="yr.no", line_dash="dashed", line_dash_offset=5, line_width=5)


# ADD PRECIPITATION LABELS
precipitation_labels_emhi = LabelSet(x="start", y="precipitation_emhi", source=source,
                                     text="precipitation_emhi", level='glyph', text_font_size="0.5em",
                                     x_offset=-5, y_offset=5, render_mode='canvas', y_range_name="precip")
precipitation_labels_yrno = LabelSet(x="start", y="precipitation_yrno", source=source,
                                     text="precipitation_yrno", level='glyph', text_font_size="0.5em",
                                     x_offset=-5, y_offset=5, render_mode='canvas', y_range_name="precip")
f.add_layout(precipitation_labels_emhi)
f.add_layout(precipitation_labels_yrno)


# ADD SYMBOLS (CLOUDINESS ETC), i.e. LABELS
f.image_url(url="symbol_yrno", x="start", y="temp_yrno", w=None, h=None, anchor="bottom_center", source=source,
            global_alpha=0.5)
f.image_url(url="symbol_emhi", x="start", y="temp_emhi", w=None, h=None, anchor="top_center", source=source)


# AXIS ETC
# DATETIME (X) FORMAT
f.xaxis.formatter = DatetimeTickFormatter(
    minutes=["%H"], hours=["%H"], days=["%H"], months=["%H"], years=["%H"],
)
f.xaxis[0].ticker.desired_num_ticks = 30  # 10 ~ 6h/tick, 30 ~ 2h/tick; 40 ~ h/tick;

# TEMPERATURE (Y1 - LEFT)
min_temp = np.nanmin(city.union[["temperature_emhi", "temperature_yrno"]])
max_temp = np.nanmax(city.union[["temperature_emhi", "temperature_yrno"]])

f.y_range = Range1d(start=min_temp - 4, end=max_temp + 4)
f.yaxis[0].ticker = SingleIntervalTicker(interval=1)
f.yaxis[0].ticker.num_minor_ticks = 2

# PRECIPITATION (Y2 - RIGHT)
max_precipitation = np.nanmax(city.union[["precipitation_emhi", "precipitation_yrno"]])  # Ignore "NaN" getting max
max_precipitation = (int(max_precipitation) + 2) if (int(max_precipitation) + 2) > 4 else 4  # Standardize result

f.extra_y_ranges = {"precip": Range1d(start=0, end=max_precipitation)}
f.add_layout(LinearAxis(y_range_name="precip"), "right")

# DAY SEPARATORS (MIDNIGHT LINES)
midnight_time_and_label_dict = midnights.get(source.data["start"])
for midnight_time, midnight_label in midnight_time_and_label_dict.items():
    midnight_span = Span(location=midnight_time, dimension='height',
                         line_color='DimGray', line_width=2, level="underlay")
    midnight_label = Label(x=midnight_time, y=max_temp + 4, text=midnight_label,
                           x_offset=5, y_offset=-20, render_mode='canvas', text_font_size="10pt")
    f.add_layout(midnight_span)  # Add line
    f.add_layout(midnight_label)  # Add title/label to the line


# LEGEND LOCATION
f.legend.location = "top_left"


# DIVS BELOW PLOT (DATA SOURCE + TEXT INPUT BOX)
css_style = 'style="text-decoration: none;color: DimGray; font-size: calc(7px + .5vw);"'
weather_notice_text = '<link rel="stylesheet" href="https://code.jquery.com/ui/1.10.4/themes/smoothness/' \
                      'jquery-ui.min.css" type="text/css">' \
                      '<a href="{0.yrno_url}" {1}>' \
                      'Ilmaprognoos Yr-lt, mille on loonud Norra Meteoroloogia Instituut ja NRK</a>' \
                      '<br>' \
                      '<a href="{0.emhi_url}" {1}>' \
                      'Ilmaprognoos Riigi Ilmateenistuselt'.format(city, css_style)

weather_source = Div(text=weather_notice_text)

# CREATE LAYOUT
plot_layout = layout([
    [f],
    [weather_source, city_picker]
], responsive=True, width=1300
)

# PUSH TO SERVER AND ADD TITLE
curdoc().add_root(plot_layout)
curdoc().title = "Ilmaennustus"
