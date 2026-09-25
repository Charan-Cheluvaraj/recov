import re
from typing import List, Dict, Any, Union
from .pii_detection import extract_printable_text

SENSITIVE_KEYWORD_REGISTRY: tuple[tuple[str, str], ...] = (
    (r"\bconfidential\b", "Confidentiality Indicator"),
    (r"\brestricted\b", "Restricted Access Marker"),
    (r"\binternal use only\b", "Internal Distribution Marker"),
    (r"\bclassified\b", "Classification Marker"),
    (r"\btop secret\b", "High-Classification Marker"),
    (r"\bsecret\b", "Secret Keyword"),
    (r"\bfinancial statement\b", "Financial Document Indicator"),
    (r"\bbank statement\b", "Banking Record Indicator"),
    (r"\bsalary\b", "Compensation / Payroll Record"),
    (r"\btax return\b", "Tax Filing Indicator"),
    (r"\bincome tax\b", "Income Tax Reference"),
    (r"\baudit report\b", "Audit Findings Indicator"),
    (r"\bprivileged\b", "Privileged Information Marker"),
    (r"\battorney[- ]client\b", "Legal Privilege Marker"),
    (r"\bssn\b", "Social Security Keyword"),
    (r"\baadhaar\b", "Aadhaar Card Reference"),
    (r"\bpan card\b", "PAN Card Reference"),
    (r"\bcredentials?\b", "Authentication Credentials Keyword"),
    (r"\bdo not disclose\b", "Non-Disclosure Instruction"),
)


def detect_keywords(data: Union[str, bytes], rules_path: str = "") -> List[Dict[str, Any]]:
    """
    Scan text or candidate bytes for sensitive organizational, legal, and financial keywords.
    
    Returns:
        List of match dictionaries containing category='sensitive_keyword', pattern_name, match_snippet, occurrence_count.
    """
    text = extract_printable_text(data)
    if not text:
        return []

    results: List[Dict[str, Any]] = []

    for pattern, name in SENSITIVE_KEYWORD_REGISTRY:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            results.append({
                "category": "sensitive_keyword",
                "pattern_name": name,
                "match_snippet": f"Keyword '{matches[0]}' matched ({len(matches)}x)",
                "occurrence_count": len(matches),
            })

    return results
