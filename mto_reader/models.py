from dataclasses import dataclass

import pandas as pd


@dataclass
class ExtractedTable:
    page_number: int
    dataframe: pd.DataFrame
