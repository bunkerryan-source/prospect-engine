"""
Centralized domain filtering and company name extraction utilities.

Used by all scraping modules and Hunter enrichment to reject noise domains
(news sites, social media, directories, consultants, etc.) and to extract
clean company names from domains when title-tag parsing fails.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Blocked domain suffixes — matched against the END of the normalized domain.
# e.g. "marketplace.walmart.com" matches "walmart.com".
# ---------------------------------------------------------------------------

_BLOCKED_SUFFIXES = {
    # Social media
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "threads.net",
    "snapchat.com",

    # Video
    "youtube.com",
    "vimeo.com",

    # Q&A / forums
    "quora.com",
    "stackexchange.com",
    "stackoverflow.com",

    # Search / tech
    "google.com",
    "bing.com",
    "yahoo.com",
    "aol.com",
    "msn.com",

    # Retail / ecommerce (not prospects — they're buyers, not shippers)
    "walmart.com",
    "amazon.com",
    "target.com",
    "costco.com",
    "ebay.com",
    "etsy.com",
    "alibaba.com",
    "aliexpress.com",

    # Hospitality / non-manufacturer
    "wynnlasvegas.com",
    "mgmresorts.com",
    "caesars.com",

    # Delivery / gig platforms (not freight shippers)
    "instacart.com",
    "grubhub.com",
    "doordash.com",
    "ubereats.com",
    "postmates.com",
    "gopuff.com",
    "shipt.com",

    # LinkedIn subdomains
    "linkedin.com",

    # Government (additional)
    "federalregister.gov",
    "ftc.gov",
    "dshs.texas.gov",
    "agr.wa.gov",
    "agri.nv.gov",
    "gov",

    # Trade data / import record sites (shipping records, not companies)
    "trademo.com",
    "zauba.com",
    "importkey.com",
    "seair.co.in",

    # Ingredient distributors / brokers (not manufacturers, don't ship their own freight)
    "univarsolutions.com",

    # Compliance / regulatory news (not companies)
    "globalcompliancenews.com",
    "compliancegate.com",
    "pharmacompass.com",

    # M&A / investment firms (not shippers)
    "morganandwestfield.com",
    "ampersandcapital.com",

    # Testing / lab services (not freight shippers)
    "eurofinsus.com",

    # Retail / e-commerce (additional)
    "redstickspice.com",
    "olivenation.com",
    "wholesalesuppliesplus.com",

    # Drug development news/directories
    "drug-dev.com",
    "chemxpert.com",

    # Jobs / recruiting
    "indeed.com",
    "glassdoor.com",
    "glassdoor.co.in",
    "ziprecruiter.com",
    "monster.com",
    "careerbuilder.com",

    # News / media
    "latimes.com",
    "nytimes.com",
    "washingtonpost.com",
    "wsj.com",
    "cnn.com",
    "foxnews.com",
    "bbc.com",
    "reuters.com",
    "apnews.com",
    "usatoday.com",
    "forbes.com",
    "bloomberg.com",
    "businessinsider.com",
    "cnbc.com",
    "finance.yahoo.com",

    # Regional news / media
    "dailyhive.com",
    "coppercourier.com",

    # Press release / PR
    "prnewswire.com",
    "globenewswire.com",
    "businesswire.com",
    "prweb.com",

    # Trade news (articles, not companies)
    "supplychaindive.com",
    "fooddive.com",
    "bevnet.com",
    "massmarketretailers.com",
    "talkbusiness.net",
    "trellis.net",
    "packagingdigest.com",
    "foodprocessing.com",
    "nutraceuticalsworld.com",
    "nutraceuticalbusinessreview.com",
    "contractpharma.com",
    "candlefind.com",

    # Directories / aggregators (not the actual companies)
    "thomasnet.com",
    "dnb.com",
    "zoominfo.com",
    "manta.com",
    "bbb.org",
    "yellowpages.com",
    "superpages.com",
    "hotfrog.com",
    "eximpedia.app",
    "accio.com",
    "tradekey.com",
    "kompass.com",
    "europages.com",
    "globalspec.com",
    "exportgenius.in",
    "panjiva.com",
    "volza.com",
    "madeinwashington.com",

    # Logistics consultants & compliance SaaS (they advise, not ship)
    "8thandwalton.com",
    "carbon6.io",
    "vendormint.com",
    "newnexusgroup.com",
    "ozarkconsulting.com",
    "coldstreamlogistics.com",
    "rjwgroup.com",
    "5gsales.com",
    "supplypike.com",
    "harvestgroup.com",
    "winningwithwalmart.com",
    "getproductiv.com",
    "orderful.com",
    "triumph.io",
    "warehousequote.com",
    "mybluegrace.com",
    "capstonelogistics.com",
    "classicharvest.com",
    "buildbunker.com",

    # Knowledge / reference / wiki
    "wikipedia.org",
    "wikihow.com",
    "britannica.com",

    # Government
    "fda.gov",
    "nih.gov",
    "usda.gov",
    "sec.gov",
    "census.gov",

    # Academic
    "edu",

    # State economic dev (articles about industry, not companies)
    "arkansasedc.com",

    # Generic hosting / platform pages
    "medium.com",
    "substack.com",
    "wordpress.com",
    "blogspot.com",
    "wixsite.com",
    "squarespace.com",
    "hubspot.com",
    "mailchimp.com",

    # Marketplace / learning pages of retailers
    "corporate.walmart.com",
    "marketplace.walmart.com",
    "public.walmart.com",
    "marketplacelearn.walmart.com",
    "supplierone.helpdocs.io",

    # Non-prospect platforms (lead gen sites, not actual manufacturers)
    "mycustommanufacturer.com",

    # Yelp / review sites
    "yelp.com",
    "trustpilot.com",
    "sitejabber.com",
    "g2.com",
}


# ---------------------------------------------------------------------------
# Blocked country-code TLDs — we only target US freight, so non-US domains
# are not prospects.
# ---------------------------------------------------------------------------

_BLOCKED_TLDS = {
    ".ca",
    ".co.uk",
    ".co.in",
    ".com.au",
    ".com.br",
    ".com.mx",
    ".com.ec",
    ".com.pg",
    ".de",
    ".fr",
    ".es",
    ".it",
    ".jp",
    ".cn",
    ".in",
    ".ae",
    ".co.jp",
    ".eu",
}


# User-configurable blocked domains loaded from config.yaml at runtime.
# Populated by load_user_blocked_domains() — called once during pipeline init.
_user_blocked: set[str] = set()


def load_user_blocked_domains(config: dict) -> None:
    """Load the blocked_domains list from config.yaml into the runtime set.

    Call this once at pipeline startup after loading config.
    """
    global _user_blocked
    domains = config.get("blocked_domains") or []
    _user_blocked = {d.lower().strip() for d in domains if d}


def is_blocked_domain(domain: str) -> bool:
    """Check if a domain matches any blocked suffix, user blocklist, or non-US TLD.

    Uses suffix matching so 'marketplace.walmart.com' matches 'walmart.com',
    and 'news.google.com' matches 'google.com'.  Also rejects domains ending
    in non-US country-code TLDs (e.g. .ca, .co.uk, .de).
    """
    if not domain:
        return True
    d = domain.lower().strip()
    # User-configured blocklist (exact match)
    if d in _user_blocked:
        return True
    # User-configured blocklist (suffix match)
    for blocked in _user_blocked:
        if d.endswith("." + blocked):
            return True
    # Block non-US country TLDs (check longest suffixes first for .co.uk etc.)
    for tld in _BLOCKED_TLDS:
        if d.endswith(tld):
            return True
    # Exact match first (fast path)
    if d in _BLOCKED_SUFFIXES:
        return True
    # Suffix match: check if domain ends with '.blockedsite.com'
    for blocked in _BLOCKED_SUFFIXES:
        if d.endswith("." + blocked):
            return True
    return False


# ---------------------------------------------------------------------------
# ImportYeti special handling — we WANT importyeti search results but the
# domain itself (importyeti.com) is not a prospect.  The company name
# should be extracted from the title, not the domain.
# ---------------------------------------------------------------------------

_IMPORTYETI_DOMAINS = {"importyeti.com"}


def is_importyeti(domain: str) -> bool:
    return domain.lower().strip() in _IMPORTYETI_DOMAINS


# ---------------------------------------------------------------------------
# Company name extraction from domain
# ---------------------------------------------------------------------------

# Common TLDs to strip
_TLD_PATTERN = re.compile(
    r"\.(com|net|org|io|co|us|biz|info|app|ai|xyz|tech|solutions|global|inc)$",
    re.IGNORECASE,
)

# Words that are part of the domain but not meaningful company names
_DOMAIN_NOISE_WORDS = {
    "www", "mail", "shop", "store", "buy", "get", "my", "the",
}


def domain_to_company_name(domain: str) -> str:
    """Convert a bare domain to a rough company name.

    Example: 'bellff.com' → 'Bellff'
             'citrusandallied.com' → 'Citrusandallied'
             'fultonandroark.com' → 'Fultonandroark'

    This is a fallback — Apollo/Hunter will overwrite with the real name.
    """
    if not domain:
        return ""
    # Strip TLD
    name = _TLD_PATTERN.sub("", domain.lower().strip())
    # Remove any remaining dots (subdomains)
    parts = name.split(".")
    # Take the last meaningful part (the actual domain name, not subdomain)
    name = parts[-1] if parts else name
    # Title case
    return name.strip().title() if name else domain


def extract_company_from_title(title: str, domain: str) -> str:
    """Try to extract a company name from a search result title.

    Strategy:
    1. Split title on common separators (|, -, —, :)
    2. Take the first segment
    3. If the first segment looks like an article headline (>60 chars or
       starts with common article words), fall back to domain-based name
    4. Otherwise use the cleaned first segment

    Args:
        title: The search result title tag
        domain: The normalized domain (used as fallback)

    Returns:
        Best-guess company name
    """
    if not title:
        return domain_to_company_name(domain)

    # Split on separators: pipe, em-dash, space-dash-space, colon-space
    parts = re.split(r"\s*[|\u2014]\s*|\s+-\s+|\s*:\s+", title)
    candidate = parts[0].strip() if parts else title.strip()

    # Heuristics: is this a company name or an article headline?
    _ARTICLE_STARTERS = (
        "how", "what", "why", "when", "where", "which", "who",
        "top", "best", "the", "a ", "an ",
        "should", "can", "is ", "are ", "do ", "does ",
        "avoid", "prevent", "guide", "review", "list",
        "walmart", "amazon",
        # Service/manufacturing descriptions — not company names
        "private label", "contract", "custom", "manufacturing",
        "supplement", "us based", "usa based", "companies directory",
        "turnkey", "dietary supplement",
    )

    candidate_lower = candidate.lower()

    # Too long = almost certainly a headline, not a company name
    if len(candidate) > 60:
        return domain_to_company_name(domain)

    # Starts with article/question words or service descriptions
    if any(candidate_lower.startswith(w) for w in _ARTICLE_STARTERS):
        return domain_to_company_name(domain)

    # Starts with a number (e.g. "9 PNW-based...") — listicle title
    if re.match(r"^\d+\s", candidate):
        return domain_to_company_name(domain)

    # Contains service/manufacturing description words mid-title
    _SERVICE_WORDS = ("manufacturing", "services", "solutions", "private label")
    if any(w in candidate_lower for w in _SERVICE_WORDS) and len(candidate) > 30:
        return domain_to_company_name(domain)

    # Contains "..." (truncated title)
    if "..." in candidate:
        return domain_to_company_name(domain)

    # If we get here, the candidate looks plausible as a company name
    # Strip trailing punctuation
    candidate = candidate.rstrip(".:,;!?")
    return candidate if candidate else domain_to_company_name(domain)


# ---------------------------------------------------------------------------
# US state extraction from free text (snippets)
# ---------------------------------------------------------------------------

# US state abbreviations and full names mapping
_STATE_ABBREVS = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
_VALID_ABBREVS = set(_STATE_ABBREVS.values())


def extract_state_from_text(text: str) -> str:
    """Try to extract a US state abbreviation from free text.

    Looks for patterns like:
    - "Phoenix, AZ"
    - "in Arizona"
    - "located in California"
    - "Las Vegas, Nevada"
    - "Twin Falls, ID 83301"

    Returns 2-letter state abbreviation or empty string.
    """
    if not text:
        return ""

    import re

    # Pattern 1: "City, ST" or "City, ST ZIP" (2-letter abbreviation after comma)
    match = re.search(r',\s*([A-Z]{2})\b', text)
    if match:
        abbrev = match.group(1)
        if abbrev in _VALID_ABBREVS:
            return abbrev

    # Pattern 2: Full state name
    text_lower = text.lower()
    for state_name, abbrev in _STATE_ABBREVS.items():
        # Look for the state name as a whole word
        pattern = r'\b' + re.escape(state_name) + r'\b'
        if re.search(pattern, text_lower):
            return abbrev

    return ""
