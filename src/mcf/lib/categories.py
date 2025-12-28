"""Job categories used by MyCareersFuture."""

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


def get_categories() -> list[str]:
    """Get list of all valid job categories.

    Returns:
        List of category names that can be used for filtering.
    """
    return CATEGORIES.copy()


def validate_category(category: str) -> str | None:
    """Validate a category name (case-insensitive).

    Args:
        category: Category name to validate.

    Returns:
        The correct category name if found, None otherwise.
    """
    category_lower = category.lower()
    for cat in CATEGORIES:
        if cat.lower() == category_lower:
            return cat
    return None


def find_categories(search_term: str) -> list[str]:
    """Find categories matching a search term.

    Args:
        search_term: Partial name to search for.

    Returns:
        List of matching category names.
    """
    term_lower = search_term.lower()
    return [cat for cat in CATEGORIES if term_lower in cat.lower()]

