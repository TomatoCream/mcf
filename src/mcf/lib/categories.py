"""Job categories used by MyCareersFuture."""

import re

# Known categories extracted from actual job data.
# These are the valid category names for filtering searches.
CATEGORIES: list[str] = [
    "Accounting / Auditing / Taxation",
    "Admin / Secretarial",
    "Advertising / Media",
    "Architecture / Interior Design",
    "Banking and Finance",
    "Building and Construction",
    "Consulting",
    "Customer Service",
    "Design",
    "Education and Training",
    "Engineering",
    "Entertainment",
    "Environment / Health",
    "Events / Promotions",
    "F&B",
    "General Management",
    "General Work",
    "Healthcare / Pharmaceutical",
    "Hospitality",
    "Human Resources",
    "Information Technology",
    "Insurance",
    "Legal",
    "Logistics / Supply Chain",
    "Manufacturing",
    "Marketing / Public Relations",
    "Medical / Therapy Services",
    "Others",
    "Personal Care / Beauty",
    "Precision Engineering",
    "Professional Services",
    "Public / Civil Service",
    "Purchasing / Merchandising",
    "Real Estate / Property Management",
    "Repair and Maintenance",
    "Risk Management",
    "Sales / Retail",
    "Sciences / Laboratory / R&D",
    "Security and Investigation",
    "Social Services",
    "Telecommunications",
    "Travel / Tourism",
    "Wholesale Trade",
]


def _to_slug(name: str) -> str:
    """Convert category name to a slug for easy typing.

    Examples:
        "Information Technology" -> "information-technology"
        "F&B" -> "fb"
        "Accounting / Auditing / Taxation" -> "accounting-auditing-taxation"
    """
    # Lowercase
    slug = name.lower()
    # Replace / and & with nothing (they separate words)
    slug = slug.replace(" / ", "-").replace("/", "-").replace(" & ", "-").replace("&", "")
    # Replace spaces with dashes
    slug = slug.replace(" ", "-")
    # Remove any other special characters
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse multiple dashes
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing dashes
    return slug.strip("-")


# Build slug -> category mapping
CATEGORY_SLUGS: dict[str, str] = {_to_slug(cat): cat for cat in CATEGORIES}

# Common aliases for easier typing
CATEGORY_ALIASES: dict[str, str] = {
    "it": "Information Technology",
    "tech": "Information Technology",
    "hr": "Human Resources",
    "fnb": "F&B",
    "f-and-b": "F&B",
    "food": "F&B",
    "pr": "Marketing / Public Relations",
    "marketing": "Marketing / Public Relations",
    "finance": "Banking and Finance",
    "bank": "Banking and Finance",
    "construction": "Building and Construction",
    "building": "Building and Construction",
    "accounting": "Accounting / Auditing / Taxation",
    "audit": "Accounting / Auditing / Taxation",
    "tax": "Accounting / Auditing / Taxation",
    "admin": "Admin / Secretarial",
    "secretary": "Admin / Secretarial",
    "logistics": "Logistics / Supply Chain",
    "supply-chain": "Logistics / Supply Chain",
    "healthcare": "Healthcare / Pharmaceutical",
    "pharma": "Healthcare / Pharmaceutical",
    "medical": "Medical / Therapy Services",
    "therapy": "Medical / Therapy Services",
    "sales": "Sales / Retail",
    "retail": "Sales / Retail",
    "security": "Security and Investigation",
    "science": "Sciences / Laboratory / R&D",
    "lab": "Sciences / Laboratory / R&D",
    "rnd": "Sciences / Laboratory / R&D",
    "r-and-d": "Sciences / Laboratory / R&D",
    "education": "Education and Training",
    "training": "Education and Training",
    "real-estate": "Real Estate / Property Management",
    "property": "Real Estate / Property Management",
    "travel": "Travel / Tourism",
    "tourism": "Travel / Tourism",
    "repair": "Repair and Maintenance",
    "maintenance": "Repair and Maintenance",
    "social": "Social Services",
    "telecom": "Telecommunications",
    "env": "Environment / Health",
    "environment": "Environment / Health",
    "events": "Events / Promotions",
    "promotions": "Events / Promotions",
}


def get_categories() -> list[str]:
    """Get list of all valid job categories.

    Returns:
        List of category names that can be used for filtering.
    """
    return CATEGORIES.copy()


def get_category_slugs() -> dict[str, str]:
    """Get mapping of slug -> category name.

    Returns:
        Dict mapping slugs to full category names.
    """
    return CATEGORY_SLUGS.copy()


def resolve_category(input_str: str) -> str | None:
    """Resolve a category from user input (alias, slug, partial match, or exact).

    Tries in order:
    1. Common alias (e.g., "it" -> "Information Technology")
    2. Exact slug match (e.g., "information-technology")
    3. Exact name match (case-insensitive)
    4. Slug starts with input (e.g., "info" -> "information-technology")
    5. Input starts a word in slug (e.g., "eng" -> "engineering")
    6. Partial match in slug or name

    Args:
        input_str: User input - can be alias, slug, or category name.

    Returns:
        The canonical category name if found, None otherwise.
    """
    input_lower = input_str.lower().strip()

    # 1. Check common aliases first
    if input_lower in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[input_lower]

    # 2. Check exact slug match
    if input_lower in CATEGORY_SLUGS:
        return CATEGORY_SLUGS[input_lower]

    # 3. Check exact name match (case-insensitive)
    for cat in CATEGORIES:
        if cat.lower() == input_lower:
            return cat

    # 4. Check if slug starts with input
    for slug, cat in CATEGORY_SLUGS.items():
        if slug.startswith(input_lower):
            return cat

    # 5. Check if input starts a word in the slug (e.g., "eng" in "engineering")
    for slug, cat in CATEGORY_SLUGS.items():
        parts = slug.split("-")
        for part in parts:
            if part.startswith(input_lower):
                return cat

    # 6. Fallback: partial match anywhere in slug
    for slug, cat in CATEGORY_SLUGS.items():
        if input_lower in slug:
            return cat

    # 7. Fallback: partial match in name
    for cat in CATEGORIES:
        if input_lower in cat.lower():
            return cat

    return None


def find_categories(search_term: str) -> list[str]:
    """Find categories matching a search term.

    Args:
        search_term: Partial name or slug to search for.

    Returns:
        List of matching category names.
    """
    term_lower = search_term.lower()
    matches = []

    for cat in CATEGORIES:
        slug = _to_slug(cat)
        if term_lower in cat.lower() or term_lower in slug:
            matches.append(cat)

    return matches


# Legacy alias
def validate_category(category: str) -> str | None:
    """Validate a category name (case-insensitive).

    Deprecated: Use resolve_category() instead.

    Args:
        category: Category name to validate.

    Returns:
        The correct category name if found, None otherwise.
    """
    return resolve_category(category)
