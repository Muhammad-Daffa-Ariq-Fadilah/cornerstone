"""
cornerstone_preprocessing.py

Text cleaning module for Cornerstone — replicates the EXACT preprocessing
used during model training (by AI Engineer 2). This is critical: the model
was trained on cleaned text, so inference MUST apply the same cleaning,
otherwise accuracy drops from ~95% to ~71%.

Source of truth: cornerstone_preprocessing.py (training pipeline).
"""

import re

# Leet-speak digit -> letter mapping
LEET_MAP = {
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "6": "g", "7": "t",
}

# Merchant name normalization (regex pattern -> canonical name)
MERCHANT_NORMALIZATION = {
    # Transportation
    r"\bgojek\b": "gojek", r"\bgo.?ride\b": "goride", r"\bgo.?car\b": "gocar",
    r"\bgo.?food\b": "gofood", r"\bgrab\b": "grab", r"\bgrab.?food\b": "grabfood",
    r"\bgrab.?car\b": "grabcar", r"\bgrab.?bike\b": "grabbike", r"\bmaxim\b": "maxim",
    r"\bbluebird\b": "bluebird", r"\bkrl\b": "krl commuter", r"\btransjakarta\b": "transjakarta",
    r"\bmrt\b": "mrt jakarta", r"\bspbu\b": "pertamina", r"\bpertamina\b": "pertamina",
    # Food & Beverage
    r"\bmcdonalds?\b": "mcdonalds", r"\bkfc\b": "kfc", r"\bpizza.?hut\b": "pizza hut",
    r"\bdomino.?s?\b": "dominos", r"\bindomaret\b": "indomaret", r"\balfamart\b": "alfamart",
    r"\bstarbucks?\b": "starbucks", r"\bkopi.?kenangan\b": "kopi kenangan", r"\bjco\b": "j.co donuts",
    r"\bchatime\b": "chatime", r"\bgofood\b": "gofood", r"\bshopee.?food\b": "shopeefood",
    # Entertainment
    r"\bspotify\b": "spotify", r"\bdrv\s+spotify\b": "spotify", r"\byoutube\b": "youtube",
    r"\bnetflix\b": "netflix", r"\bhbo\s*go\b": "hbo go", r"\bdisney\s*\+?\b": "disney plus",
    r"\bviu\b": "viu", r"\bvidio\b": "vidio", r"\bwebtoon\b": "webtoon", r"\bbioskop\b": "bioskop",
    r"\bcgv\b": "cgv", r"\bxxi\b": "xxi", r"\bcinepolis\b": "cinepolis",
    # Shopping
    r"\btokopedia\b": "tokopedia", r"\bshopee\b": "shopee", r"\blazada\b": "lazada",
    r"\bbukalapak\b": "bukalapak", r"\bblibli\b": "blibli", r"\bikea\b": "ikea",
    # Bills / Utilities
    r"\bpln\b": "pln", r"\bpdam\b": "pdam", r"\btelkomsel\b": "telkomsel", r"\bindosat\b": "indosat",
    r"\bxl\b": "xl axiata", r"\baxis\b": "xl axiata", r"\bbypass\b": "bypass", r"\bbpjs\b": "bpjs",
    r"\bbrizzi\b": "brizzi", r"\btapcash\b": "tapcash", r"\be.?money\b": "emoney", r"\bflazz\b": "flazz",
    # Payments / Wallets
    r"\bgopay\b": "gopay", r"\bovo\b": "ovo", r"\bdana\b": "dana", r"\blinkaja\b": "linkaja",
    r"\bshopeepay\b": "shopeepay", r"\bmandiri\b": "bank mandiri", r"\bbca\b": "bank bca",
    r"\bbni\b": "bank bni", r"\bbri\b": "bank bri", r"\bcimb\b": "cimb niaga",
}


def normalize_leet(text: str) -> str:
    """Replace leet-speak digits in uppercase or digit-containing strings."""
    if text.isupper() or re.search(r"[0-9]", text):
        for digit, letter in LEET_MAP.items():
            text = text.replace(digit, letter)
    return text


def clean_transaction_name(raw: str) -> str:
    """
    Full cleaning pipeline for a single transaction name.
    MUST match the training-time cleaning exactly.

    Steps:
      1. Coerce to string, strip
      2. Leet normalization (before lowercasing)
      3. Lowercase
      4. Remove special chars (keep alphanumeric + space)
      5. Collapse whitespace
      6. Merchant normalization via regex
    """
    if raw is None or (isinstance(raw, float)):
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    text = normalize_leet(text)            # step 2
    text = text.lower()                    # step 3
    text = re.sub(r"[^a-z0-9\s]", " ", text)   # step 4
    text = re.sub(r"\s+", " ", text).strip()   # step 5
    for pattern, replacement in MERCHANT_NORMALIZATION.items():  # step 6
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text.strip()
