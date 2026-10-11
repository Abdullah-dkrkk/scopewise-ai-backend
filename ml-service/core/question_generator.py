"""Deterministic, text-aware clarification question generation.

The generator never calls a model or the network. Instead it combines four
deterministic signals to produce questions that read as though they were
written for the specific requirement:

1. **Category templates** — the questions that always matter for the detected
   category (payments, auth, dashboards, ...), skipped when the text already
   answers them.
2. **Feature templates** — questions for each feature the extractor found.
3. **Quoted terms** — the exact vague or de-scoping words the customer used
   ("etc", "phase 2", "simple") are quoted back at them, which is what turns a
   generic question into a pointed one.
4. **Missing dimensions** — non-functional areas a requirement frequently omits
   (performance/scale, security, accessibility, data retention, error handling,
   acceptance criteria) are explicitly asked about when absent.

Every returned question has the public shape
``{"question", "category", "priority"}``.
"""

from __future__ import annotations

import re

from core.clarity import find_scope_terms, find_vague_terms, quote_term

MAX_QUESTIONS = 15

# Internal templates carry a `covers` list: if any of those terms already
# appears in the text the topic is considered answered and the question is
# dropped. `covers` never leaves this module.
CATEGORY_TEMPLATES: dict[str, list[dict]] = {
    "authentication": [
        {"question": "What authentication methods do you need? (Email/Password, Social Login, SSO, 2FA)", "category": "authentication", "priority": "high", "covers": ["oauth", "sso", "2fa", "mfa", "social login"]},
        {"question": "What password policy should be enforced? (Min length, special chars, expiry)", "category": "authentication", "priority": "medium", "covers": ["password policy", "min length", "complexity"]},
        {"question": "Do you need role-based access control (RBAC)? What roles are required?", "category": "authentication", "priority": "high", "covers": ["rbac", "role", "permission"]},
        {"question": "How should password reset work? (Email link, security questions, admin reset)", "category": "authentication", "priority": "medium", "covers": ["reset password", "forgot password", "password reset"]},
        {"question": "Do you need session management features? (Concurrent sessions, session timeout)", "category": "authentication", "priority": "low", "covers": ["session timeout", "concurrent session"]},
    ],
    "e_commerce": [
        {"question": "What payment gateways should be integrated? (Stripe, PayPal, local methods)", "category": "payment", "priority": "high", "covers": ["stripe", "paypal", "gateway", "checkout"]},
        {"question": "What product types will be sold? (Physical, digital, subscriptions, services)", "category": "e_commerce", "priority": "high", "covers": ["subscription", "digital product", "physical product"]},
        {"question": "Do you need multi-currency and tax calculation support?", "category": "e_commerce", "priority": "medium", "covers": ["currency", "tax", "vat", "gst"]},
        {"question": "What shipping and delivery options are required?", "category": "e_commerce", "priority": "medium", "covers": ["shipping", "delivery", "dispatch"]},
        {"question": "Do you need inventory management with stock alerts?", "category": "e_commerce", "priority": "medium", "covers": ["inventory", "stock", "warehouse"]},
        {"question": "Should customers have wishlists and save-for-later functionality?", "category": "e_commerce", "priority": "low", "covers": ["wishlist", "save for later"]},
    ],
    "dashboard": [
        {"question": "What key metrics and KPIs should be displayed on the dashboard?", "category": "dashboard", "priority": "high", "covers": ["kpi", "metric"]},
        {"question": "Should the dashboard have real-time data updates? What refresh rate?", "category": "dashboard", "priority": "high", "covers": ["real-time", "realtime", "live", "websocket", "refresh"]},
        {"question": "What export formats are needed? (PDF, CSV, Excel, Print)", "category": "dashboard", "priority": "medium", "covers": ["pdf", "csv", "excel", "export"]},
        {"question": "Do users need customizable dashboard layouts or widget arrangements?", "category": "dashboard", "priority": "medium", "covers": ["customizable", "widget", "layout"]},
        {"question": "What date range and filtering options should be available?", "category": "dashboard", "priority": "medium", "covers": ["date range", "filter"]},
    ],
    "api": [
        {"question": "What authentication method should the API use? (JWT, API Key, OAuth)", "category": "api", "priority": "high", "covers": ["jwt", "api key", "oauth"]},
        {"question": "What rate limiting requirements do you have?", "category": "api", "priority": "medium", "covers": ["rate limit", "throttl"]},
        {"question": "Do you need API versioning? What versioning strategy? (URL, Header)", "category": "api", "priority": "medium", "covers": ["versioning", "version"]},
        {"question": "What third-party APIs need to be integrated?", "category": "api", "priority": "high", "covers": ["third-party", "third party", "external api"]},
        {"question": "Do you need webhook support for event-driven integrations?", "category": "api", "priority": "medium", "covers": ["webhook", "callback"]},
    ],
    "ui_design": [
        {"question": "What devices and screen sizes must be supported? (Desktop, tablet, mobile)", "category": "ui_design", "priority": "high", "covers": ["responsive", "mobile", "tablet", "desktop"]},
        {"question": "Should the UI support theming? (Light/dark mode, custom colors)", "category": "ui_design", "priority": "medium", "covers": ["theme", "dark mode", "light mode"]},
        {"question": "What accessibility standards must be met? (WCAG 2.1 Level A/AA)", "category": "ui_design", "priority": "medium", "covers": ["accessibility", "wcag", "a11y"]},
        {"question": "Do you need multi-language support? What languages?", "category": "ui_design", "priority": "medium", "covers": ["multi-language", "multilingual", "i18n", "translation"]},
        {"question": "What animation and transition effects are expected?", "category": "ui_design", "priority": "low", "covers": ["animation", "transition"]},
    ],
    "content_management": [
        {"question": "What content types need to be managed? (Pages, blog posts, media, products)", "category": "content_management", "priority": "high", "covers": ["content type", "blog", "page", "media"]},
        {"question": "Do you need a WYSIWYG editor or Markdown support?", "category": "content_management", "priority": "medium", "covers": ["wysiwyg", "markdown", "rich text"]},
        {"question": "What SEO features are required? (Meta tags, sitemaps, canonical URLs)", "category": "content_management", "priority": "medium", "covers": ["seo", "meta", "sitemap"]},
        {"question": "Do you need content versioning and revision history?", "category": "content_management", "priority": "medium", "covers": ["versioning", "revision", "draft"]},
        {"question": "Is multi-language content management required?", "category": "content_management", "priority": "low", "covers": ["multilingual", "translation", "language"]},
    ],
    "marketing": [
        {"question": "What email marketing features are needed? (Templates, scheduling, analytics)", "category": "marketing", "priority": "high", "covers": ["email marketing", "template", "campaign"]},
        {"question": "Do you need A/B testing capabilities for campaigns?", "category": "marketing", "priority": "medium", "covers": ["a/b", "ab test", "variant"]},
        {"question": "What analytics and tracking integrations are required?", "category": "marketing", "priority": "medium", "covers": ["analytics", "tracking", "conversion"]},
        {"question": "Do you need social media integration and scheduling?", "category": "marketing", "priority": "low", "covers": ["social media", "scheduler"]},
    ],
    "integration": [
        {"question": "What external systems need to be integrated?", "category": "integration", "priority": "high", "covers": ["integrat", "external system", "third-party"]},
        {"question": "Is real-time data synchronization required between systems?", "category": "integration", "priority": "high", "covers": ["synchron", "real-time sync", "two-way"]},
        {"question": "What happens when the external system is unavailable? (Fallback, retry, queue)", "category": "integration", "priority": "high", "covers": ["fallback", "retry", "circuit breaker", "degraded"]},
        {"question": "Do you need data transformation between different formats?", "category": "integration", "priority": "medium", "covers": ["transform", "mapping", "format"]},
    ],
    "general": [
        {"question": "What is the expected number of users/traffic for this feature?", "category": "general", "priority": "high", "covers": ["users", "traffic", "concurrent", "scale"]},
        {"question": "Are there any performance requirements? (Response time, throughput)", "category": "general", "priority": "high", "covers": ["performance", "response time", "throughput", "latency"]},
        {"question": "What browser and device compatibility is required?", "category": "general", "priority": "medium", "covers": ["browser", "device", "compatibility", "responsive"]},
        {"question": "Do you need audit logging for this feature?", "category": "general", "priority": "low", "covers": ["audit", "logging", "activity log"]},
        {"question": "What testing coverage is expected? (Unit, integration, e2e)", "category": "general", "priority": "low", "covers": ["testing", "unit test", "e2e"]},
    ],
}

