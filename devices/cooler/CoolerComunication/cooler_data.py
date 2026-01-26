import time
import pandas as pd
from typing import Optional, Union


class CoolerData:
    """
    Skaito 'axis_controller.get_cooler_data()' eilutę ir paverčia ją į DataFrame.
    Tikimasi formato, panašaus į:
    '#Readings: 21.4 21.2 21.1 123mA 10% 20% APC 50% 3.30V'
    """

    def __init__(self, axis_controller, read_delay_s: float = 0.1):
        self.axis_controller = axis_controller
        self.read_delay_s = read_delay_s
        self.last_raw: Optional[str] = None

    def get_dataframe(self) -> pd.DataFrame:
        """
        Perskaito iš valdiklio ir grąžina vienos eilutės DataFrame.
        """
        raw = self._read_raw_line()
        return self._parse_to_df(raw)

    def _read_raw_line(self) -> str:
        """
        Kvieskite kontrolerį ir grąžinkite dekoduotą eilutę (utf-8).
        """
        data: Union[str, bytes, bytearray] = self.axis_controller.get_cooler_data()
        print(data)
        if isinstance(data, (bytes, bytearray)):
            decoded = data.decode("utf-8", errors="ignore")
        else:
            decoded = str(data)

        decoded = decoded.strip()
        self.last_raw = decoded
        return decoded

    def _parse_to_df(self, text: Optional[str] = None) -> pd.DataFrame:
        if text is None:
            if self.last_raw is None:
                raise ValueError("Nėra ką parsinėti: neperskaityta jokia eilutė.")
            text = self.last_raw

        if text.startswith("#Readings:"):
            text = text.replace("#Readings:", "", 1)

        tokens = text.replace(",", " ").split()
        if len(tokens) < 9:
            raise ValueError(
                f"Laukų per mažai ({len(tokens)}): tikimasi bent 9. Gauta: {tokens}"
            )

        t1, t2, t3, cur, load1, load2, apc_tag, apc_lvl, volt = tokens[:9]

        def _float(x: str) -> float:
            return float(x)

        def _strip_suffix_and_float(x: str, suffix: str) -> float:
            if x.endswith(suffix):
                x = x[: -len(suffix)]
            return float(x)

        def _percent_to_float(x: str) -> float:
            if x.endswith("%"):
                x = x[:-1]
            return float(x)

        data = [
            _float(t1),                           
            _float(t2),                           
            _float(t3),                           
            _strip_suffix_and_float(cur, "mA"),   
            _percent_to_float(load1),             
            _percent_to_float(load2),             
            apc_tag.rstrip(":"),                  
            _percent_to_float(apc_lvl),           
            _strip_suffix_and_float(volt, "V"),   
        ]

        columns = [
            "Temp1_C", "Temp2_C", "Temp3_C",
            "Current_mA", "Load1_pct", "Load2_pct",
            "APC_tag", "APC_level_pct", "Voltage_V"
        ]

        return pd.DataFrame([data], columns=columns)
