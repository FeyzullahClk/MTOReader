from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ExtractedTable:
    page_number: int
    dataframe: pd.DataFrame
    is_rigging_table: bool = field(default=False)
    table_title: str = field(default="")
    total_weight: str = field(default="")