# Feature extractor output name -> category template key. The extractor emits
# human labels ("Authentication & Authorization"), the templates key on short
# names, so the two are bridged here instead of relying on string surgery.
FEATURE_TO_CATEGORY = {
    "Authentication & Authorization": "authentication",
    "User Management": "authentication",
    "Payment Processing": "e_commerce",
    "E-Commerce": "e_commerce",
    "Dashboard & Analytics": "dashboard",
    "Content Management": "content_management",
    "API & Integration": "api",
}

# Categories beyond the classifier's vocabulary that still deserve questions
# when a feature implies them.
EXTRA_FEATURE_TEMPLATES: dict[str, list[dict]] = {
    "Notifications": [
        {"question": "Which notification channels are needed? (Email, SMS, push, in-app)", "category": "notification", "priority": "high", "covers": ["email notification", "sms", "push", "in-app"]},
        {"question": "Can users opt out of notifications, and how?", "category": "notification", "priority": "low", "covers": ["opt out", "unsubscribe", "preference"]},
    ],
    "Security": [
        {"question": "What data must be encrypted at rest and in transit?", "category": "security", "priority": "high", "covers": ["encrypt", "at rest", "in transit", "tls", "ssl"]},
        {"question": "Are there compliance obligations we must design for? (GDPR, HIPAA, PCI)", "category": "security", "priority": "high", "covers": ["gdpr", "hipaa", "pci", "compliance"]},
    ],
    "File Management": [
        {"question": "What file types and maximum sizes must be supported?", "category": "file_management", "priority": "high", "covers": ["file type", "max size", "mb", "gb"]},
        {"question": "Where should uploaded files be stored? (Local disk, S3/cloud, CDN)", "category": "file_management", "priority": "medium", "covers": ["s3", "cdn", "cloud storage", "blob"]},
    ],
    "Search & Filtering": [
        {"question": "How many records must search cover, and does it need to scale?", "category": "search", "priority": "medium", "covers": ["records", "elasticsearch", "full-text"]},
        {"question": "Which fields should be searchable and filterable?", "category": "search", "priority": "medium", "covers": ["searchable field", "filter field"]},
    ],
    "Real-Time Features": [
        {"question": "What is the acceptable latency for real-time updates?", "category": "realtime", "priority": "high", "covers": ["latency", "milliseconds", "seconds"]},
        {"question": "How many concurrent real-time connections must be supported?", "category": "realtime", "priority": "medium", "covers": ["concurrent connection", "simultaneous"]},
    ],
    "Geolocation & Maps": [
        {"question": "Which mapping provider should be used? (Google Maps, Mapbox, OpenStreetMap)", "category": "geolocation", "priority": "medium", "covers": ["google maps", "mapbox", "openstreetmap", "leaflet"]},
        {"question": "Is location data stored, and how is user privacy handled?", "category": "geolocation", "priority": "high", "covers": ["privacy", "consent", "retention"]},
    ],
    "AI & Machine Learning": [
        {"question": "What training data is available, and who owns it?", "category": "ai_ml", "priority": "high", "covers": ["training data", "dataset", "corpus"]},
        {"question": "What accuracy or quality bar must the model meet?", "category": "ai_ml", "priority": "high", "covers": ["accuracy", "precision", "recall", "f1"]},
    ],
    "UI Components": [
        {"question": "Are there design mockups or a design system to follow?", "category": "ui_design", "priority": "medium", "covers": ["mockup", "figma", "design system", "wireframe"]},
        {"question": "Which browsers and screen sizes must the components support?", "category": "ui_design", "priority": "medium", "covers": ["browser support", "screen size", "responsive"]},
    ],
}

