from typing import List, Dict, Any, Union
from models.sensitivity import SensitivityLevel, SensitivityMatch, SensitivityAssessment
from .pii_detection import detect_pii
from .keyword_detection import detect_keywords


def determine_sensitivity_level(categories: List[str], matches: List[Dict[str, Any]]) -> SensitivityLevel:
    """
    Determine deterministic sensitivity level based on detected pattern categories.
    
    Rules:
        - HIGH:
            * Credential or API key patterns detected
            * Payment/credit card patterns detected
            * Multiple government ID patterns (e.g., Aadhaar + PAN)
            * Government ID pattern + 2 or more other PII categories
            * 4 or more distinct sensitive categories
        - MEDIUM:
            * Single Aadhaar or PAN pattern detected
            * Multiple contact categories (e.g., email + phone)
            * Sensitive keywords accompanied by contact PII
            * 3 or more sensitive keywords
        - LOW:
            * Single contact pattern (email, phone, or URL only)
            * 1-2 sensitive keywords alone without PII
        - NONE:
            * Zero sensitive patterns or keywords detected
    """
    if not categories or not matches:
        return SensitivityLevel.NONE

    cat_set = set(categories)

    # High-risk conditions
    if "credential" in cat_set or "credit_card" in cat_set:
        return SensitivityLevel.HIGH
    if "aadhaar" in cat_set and "pan" in cat_set:
        return SensitivityLevel.HIGH
    if ("aadhaar" in cat_set or "pan" in cat_set) and len(cat_set - {"aadhaar", "pan"}) >= 2:
        return SensitivityLevel.HIGH
    if len(cat_set) >= 4:
        return SensitivityLevel.HIGH

    # Medium-risk conditions
    if "aadhaar" in cat_set or "pan" in cat_set:
        return SensitivityLevel.MEDIUM
    if "email" in cat_set and "phone" in cat_set:
        return SensitivityLevel.MEDIUM
    if "sensitive_keyword" in cat_set and len(cat_set) > 1:
        return SensitivityLevel.MEDIUM

    keyword_count = sum(m.get("occurrence_count", 1) for m in matches if m.get("category") == "sensitive_keyword")
    if keyword_count >= 3:
        return SensitivityLevel.MEDIUM

    # Low-risk condition (general web/contact info or isolated keywords)
    return SensitivityLevel.LOW


def generate_sensitivity_explanation(
    level: SensitivityLevel,
    categories: List[str],
    match_count: int,
) -> str:
    """
    Generate an objective, factual explanation without asserting real identity or using LLMs.
    """
    if level == SensitivityLevel.NONE or match_count == 0:
        return "No sensitive patterns or keywords detected in recovered candidate content. Classified as NONE."

    cat_str = ", ".join(sorted(categories))
    cat_word = "category" if len(categories) == 1 else "categories"
    
    if level == SensitivityLevel.HIGH:
        return (
            f"High sensitivity classification: Candidate contains {match_count} potential sensitive pattern match(es) "
            f"across {len(categories)} {cat_word} ({cat_str}), indicating potential high-risk identifiers or credentials."
        )
    elif level == SensitivityLevel.MEDIUM:
        return (
            f"Medium sensitivity classification: Candidate contains {match_count} potential sensitive pattern match(es) "
            f"across {len(categories)} {cat_word} ({cat_str})."
        )
    else:
        return (
            f"Low sensitivity classification: Candidate contains {match_count} general identifier pattern match(es) "
            f"across {len(categories)} {cat_word} ({cat_str})."
        )


def analyze_sensitivity(data: Union[str, bytes], candidate_id: str = "unknown") -> SensitivityAssessment:
    """
    Aggregate sensitivity analysis combining PII pattern detection and sensitive keyword scanning.
    
    Returns:
        Deterministic SensitivityAssessment model.
    """
    pii_matches = detect_pii(data)
    keyword_matches = detect_keywords(data)
    all_raw_matches = pii_matches + keyword_matches

    # Deduplicate categories and calculate total match count
    categories = sorted(list({m["category"] for m in all_raw_matches}))
    match_count = sum(m.get("occurrence_count", 1) for m in all_raw_matches)

    level = determine_sensitivity_level(categories, all_raw_matches)
    explanation = generate_sensitivity_explanation(level, categories, match_count)

    structured_matches = [
        SensitivityMatch(
            category=m["category"],
            pattern_name=m["pattern_name"],
            match_snippet=m["match_snippet"],
            occurrence_count=m.get("occurrence_count", 1),
        )
        for m in all_raw_matches
    ]

    return SensitivityAssessment(
        candidate_id=candidate_id,
        sensitivity_level=level,
        detected_categories=categories,
        matches=structured_matches,
        match_count=match_count,
        explanation=explanation,
    )
