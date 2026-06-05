import os
import re

def refactor_sec_db(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Add config import
    if "from findata.core.config import " not in content:
        if "import os" in content:
            content = content.replace("import os", "import os\nfrom findata.core.config import SEC_DB_DIR, DART_CACHE_DIR")
        else:
            content = "from findata.core.config import SEC_DB_DIR, DART_CACHE_DIR\n" + content

    content = re.sub(r'os\.path\.join\([^,]*, "db", "([^"]+)"\)', r'os.path.join(SEC_DB_DIR, "\1")', content)
    content = re.sub(r'os\.path\.join\(_DB_DIR, "([^"]+)"\)', r'os.path.join(SEC_DB_DIR, "\1")', content)
    content = re.sub(r'os\.path\.join\(DB_DIR, "([^"]+)"\)', r'os.path.join(SEC_DB_DIR, "\1")', content)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

for root, _, files in os.walk(r"c:\Users\mrsim\finData\findata\sec"):
    for file in files:
        if file.endswith(".py"):
            refactor_sec_db(os.path.join(root, file))

def refactor_dart_cache(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace auto_corp_cache.json path
    if "_CACHE_FILE =" in content:
        content = content.replace("Path(__file__).resolve().parent.parent / \"auto_corp_cache.json\"", "DART_CACHE_DIR / \"auto_corp_cache.json\"")
        content = "from findata.core.config import DART_CACHE_DIR\n" + content

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

for root, _, files in os.walk(r"c:\Users\mrsim\finData\findata\dart"):
    for file in files:
        if file.endswith(".py"):
            refactor_dart_cache(os.path.join(root, file))
