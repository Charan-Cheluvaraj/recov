import re
from typing import List, Dict, Any, Union


def extract_printable_text(data: Union[str, bytes]) -> str:
    """Extract decodable or printable text strings from candidate bytes or text string."""
    if isinstance(data, str):
        return data
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1")
        except Exception:
            # Extract printable runs of ASCII characters (useful for binary candidates)
            matches = re.findall(r"[A-Za-z0-9_\-\.\:\/\@\=\+\, ]{4,}", data.decode("ascii", errors="ignore"))
            return " ".join(matches)


def _mask_aadhaar(match_text: str) -> str:
    digits = re.sub(r"\D", "", match_text)
    last4 = digits[-4:] if len(digits) >= 4 else "XXXX"
    return f"XXXX-XXXX-{last4}"


def _mask_pan(match_text: str) -> str:
    clean = match_text.strip().upper()
    if len(clean) == 10:
        return f"{clean[0]}****{clean[-4:]}"
    return "X****XXXX"


def _mask_email(match_text: str) -> str:
    parts = match_text.split("@")
    if len(parts) == 2:
        user, domain = parts
        masked_user = (user[0] + "***") if user else "***"
        return f"{masked_user}@{domain}"
    return "***@***"


def _mask_phone(match_text: str) -> str:
    digits = re.sub(r"\D", "", match_text)
    last4 = digits[-4:] if len(digits) >= 4 else "XXXX"
    return f"+91-XXXXX-{last4}" if len(digits) >= 10 else f"XXX-{last4}"


def _mask_card(match_text: str) -> str:
    digits = re.sub(r"\D", "", match_text)
    last4 = digits[-4:] if len(digits) >= 4 else "XXXX"
    return f"****-****-****-{last4}"


def detect_pii(text_or_bytes: Union[str, bytes]) -> List[Dict[str, Any]]:
    """
    Detect potentially sensitive identifiers and credentials using deterministic regex patterns.
    
    Returns:
        List of match dictionaries containing category, pattern_name, match_snippet, and occurrence_count.
    """
    text = extract_printable_text(text_or_bytes)
    if not text:
        return []

    results: List[Dict[str, Any]] = []

    # 1. PAN-like Pattern: 5 letters, 4 digits, 1 letter
    pan_matches = re.findall(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", text)
    if pan_matches:
        for val in set(pan_matches):
            results.append({
                "category": "pan",
                "pattern_name": "Potential PAN Pattern",
                "match_snippet": _mask_pan(val),
                "occurrence_count": pan_matches.count(val),
            })

    # 2. Aadhaar-like Pattern: 12 digits, often 4-4-4 formatted
    aadhaar_matches = re.findall(r"\b[2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}\b", text)
    if aadhaar_matches:
        # Exclude common card numbers if already overlapping
        for val in set(aadhaar_matches):
            results.append({
                "category": "aadhaar",
                "pattern_name": "Potential Aadhaar Pattern",
                "match_snippet": _mask_aadhaar(val),
                "occurrence_count": aadhaar_matches.count(val),
            })

    # 3. Email Address Pattern
    email_matches = re.findall(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b", text)
    if email_matches:
        for val in set(email_matches):
            results.append({
                "category": "email",
                "pattern_name": "Email Address Pattern",
                "match_snippet": _mask_email(val),
                "occurrence_count": email_matches.count(val),
            })

    # 4. Phone Number Pattern: 10 digits starting 6-9 (optional +91) or international
    phone_matches = re.findall(r"(?:\+91[\-\s]?)?[6-9]\d{9}\b", text)
    if phone_matches:
        for val in set(phone_matches):
            # Avoid overlapping with Aadhaar matches
            clean_digits = re.sub(r"\D", "", val)
            if len(clean_digits) in (10, 12):
                results.append({
                    "category": "phone",
                    "pattern_name": "Phone Number Pattern",
                    "match_snippet": _mask_phone(val),
                    "occurrence_count": phone_matches.count(val),
                })

    # 5. Credit/Debit Card-like Pattern: 16 digits formatted 4-4-4-4
    card_matches = re.findall(r"\b(?:\d{4}[\-\s]){3}\d{4}\b", text)
    if card_matches:
        for val in set(card_matches):
            results.append({
                "category": "credit_card",
                "pattern_name": "Potential Payment Card Pattern",
                "match_snippet": _mask_card(val),
                "occurrence_count": card_matches.count(val),
            })

    # 6. Credentials & API Keys Patterns
    cred_patterns = [
        (r"(?i)\b(?:api[_-]?key|apikey|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{16,})['\"]?", "Potential API Key / Secret"),
        (r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"\\;]{6,})['\"]?", "Potential Password String"),
        (r"(?i)bearer\s+([A-Za-z0-9_\-\.]{20,})", "Potential Bearer Token"),
        (r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----", "Private Key Header"),
    ]
    for pattern, name in cred_patterns:
        found = re.findall(pattern, text)
        if found:
            results.append({
                "category": "credential",
                "pattern_name": name,
                "match_snippet": f"{name} detected (masked for security)",
                "occurrence_count": len(found),
            })

    # 7. URLs
    url_matches = re.findall(r"\bhttps?://[^\s<>\"']+|www\.[^\s<>\"']+\b", text)
    if url_matches:
        for val in set(url_matches[:5]):  # Cap at top 5 distinct URLs
            snippet = val[:40] + "..." if len(val) > 40 else val
            results.append({
                "category": "url",
                "pattern_name": "URL Reference",
                "match_snippet": snippet,
                "occurrence_count": url_matches.count(val),
            })

    return results
