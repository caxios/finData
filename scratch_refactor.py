import os

def replace_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    replacements = {
        "from agents": "from findata.sec.agents",
        "import agents": "import findata.sec.agents as agents",
        "from form4": "from findata.sec.utils.form4",
        "import form4": "import findata.sec.utils.form4 as form4",
        "from sec_10kq": "from findata.sec.utils.sec_10kq",
        "import sec_10kq": "import findata.sec.utils.sec_10kq as sec_10kq",
        "from company_facts": "from findata.sec.company_facts",
        "from const import": "from findata.sec.const import",
        "from OpenDart": "from findata.dart",
        "import OpenDart": "import findata.dart as OpenDart",
    }
    
    original = content
    for old, new in replacements.items():
        content = content.replace(old, new)
        
    if original != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")

for root, _, files in os.walk(r"c:\Users\mrsim\finData\findata"):
    for file in files:
        if file.endswith(".py"):
            replace_in_file(os.path.join(root, file))