# Non-functional dimensions a requirement frequently forgets to state. Each is
# asked only when none of its trigger terms appear in the text.
DIMENSION_CHECKS: list[dict] = [
    {
        "triggers": ["performance", "response time", "latency", "throughput", "fast", "slow", "under"],
        "question": "What are the performance expectations? (Expected response time and peak load)",
        "category": "performance",
        "priority": "medium",
    },
    {
        "triggers": ["security", "secure", "encrypt", "auth", "token", "gdpr", "hipaa", "pci", "privacy"],
        "question": "What security and privacy requirements apply to this feature?",
        "category": "security",
        "priority": "medium",
    },
    {
        "triggers": ["error", "failure", "retry", "fallback", "timeout", "unavailable"],
        "question": "How should the system behave when something fails or is temporarily unavailable?",
        "category": "reliability",
        "priority": "low",
    },
    {
        "triggers": ["acceptance", "criteria", "definition of done", "success measure"],
        "question": "What are the acceptance criteria that define this requirement as complete?",
        "category": "scope",
        "priority": "high",
    },
]

GENERAL_QUESTIONS = [
    {"question": "What is the target launch date for this feature/project?", "category": "timeline", "priority": "high", "covers": ["deadline", "launch date", "go live"]},
    {"question": "What is the estimated team size and composition?", "category": "planning", "priority": "high", "covers": ["team size", "developers", "resources"]},
    {"question": "Are there any dependencies on other features or teams?", "category": "dependencies", "priority": "medium", "covers": ["depend", "blocker", "prerequisite"]},
]


