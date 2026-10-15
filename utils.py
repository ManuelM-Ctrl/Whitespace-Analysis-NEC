import re

CODE_RE = re.compile(r"^(.*?)\s*\(([^)]+)\)$")
EUR_TO_USD = 1.16


def strip_code(label):
    if not isinstance(label, str):
        return label
    m = CODE_RE.match(label.strip())
    return m.group(1).strip() if m else label.strip()
