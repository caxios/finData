import re

filepath = r"c:\Users\mrsim\finData\fetch_data.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    "from findata.sec.company_data import get_company_data, TickerNotFound, SECRateLimit",
    "PROJECT_ROOT = Path(__file__).resolve().parent\nfrom findata.sec.company_data import get_company_data, TickerNotFound, SECRateLimit\nfrom findata.core.config import GENERAL_DATA_DIR"
)

content = content.replace("from OpenDart import (", "from findata.dart import (")
content = content.replace("from OpenDart.utils.get_companies import COMPANY_CODES", "from findata.dart.utils.get_companies import COMPANY_CODES")

# Update US data save directory
content = content.replace(
    'data_dir = PROJECT_ROOT / "data" / "us_company_data"',
    'data_dir = GENERAL_DATA_DIR / "us_company_data"'
)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
