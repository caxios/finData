import os

# SEC requires a descriptive User-Agent ("Sample Company AdminContact@email.com").
# Override per-deployment with FINDATA_SEC_USER_AGENT; this is the single source
# of truth for the SEC User-Agent across the project.
_DEFAULT_SEC_USER_AGENT = "mrsimple1015 mrsimple1015@gmail.com"
SEC_USER_AGENT = os.environ.get("FINDATA_SEC_USER_AGENT", _DEFAULT_SEC_USER_AGENT)

HEADERS = {"User-Agent": SEC_USER_AGENT}

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")