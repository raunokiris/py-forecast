import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import requests
import requests_cache
import json
from datetime import datetime
from default_data import CITY_MAP, ELEMENTS_MAP

requests_cache.install_cache('forecast_cache', backend='memory', expire_after=3600)


class City(object):
    def __init__(self, name: str):
        self.name = name  # str
        self.emhi_url = self._get_city_url("emhi")  # str
        self.yrno_url = self._get_city_url("yrno")  # str
        self.sunrise = None  # datetime
        self.sunset = None  # datetime
        self.yrno = self.get_yrnodf()  # pd.DataFrame NB! Also sets sunrise and sunset TODO refactor
        self.emhi = self.get_emhidf()  # pd.DataFrame
        self.union = self.get_uniondf()  # pd.DataFrame (.yrno + .emhi)

    def _get_city_code(self, forecast_provider: str) -> str:
        """
        Returns the city code forecast_provider.
        :param forecast_provider: str in ["emhi", "yrno"]
        :return: str, city code for given provider, i.e. if the .name is "Tallinn", then
                - forecast_provider="emhi" returns "784"
                - forecast_provider="yrno" returns "Harjumaa/Tallinn"
        """
        return CITY_MAP[self.name.title()][forecast_provider]

    def _get_city_url(self, forecast_provider: str) -> str:
        """
        Returns an URL to the forecast providers webpage for the current city.
        :param forecast_provider: str in ["emhi", "yrno"]
        :return: str, i.e. if .name is Tallinn,
                    - "emhi" returns "http://www.ilmateenistus.ee/asukoha-prognoos/?id=784",
                    - "yrno" returns "https://www.yr.no/place/Estonia/Harjumaa/Tallinn"
        """
        code = self._get_city_code(forecast_provider)
        if forecast_provider == "emhi":
            url = r"http://www.ilmateenistus.ee/asukoha-prognoos/?id={}".format(code)
        elif forecast_provider == "yrno":
            url = r"https://www.yr.no/place/Estonia/{}".format(code)
        else:
            url = None  # TODO
        return url

    def get_emhidf(self) -> pd.DataFrame:
        """
        Returns emhi (ilmateenistus.ee) 2-day weather forecast as a dataframe.
        :return: pd.DataFrame[["end", "precipitation", "pressure", "start", "symbol",
                               "temperature", "windDirection", "windSpeed"]]
        """
        city_code = self._get_city_code("emhi")
        query_base = r"http://www.ilmateenistus.ee/wp-content/themes/emhi2013/meteogram.php?locationId={}"
        query_url = query_base.format(city_code)
        emhi_data = requests.get(query_url).text.replace("callback(", "").replace(");", "")
        emhi_json = json.loads(emhi_data)["forecast"]["tabular"]["time"]
        data = [self._return_emhi_hour_data(hour) for hour in emhi_json]
        df = pd.DataFrame(data)
        df = df.rename(columns={'phenomen': 'symbol'})  # rename/harmonize emhi 'phenomen' to yrno 'symbol'.
        df = self.convert_df_dtypes(df)
        df['symbol'] = df.apply(self._convert_emhi_symbol, axis=1)  # emhi
        return df

    @staticmethod
    def _return_emhi_hour_data(hour: dict) -> dict:
        """
        Returns a dict of emhi hourly weather data.
        :param hour: (json) dict
        :return: dict; keys are list(ELEMENTS_MAP["emhi"])
        """
        hour_data = {
            "start": hour["@attributes"]["from"],
            "end": hour["@attributes"]["to"]
        }
        for element in hour:
            if element in ELEMENTS_MAP["emhi"]:
                hour_data[element] = hour[element]["@attributes"][ELEMENTS_MAP["emhi"][element]]
        return hour_data

    def _convert_emhi_symbol(self, row) -> str:
        """
        Converts emhi phenomens (cloud data) to yrno symbol codes and - when necessary - converts them to nighttime.
        :param row: pd.DataFrame row
        :return: str, yrno symbol code
        """
        if row.symbol is not None and row.symbol != "":
            symbol = ELEMENTS_MAP["emhi_symbols"][row.symbol]
            symbol = self._convert_emhi_symbol_daynight(row.start, symbol)
            return symbol
        return np.nan

    def _convert_emhi_symbol_daynight(self, start_date: pd.tslib.Timestamp, symbol: str) -> str:
        if "d" in symbol and not self._is_daytime(start_date):
            symbol = symbol.replace("d", "n")
        return symbol

    def _is_daytime(self, check_datetime: pd.tslib.Timestamp) -> bool:
        """
        Returns if check_datetime is in the daytime. Relies on .sunrise and sunset.
        :param check_datetime: pd.tslib.Timestamp (i.e. pandas dt64 object)
        :return: bool
        """
        t = check_datetime.to_pydatetime()  # Convert pd dt64 to python datetime object
        # .sunrise and .sunset are based on the first day of the forecast.
        # As forecast also contains future dates and we don't have their sunrise/sunset time,
        # we'll just use the same times from first day (i.e hours and seconds from self.sunrise and self.sunset)
        sunrise = t.replace(hour=self.sunrise.hour, second=self.sunrise.second)
        sunset = t.replace(hour=self.sunset.hour, second=self.sunset.second)
        return sunrise <= t <= sunset

    def get_yrnodf(self):
        """
        Returns yrno (yr.no) 2-day weather forecast as a dataframe.
        :return: pd.DataFrame[["end", "precipitation", "pressure", "start", "symbol",
                               "temperature", "windDirection", "windSpeed"]]
        """
        city_code = self._get_city_code("yrno")
        query_url = r"https://www.yr.no/place/Estonia/{}/forecast_hour_by_hour.xml".format(city_code)
        tree = ET.fromstring(requests.get(query_url).content)
        self.sunrise = self.str_to_dt(tree.find("sun").attrib["rise"])
        self.sunset = self.str_to_dt(tree.find("sun").attrib["set"])
        data = [self._return_yrno_hour_data(hour) for hour in tree.findall("forecast/tabular/time")]
        df = pd.DataFrame(data)
        df = self.convert_df_dtypes(df)
        return df

    @staticmethod
    def str_to_dt(date_string: str) -> datetime:
        return datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def _return_yrno_hour_data(hour: ET.Element) -> dict:
        """
        Returns a dict of yrno hourly weather data.
        :param hour: xml.etree.ElementTree.Element
        :return: dict; keys are list(ELEMENTS_MAP["yrno"])
        """
        hour_data = {
            "start": hour.attrib["from"],
            "end": hour.attrib["to"]
        }
        for element in hour.iter():
            el_tag = element.tag
            if el_tag in ELEMENTS_MAP["yrno"]:
                element_name = el_tag
                element_value = element.attrib[ELEMENTS_MAP["yrno"][el_tag]]
                hour_data[element_name] = element_value
        return hour_data

    @staticmethod
    def convert_df_dtypes(df: pd.DataFrame) -> pd.DataFrame:
        """
        Converts dataframe columns to specific datatypes. Columns pressure, temperature, windDirection,
        windSpeed and precipitation are converted to float; columns start and end are converted to dt64
        :param df: pd.DataFrame
        :return: pd.DataFrame
        """
        columns_to_float = ['pressure', 'temperature', 'windDirection', 'windSpeed', 'precipitation']
        df[columns_to_float] = df[columns_to_float].astype(float, errors='ignore')
        df['start'] = pd.to_datetime(df['start'], format='%Y-%m-%dT%H:%M:%S', errors='coerce')
        df['end'] = pd.to_datetime(df['end'], format='%Y-%m-%dT%H:%M:%S', errors='coerce')
        return df

    def get_uniondf(self) -> pd.DataFrame:
        """
        Returns .emhi and .yrno outer-joined dataframe.
        :return: pd.DataFrame
        """
        df = pd.merge(self.emhi, self.yrno, how="outer", on=["start", "end"], suffixes=["_emhi", "_yrno"])
        return df
