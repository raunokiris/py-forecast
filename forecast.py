from bokeh.plotting import figure, ColumnDataSource
from bokeh.models import DatetimeTickFormatter, Range1d, LinearAxis, \
    SingleIntervalTicker, LabelSet, Label, Span
from bokeh.models.widgets import Div, AutocompleteInput
from bokeh.io import curdoc
from bokeh.layouts import layout

import numpy as np
import pandas as pd
from city_forecast import City
import midnights

from default_data import CITY_MAP


def get_precipitation_bar_width() -> float:
    """
    Returns a responsive size to precipitation bars.
    :return: float
    """
    global source
    mindate = min(source.data['start'])
    maxdate = max(source.data['start'])
    return 0.8 * (maxdate - mindate).total_seconds() * 1000 / len(source.data['start'])


def jsonize_to_list(series) -> list:
    """
    Converts a Pandas series to JSON-compatible list with specific rules for symbol/start and precipitation.
    :param series: pandas series
    :return: list
    """
    pd_series = series.copy()
    if pd_series.name.startswith('symbol'):
        symbol_path = "symbols/{}.png"
        pd_series = pd_series.apply(lambda x: symbol_path.format(x) if pd.notnull(x) else None)
        jsonized_list = [el for el in pd_series.where((pd.notnull(pd_series)), None).tolist()]
    elif pd_series.name == "start":
        jsonized_list = [ts.to_pydatetime() for ts in pd_series.tolist()]
    else:
        if pd_series.name.startswith('precipitation'):
            pd_series.replace([0.0], [float('NaN')], inplace=True)
        jsonized_list = [el if el is not None else float('NaN') for el in pd_series.where((pd.notnull(pd_series)),
                                                                                          None).tolist()]
    return jsonized_list


def update() -> None:
    """
    Updates the data source based on the city_picker (i.e. user input) value and changes plot title.
    :return: None
    """
    global source
    global city
    input_city = city_picker.value
    city = City(input_city)
    forecast = city.union

    source.data = dict(
        start=jsonize_to_list(forecast["start"]),
        temp_emhi=jsonize_to_list(forecast["temperature_emhi"]),
        precipitation_emhi=jsonize_to_list(forecast["precipitation_emhi"]),
        temp_yrno=jsonize_to_list(forecast["temperature_yrno"]),
        precipitation_yrno=jsonize_to_list(forecast["precipitation_yrno"]),
        symbol_yrno=jsonize_to_list(forecast["symbol_yrno"]),
        symbol_emhi=jsonize_to_list(forecast["symbol_emhi"])
    )
    f.title.text = "Ilmaennustus - {}".format(input_city)


city_picker = AutocompleteInput(value="Tartu", title="\n",
                                completions=list(CITY_MAP))
city_picker.on_change("value", lambda attr, old, new: update())

source = ColumnDataSource(
    data=dict(
        start=[],
        temp_emhi=[],
        precipitation_emhi=[],
        temp_yrno=[],
        precipitation_yrno=[],
        symbol_yrno=[],
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
f.vbar(x="start", top="precipitation_emhi", bottom=0, width=get_precipitation_bar_width(),
       source=source, y_range_name="precip", alpha=0.5, legend="Ilmateenistus")
f.line(x="start", y="temp_emhi", source=source, line_width=5, color="firebrick", legend="Ilmateenistus")

f.vbar(x="start", top="precipitation_yrno", bottom=0, width=get_precipitation_bar_width(),
       source=source, y_range_name="precip", alpha=0.5,
       color="DarkCyan", legend="yr.no")
f.line(x="start", y="temp_yrno", source=source, line_dash="dashed", line_dash_offset=5,
       line_width=5, color="firebrick", legend="yr.no")

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
f.y_range = Range1d(start=min_temp - 4,
                    end=max_temp + 4)
f.yaxis[0].ticker = SingleIntervalTicker(interval=1)
f.yaxis[0].ticker.num_minor_ticks = 2

# PRECIPITATION (Y2 - RIGHT)
max_precipitation = np.nanmax(city.union[["precipitation_emhi", "precipitation_yrno"]])  # Ignore "NaN" getting max
max_precipitation = (int(max_precipitation) + 2) if (int(max_precipitation) + 2) > 4 else 4  # Standardize result

f.extra_y_ranges = {"precip": Range1d(start=0, end=max_precipitation)}
f.add_layout(LinearAxis(y_range_name="precip"), "right")

# DAY SEPARATORS (MIDNIGHT LINES)
MIDNIGHTS = midnights.get(source.data["start"])
for midnight in MIDNIGHTS:
    midnight_span = Span(location=midnight, dimension='height',
                         line_color='DimGray', line_width=2, level="underlay")
    midnight_label = Label(x=midnight, y=max_temp + 4, text=MIDNIGHTS[midnight],
                           x_offset=5, y_offset=-20, render_mode='canvas', text_font_size="10pt")
    f.add_layout(midnight_span)  # Add line
    f.add_layout(midnight_label)  # Add title/label to the line

# LEGEND LOCATION
f.legend.location = "top_left"


# DIVS BELOW PLOT (DATA SOURCE + TEXT INPUT BOX)
css_style = 'style="text-decoration: none;color: DimGray; font-size: calc(7px + .5vw);"'
weather_notice_text = '<link rel="stylesheet" href="https://code.jquery.com/ui/1.10.4/themes/smoothness/' \
                      'jquery-ui.min.css" type="text/css">' \
                      '<a href="{0}" {1}>Ilmaprognoos Yr-lt, mille on loonud Norra Meteoroloogia Instituut ja NRK</a>' \
                      '<br>' \
                      '<a href="{2}" {1}>Ilmaprognoos Riigi Ilmateenistuselt'.format(city.yrno_url,
                                                                                     css_style,
                                                                                     city.emhi_url
                                                                                     )
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
