import re
from datetime import datetime

EPOCHS = [2020, 2000, 2010, 1990]

DEFINITE_CLASSES = [
    "built_up",
    "agriculture",
    "natural_vegetation",
    "water",
    "bare_sparse",
    "other"
]

ABSTAIN_CLASSES = [
    "uncertain",
    "ambiguous",
    "unavailable"
]

ALL_CLASSES = DEFINITE_CLASSES + ABSTAIN_CLASSES

SHARE_BINS = [">=75", "50-75", "<50"]

CONFIDENCE_LEVELS = [1, 2, 3]

SOURCES_OK = [
    "GEP_historical",
    "Landsat_context",
    "field",
    "Sentinel2_context",
    "other_vhr"
]

STATUS_OPTIONS = ["done", "unavailable", "skipped", ""]

DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_epoch_annotation(epoch, data):
    """
    Validates annotation fields for a specific epoch.
    Returns (is_valid, list_of_errors, list_of_warnings).
    """
    errors = []
    warnings = []

    status = data.get("status", "")
    if status not in STATUS_OPTIONS:
        errors.append(f"Invalid status '{status}' for epoch {epoch}. Allowed: {STATUS_OPTIONS}")
        return False, errors, warnings

    if status == "skipped" or status == "":
        # Skipped or empty
        dom = data.get("dominant_class", "")
        if dom:
            errors.append(f"Epoch {epoch} is marked as '{status or 'empty'}', but dominant_class '{dom}' was provided.")
        return len(errors) == 0, errors, warnings

    if status == "unavailable":
        dom = data.get("dominant_class", "")
        if dom and dom != "unavailable":
            errors.append(f"Epoch {epoch} has status 'unavailable', but dominant_class is '{dom}'. Must be 'unavailable' or empty.")
        src = data.get("imagery_source", "")
        if not src:
            warnings.append(f"Epoch {epoch} marked 'unavailable' without specifying imagery_source attempted.")
        return len(errors) == 0, errors, warnings

    # Status is 'done'
    dom = data.get("dominant_class", "")
    if not dom:
        errors.append(f"Epoch {epoch}: dominant_class is required when status is 'done'.")
    elif dom not in ALL_CLASSES:
        errors.append(f"Epoch {epoch}: dominant_class '{dom}' not in approved vocabulary.")

    if dom in {"other", "ambiguous"}:
        notes = (data.get("notes") or "").strip()
        if not notes:
            errors.append(
                f"Epoch {epoch}: Notes are mandatory when dominant_class is '{dom}'."
            )

    # Share bin validation: mandatory for definite classes, validated if present for any class
    share = data.get("dominant_share_3bins", "")
    if dom in DEFINITE_CLASSES:
        if share not in SHARE_BINS:
            errors.append(f"Epoch {epoch}: dominant_share_3bins '{share}' is invalid. Allowed: {SHARE_BINS}")
    elif share and share not in SHARE_BINS:
        errors.append(f"Epoch {epoch}: dominant_share_3bins '{share}' is invalid. Allowed: {SHARE_BINS}")

    # Confidence validation: mandatory for definite classes, validated if present for any class
    conf = data.get("confidence_1to3")
    if dom in DEFINITE_CLASSES:
        try:
            conf_int = int(conf)
            if conf_int not in CONFIDENCE_LEVELS:
                errors.append(f"Epoch {epoch}: confidence '{conf}' must be 1, 2, or 3.")
            elif conf_int == 1:
                warnings.append(f"Epoch {epoch}: Label has weak confidence (1). Consider re-checking.")
        except (ValueError, TypeError):
            errors.append(f"Epoch {epoch}: confidence_1to3 is required and must be an integer (1, 2, or 3).")
    elif conf is not None and conf != "":
        try:
            conf_int = int(conf)
            if conf_int not in CONFIDENCE_LEVELS:
                errors.append(f"Epoch {epoch}: confidence '{conf}' must be 1, 2, or 3.")
            elif conf_int == 1:
                warnings.append(f"Epoch {epoch}: Label has weak confidence (1). Consider re-checking.")
        except (ValueError, TypeError):
            errors.append(f"Epoch {epoch}: confidence '{conf}' must be an integer (1, 2, or 3).")

    # Second class validation: must be definite class and cannot equal dominant class
    sec = data.get("second_class", "none")
    if sec and sec != "none":
        if sec not in DEFINITE_CLASSES:
            errors.append(f"Epoch {epoch}: second_class '{sec}' not in allowed definite classes.")
        elif sec == dom:
            errors.append(f"Epoch {epoch}: second_class '{sec}' cannot be identical to dominant_class.")

    # Validate imagery source
    src = data.get("imagery_source", "")
    if not src:
        errors.append(f"Epoch {epoch}: imagery_source is required.")
    elif src not in SOURCES_OK:
        errors.append(f"Epoch {epoch}: imagery_source '{src}' is not in approved list: {SOURCES_OK}")

    if src == "Landsat_context":
        conf = data.get("confidence_1to3")
        try:
            if conf and int(conf) > 2:
                errors.append(f"Epoch {epoch}: Protocol rule: with 'Landsat_context', confidence must be at most 2.")
        except (ValueError, TypeError):
            pass

    # Validate date
    dt_str = data.get("imagery_date", "")
    if not dt_str:
        errors.append(f"Epoch {epoch}: imagery_date (YYYY-MM-DD) is required.")
    elif not DATE_REGEX.match(dt_str):
        errors.append(f"Epoch {epoch}: imagery_date '{dt_str}' must be in YYYY-MM-DD format.")
    else:
        try:
            dt_obj = datetime.strptime(dt_str, "%Y-%m-%d")
            year = dt_obj.year
            # Protocol rule: +/- 2 calendar years
            if not (epoch - 2 <= year <= epoch + 2):
                errors.append(f"Epoch {epoch}: imagery_date year {year} is outside the allowed +/-2 years window [{epoch-2}, {epoch+2}].")
        except ValueError:
            errors.append(f"Epoch {epoch}: imagery_date '{dt_str}' is an invalid calendar date.")

    is_valid = len(errors) == 0
    return is_valid, errors, warnings