def _normalize_category(category: str) -> str:
    return str(category or "general").strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_feature(feature: str) -> str:
    return re.sub(r"\s+", " ", str(feature or "")).strip()


def _answered(question: dict, text_lower: str) -> bool:
    covers = question.get("covers") or []

    return any(term in text_lower for term in covers)


def _vague_term_questions(text: str) -> list[dict]:
    """Quote the exact vague/de-scoping words back to the customer."""
    questions = []

    vague = find_vague_terms(text)
    scope = find_scope_terms(text)

    if vague:
        listed = ", ".join(quote_term(term) for term in vague[:4])
        questions.append(
            {
                "question": (
                    f"You wrote {listed}. Please list every item, case or feature those "
                    "words stand in for, so the scope can be estimated."
                ),
                "category": "scope",
                "priority": "high",
            }
        )

    scope_phrases = [term for term in scope if term in {"maybe", "perhaps", "possibly", "might", "could", "should", "simple", "just", "easy", "quick", "basic"}]

    if scope_phrases:
        listed = ", ".join(quote_term(term) for term in scope_phrases[:4])
        questions.append(
            {
                "question": (
                    f"Words like {listed} suggest the work is smaller than it may be. "
                    "What exactly must be built, and what is explicitly out of scope?"
                ),
                "category": "scope",
                "priority": "high",
            }
        )

    deferred = [term for term in scope if term in {"later", "phase 2", "phase two", "nice to have", "nice-to-have", "stretch", "if time permits", "as needed"}]

    if deferred:
        listed = ", ".join(quote_term(term) for term in deferred[:4])
        questions.append(
            {
                "question": (
                    f"You mentioned {listed}. Confirm whether this work is in scope for this "
                    "estimate or deferred to a later phase."
                ),
                "category": "scope",
                "priority": "high",
            }
        )

    return questions


def generate_questions(
    text: str,
    category: str,
    complexity_score: float,
    detected_features: list[str],
    *,
    max_questions: int = MAX_QUESTIONS,
) -> list[dict]:
    """Produce bounded, deduplicated, text-aware clarification questions."""
    text_lower = text.lower()
    category_key = _normalize_category(category)
    questions: list[dict] = []

    def add(question: dict | None) -> None:
        if not question:
            return

        if _answered(question, text_lower):
            return

        prompt = str(question.get("question", "")).strip()

        if not prompt:
            return

        if any(existing["question"] == prompt for existing in questions):
            return

        questions.append(
            {
                "question": prompt,
                "category": _normalize_category(question.get("category", "general")),
                "priority": question.get("priority", "medium"),
            }
        )

    # 1. Category questions.
    for question in CATEGORY_TEMPLATES.get(category_key, []):
        add(question)

    # 2. Feature questions, mapped from extractor labels and extra templates.
    for feature in detected_features:
        label = _normalize_feature(feature)
        bridged = FEATURE_TO_CATEGORY.get(label, category_key)

        if bridged != category_key:
            for question in CATEGORY_TEMPLATES.get(bridged, [])[:2]:
                add(question)

        for question in EXTRA_FEATURE_TEMPLATES.get(label, []):
            add(question)

    # 3. Quote the customer's own vague words.
    for question in _vague_term_questions(text):
        add(question)

    # 4. Missing non-functional dimensions.
    for dimension in DIMENSION_CHECKS:
        if not any(trigger in text_lower for trigger in dimension["triggers"]):
            add(dimension)

    # 5. High-complexity delivery questions.
    if complexity_score >= 3.5:
        add(
            {
                "question": "This feature has high complexity. Should it be broken into phases for delivery?",
                "category": "scope",
                "priority": "high",
            }
        )
        add(
            {
                "question": "Do you have the technical expertise in-house for this complexity level, or is external support needed?",
                "category": "planning",
                "priority": "medium",
            }
        )

    # 6. Always-useful project questions, added last so they only fill space.
    for question in GENERAL_QUESTIONS:
        add(question)

    priority_order = {"high": 0, "medium": 1, "low": 2}
    questions.sort(key=lambda item: priority_order.get(item["priority"], 2))

    return questions[:max_questions]
