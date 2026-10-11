"""Generate the large, realistic training corpus for the ML pipeline.

The corpus is a deterministic mix of three data tiers:

1. ``seed``       - the hand-written entries already in requirements.json
                   (kept untouched on regeneration).
2. ``user``       - requirement texts real users submitted through the product
                   (captured from the production database, labelled by hand).
3. ``generated``  - combinatorial compositions over per-category feature
                   vocabularies. Labels are derived from the same deterministic
                   feature/hours rules the inference path uses, so the model
                   learns a consistent mapping instead of noise.

Regenerate with ``python scripts/generate_corpus.py``. The output is committed,
so training is reproducible without ever needing this script at runtime.

Complexity and hours for generated rows are *derived*, not guessed:
    complexity  = clamp(base + 0.25*(groups-1) + risk_bump, 1, 5)
    hours       = sum(group_base_hours) * mult(scope) * jitter
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from core.paths import REQUIREMENTS_DATA_PATH  # noqa: E402

DEFAULT_PER_CATEGORY = 520
RNG_SEED = 42

# Requirements captured from real usage of the product. Labelled by hand.
REAL_USER_REQUIREMENTS = [
    {
        "text": "User authentication system with login, registration, password reset, and email verification. Social login with Google and GitHub OAuth.",
        "category": "authentication",
        "complexity": 3.2,
        "hours": 45,
        "source": "user",
    },
    {
        "text": "As a user I want to pay for my order with a credit card and receive an emailed invoice, with the order status shown live on the dashboard.",
        "category": "e-commerce",
        "complexity": 3.6,
        "hours": 50,
        "source": "user",
    },
    {
        "text": "I need a website for my clothing business. We sell men's and women's clothes online. The website should look modern and professional and customers should be able to browse products and place orders. We also want customers to create accounts and receive notifications about their orders. There should be a payment system and the website should work well on mobile. We already have some product images and information. The website should be fast and SEO friendly. We would like to launch it as soon as possible.",
        "category": "e-commerce",
        "complexity": 4.0,
        "hours": 90,
        "source": "user",
    },
    {
        "text": "We need an online store for our cosmetics company. Customers should be able to browse products by category and search for products. Each product can have different sizes and colors. Users should be able to register, login, add products to their cart and checkout. We want online payments and cash on delivery. Customers should also be able to track their orders. The admin should be able to add and edit products, manage orders, view customers and create discount codes. We also want reviews, wishlist functionality and email notifications. The website should be responsive and optimized for Google.",
        "category": "e-commerce",
        "complexity": 4.5,
        "hours": 110,
        "source": "user",
    },
    {
        "text": "make it fast sort of like a shop and stuff",
        "category": "e-commerce",
        "complexity": 2.5,
        "hours": 18,
        "source": "user",
    },
    {
        "text": "Users should be able to reset their password via email within 5 minutes and the reset link must expire after 30 minutes.",
        "category": "authentication",
        "complexity": 2.0,
        "hours": 15,
        "source": "user",
    },
]

# Phrase openers that make generated requirements read like real customers.
OPENERS = [
    "",
    "",
    "",
    "We need ",
    "We need to build ",
    "We want ",
    "The system should have ",
    "The product should include ",
    "As a user I want ",
    "The application must support ",
    "Please build ",
]

FOLLOW_UPS = [
    "",
    "",
    "",
    "",
    "",
    " and it should be fast and secure.",
    " and everything must work well on mobile.",
    " and it should be SEO friendly.",
    " and we need it to scale as we grow.",
    " and the UX should feel modern.",
    " and it needs to be fully responsive.",
    " and we want clear analytics so we can improve it.",
]

# Per-category feature groups. Each group lists several phrasings that all
# reference the vocabulary the deterministic extractor can see.
CATEGORY_GROUPS: dict[str, list[dict]] = {
    "authentication": [
        {
            "name": "login & registration",
            "complexity": 2.0,
            "hours": 18,
            "phrases": [
                "a login and registration system",
                "user sign up and log in with email",
                "account creation and sign in pages",
                "user accounts where people can sign up and log in",
                "registration and authentication for users",
            ],
        },
        {
            "name": "password reset",
            "complexity": 1.8,
            "hours": 12,
            "phrases": [
                "password reset via email link",
                "forgot password flow that emails a reset link",
                "password recovery with emailed reset codes",
                "reset password link sent by email with expiry",
            ],
        },
        {
            "name": "email verification",
            "complexity": 1.8,
            "hours": 12,
            "phrases": [
                "email verification on signup",
                "verify email addresses with a confirmation email",
                "email confirmation links for new accounts",
            ],
        },
        {
            "name": "social login",
            "complexity": 2.4,
            "hours": 18,
            "phrases": [
                "social login with Google and GitHub OAuth",
                "sign in with Google OAuth and Facebook",
                "OAuth login with Google, Apple and Twitter",
                "social authentication providers like Google",
            ],
        },
        {
            "name": "2fa & security",
            "complexity": 3.2,
            "hours": 28,
            "phrases": [
                "two-factor authentication with SMS OTP",
                "2FA using an authenticator app and backup codes",
                "MFA with one-time codes sent by email",
                "two step verification for logins",
            ],
        },
        {
            "name": "sessions & roles",
            "complexity": 3.0,
            "hours": 26,
            "phrases": [
                "JWT token based authentication with refresh tokens",
                "session management with token revocation",
                "role based access control with permissions",
                "RBAC with admin and moderator roles",
                "permission levels for teams and admins",
            ],
        },
    ],
    "e-commerce": [
        {
            "name": "catalog & products",
            "complexity": 2.4,
            "hours": 30,
            "phrases": [
                "a product catalog with categories and filters",
                "product listings with sizes, colors and variants",
                "browse products by category with search",
                "an online store catalog with product pages",
            ],
        },
        {
            "name": "cart & checkout",
            "complexity": 2.8,
            "hours": 30,
            "phrases": [
                "shopping cart with add, remove and quantity update",
                "cart that persists between sessions",
                "checkout flow with guest ordering",
                "a shopping basket and checkout page",
            ],
        },
        {
            "name": "payments",
            "complexity": 3.8,
            "hours": 48,
            "phrases": [
                "payment integration with Stripe and PayPal",
                "online payments via credit card and digital wallets",
                "checkout with major payment gateways",
                "accept payments with Stripe webhooks",
                "cash on delivery and online payment options",
            ],
        },
        {
            "name": "orders & tracking",
            "complexity": 3.0,
            "hours": 36,
            "phrases": [
                "order management with status tracking",
                "order history and live order tracking",
                "customer orders with email notifications on status change",
                "an admin area to manage and fulfil orders",
            ],
        },
        {
            "name": "inventory & discounts",
            "complexity": 3.2,
            "hours": 40,
            "phrases": [
                "inventory management with low stock alerts",
                "automatic reorder when stock runs low",
                "discount codes and promo vouchers",
                "coupons, gift cards and special offers",
            ],
        },
        {
            "name": "reviews & wishlist",
            "complexity": 2.2,
            "hours": 24,
            "phrases": [
                "product reviews and star ratings",
                "a wishlist so users can save items",
                "ratings and customer reviews on products",
            ],
        },
        {
            "name": "marketplace",
            "complexity": 4.4,
            "hours": 110,
            "phrases": [
                "a multi-vendor marketplace with seller dashboards",
                "marketplace with commission splitting between vendors",
                "multi-seller platform with seller approval and payouts",
            ],
        },
    ],
    "dashboard": [
        {
            "name": "charts & widgets",
            "complexity": 2.6,
            "hours": 28,
            "phrases": [
                "an admin dashboard with charts and graphs",
                "kanban style widgets on a live dashboard",
                "dashboards with chart widgets and KPIs",
                "dashboard widgets for metrics and trends",
            ],
        },
        {
            "name": "real-time",
            "complexity": 3.8,
            "hours": 52,
            "phrases": [
                "real-time dashboard with live data streaming",
                "WebSocket updates that auto refresh the dashboard",
                "live sales analytics refreshed in real time",
                "a real time dashboard with streaming metrics",
            ],
        },
        {
            "name": "reports",
            "complexity": 2.8,
            "hours": 34,
            "phrases": [
                "analytics reports with date range filtering",
                "exports of reports to PDF and CSV",
                "sales analytics report generator",
                "custom reports with export options",
            ],
        },
        {
            "name": "custom builders",
            "complexity": 4.2,
            "hours": 80,
            "phrases": [
                "a custom report builder with drag and drop chart components",
                "no-code dashboard builder where users pick widgets",
                "build your own chart dashboards",
            ],
        },
        {
            "name": "kpi tracking",
            "complexity": 2.4,
            "hours": 24,
            "phrases": [
                "KPI tracking with goals and progress indicators",
                "metric scores compared against targets",
                "track revenue and conversion KPIs over time",
            ],
        },
    ],
    "api": [
        {
            "name": "rest endpoints",
            "complexity": 2.6,
            "hours": 30,
            "phrases": [
                "RESTful API with CRUD operations",
                "a REST API for the core entities",
                "JSON API endpoints with full CRUD",
            ],
        },
        {
            "name": "auth & rate limiting",
            "complexity": 3.0,
            "hours": 32,
            "phrases": [
                "API authentication with tokens and rate limiting",
                "API keys, throttling and usage quotas",
                "authentication and rate limits on every endpoint",
            ],
        },
        {
            "name": "graphql",
            "complexity": 3.8,
            "hours": 60,
            "phrases": [
                "GraphQL API with nested queries and mutations",
                "GraphQL subscriptions for live updates",
                "a GraphQL gateway over the existing services",
            ],
        },
        {
            "name": "webhooks",
            "complexity": 3.2,
            "hours": 40,
            "phrases": [
                "webhook delivery with retries and event routing",
                "outgoing webhooks with signed payloads",
                "webhook subscriptions and delivery status logs",
            ],
        },
        {
            "name": "integrations",
            "complexity": 3.8,
            "hours": 52,
            "phrases": [
                "integration with Salesforce CRM for contact sync",
                "third-party API integration with customer relationship management",
                "sync data with external systems via their APIs",
                "connect the app to stripe, zapier and slack",
            ],
        },
    ],
    "ui_design": [
        {
            "name": "landing page",
            "complexity": 1.4,
            "hours": 14,
            "phrases": [
                "a responsive landing page with hero section",
                "marketing landing page with features and testimonials",
                "a single page site with pricing and FAQ",
            ],
        },
        {
            "name": "forms & wizard",
            "complexity": 2.4,
            "hours": 26,
            "phrases": [
                "a multi-step wizard form with validation",
                "forms with inline validation and progress bar",
                "wizard style onboarding with draft save",
            ],
        },
        {
            "name": "component library",
            "complexity": 2.8,
            "hours": 34,
            "phrases": [
                "a reusable UI components library",
                "design system with buttons, tables, modals and tabs",
                "a component kit with dark mode support",
            ],
        },
        {
            "name": "file upload widgets",
            "complexity": 3.0,
            "hours": 34,
            "phrases": [
                "drag and drop file upload with preview",
                "chunked upload with a progress bar",
                "upload widget supporting images and documents",
            ],
        },
        {
            "name": "chat interface",
            "complexity": 3.8,
            "hours": 56,
            "phrases": [
                "a real-time chat interface with message history",
                "chat UI with file sharing and typing indicators",
                "a support chat window with threaded conversations",
            ],
        },
        {
            "name": "notification center",
            "complexity": 3.2,
            "hours": 44,
            "phrases": [
                "a notification center with email, SMS and push channels",
                "in-app notifications with read and unread state",
                "notification preferences and digest emails",
            ],
        },
    ],
    "content_management": [
        {
            "name": "blog & articles",
            "complexity": 2.4,
            "hours": 30,
            "phrases": [
                "a blog with rich text editor and tags",
                "articles with categories and author pages",
                "news and posts managed by an editor",
            ],
        },
        {
            "name": "page builder",
            "complexity": 4.2,
            "hours": 90,
            "phrases": [
                "a CMS page builder with drag and drop blocks",
                "visual page editor with templates",
                "a landing page builder for the marketing team",
            ],
        },
        {
            "name": "versioning & workflow",
            "complexity": 3.8,
            "hours": 72,
            "phrases": [
                "content versioning with edit history",
                "draft, review and approval workflow",
                "publish scheduling with status tracking",
            ],
        },
        {
            "name": "media library",
            "complexity": 3.4,
            "hours": 60,
            "phrases": [
                "a media library with image optimization",
                "video uploads with transcoding and CDN delivery",
                "manage images and files in a central library",
            ],
        },
        {
            "name": "multilingual",
            "complexity": 3.8,
            "hours": 70,
            "phrases": [
                "multilingual content with translation workflow",
                "i18n and l10n with localized pages",
                "multi-language site with translator roles",
            ],
        },
        {
            "name": "seo tooling",
            "complexity": 2.6,
            "hours": 30,
            "phrases": [
                "SEO fields with meta tags and sitemaps",
                "SEO friendly URLs and auto sitemap generation",
                "on-page SEO tools and structured data",
            ],
        },
    ],
    "marketing": [
        {
            "name": "email campaigns",
            "complexity": 3.6,
            "hours": 60,
            "phrases": [
                "email marketing with a drag and drop template builder",
                "campaign scheduling and email analytics",
                "automated email drips and A/B subject lines",
            ],
        },
        {
            "name": "seo audit",
            "complexity": 4.0,
            "hours": 80,
            "phrases": [
                "an SEO audit tool with keyword analysis",
                "backlink checker with recommendations",
                "SEO health reports and site crawl",
            ],
        },
        {
            "name": "social scheduler",
            "complexity": 3.8,
            "hours": 66,
            "phrases": [
                "social media scheduling with a content calendar",
                "queue posts to Instagram, LinkedIn and X",
                "social analytics and best-time-to-post signals",
            ],
        },
        {
            "name": "landing & analytics",
            "complexity": 3.0,
            "hours": 46,
            "phrases": [
                "tracking pixels and conversion analytics",
                "marketing funnel and lead attribution dashboards",
                "A/B tests for landing page copy",
            ],
        },
        {
            "name": "newsletter",
            "complexity": 2.4,
            "hours": 26,
            "phrases": [
                "a newsletter system with subscription forms",
                "segmented email lists and unsubscribes",
                "weekly newsletter with open and click stats",
            ],
        },
    ],
    "integration": [
        {
            "name": "crm sync",
            "complexity": 3.6,
            "hours": 52,
            "phrases": [
                "two-way sync with a CRM like Salesforce",
                "push contacts into HubSpot automatically",
                "keep customer data in sync with the CRM",
            ],
        },
        {
            "name": "erp & accounting",
            "complexity": 4.0,
            "hours": 70,
            "phrases": [
                "integration with ERP systems like SAP",
                "invoices pushed to Xero and QuickBooks",
                "accounting sync for orders and payments",
            ],
        },
        {
            "name": "communication",
            "complexity": 3.0,
            "hours": 42,
            "phrases": [
                "Slack notifications for key events",
                "send messages through WhatsApp Business API",
                "integrate live chat and email tools",
            ],
        },
        {
            "name": "data pipelines",
            "complexity": 3.8,
            "hours": 58,
            "phrases": [
                "ETL pipeline importing data from external systems",
                "scheduled jobs that fetch third-party data",
                "export data to warehouses like Snowflake",
            ],
        },
        {
            "name": "payment connectors",
            "complexity": 3.8,
            "hours": 56,
            "phrases": [
                "connect our checkout to Stripe via webhooks",
                "payment providers integration with reconciliation",
                "payouts and settlement sync from the payment gateway",
            ],
        },
    ],
    "general": [
        {
            "name": "business site",
            "complexity": 1.4,
            "hours": 18,
            "phrases": [
                "a professional website for our company",
                "something to show our services online",
                "improve our online presence",
            ],
        },
        {
            "name": "internal tool",
            "complexity": 1.8,
            "hours": 22,
            "phrases": [
                "an internal tool to reduce our manual work",
                "a small app to organize our daily tasks",
                "help desk system for our team",
            ],
        },
        {
            "name": "misc improvements",
            "complexity": 1.6,
            "hours": 16,
            "phrases": [
                "make our current system better",
                "fix the things that are slow and annoying",
                "upgrade our existing platform",
                "modernize our legacy software",
            ],
        },
        {
            "name": "unknown scope",
            "complexity": 2.0,
            "hours": 20,
            "phrases": [
                "we will figure out the details later",
                "start with the basics and we can add more later",
                "do it however you think is best",
            ],
        },
    ],
}

CONNECTOR_BETWEEN = [" and ", ", and ", ", plus ", ". It also needs ", "; moreover, "]
CONNECTOR_LAST = [" and ", " plus ", ", plus we need ", ", along with ", ". Finally, we need "]


def _derive_complexity(groups: list[dict]) -> float:
    base = max(g["complexity"] for g in groups)
    scope = 0.25 * (len(groups) - 1)
    bump = 0.3 if any(g["complexity"] >= 4.0 for g in groups) else 0.0
    return round(min(5.0, base + scope + bump), 1)


def _derive_hours(groups: list[dict], rng: random.Random) -> float:
    total = sum(g["hours"] for g in groups)
    scope_mult = 1.0 + 0.12 * (len(groups) - 1)
    jitter = rng.uniform(0.92, 1.08)
    hours = total * scope_mult * jitter
    return round(max(6.0, hours), 1)


def _make_statement(groups: list[dict], rng: random.Random) -> str:
    parts = [rng.choice(g["phrases"]) for g in groups]

    if len(parts) == 1:
        sentence = parts[0]
    else:
        connector = rng.choice(CONNECTOR_BETWEEN)
        sentence = connector.join(parts)

    opener = rng.choice(OPENERS)
    sentence = opener + sentence if opener else sentence[0].upper() + sentence[1:]

    follow_up = rng.choice(FOLLOW_UPS)
    if follow_up and not sentence.rstrip().endswith("."):
        sentence += follow_up

    sentence = sentence.strip()
    if not sentence.endswith("."):
        sentence += "."

    return sentence


def _generate_corpus(rng: random.Random, per_category: int) -> list[dict]:
    rows: list[dict] = []

    for category, groups in CATEGORY_GROUPS.items():
        for _ in range(per_category):
            n_groups = rng.choices([1, 2, 3, 4], weights=[25, 40, 25, 10])[0]
            chosen = rng.sample(groups, min(n_groups, len(groups)))

            # ~15% of samples blend one group from a second category to teach
            # the classifier to pick the dominant domain.
            if rng.random() < 0.15:
                others = [(c, g) for c, g in CATEGORY_GROUPS.items() if c != category]
                _, extra_groups = rng.choice(others)
                extra = rng.choice(extra_groups)

                chosen = chosen[:-1] + [extra] if len(chosen) >= 2 else chosen + [extra]

            text = _make_statement(chosen, rng)

            rows.append(
                {
                    "text": text,
                    "category": category,
                    "complexity": _derive_complexity(chosen),
                    "hours": _derive_hours(chosen, rng),
                    "source": "generated",
                }
            )

    # Plain business-speak that must land in "general".
    general_phrases = [
        "we need a new website for the team",
        "help us grow the business online",
        "something to organize our customer conversations",
        "a simple portal for our clients",
        "we want to automate some of our paperwork",
        "build us a tool to manage the daily operations",
        "an app for tracking the office requests",
        "visualize our goals for the quarter",
    ]
    for phrase in general_phrases:
        rows.append(
            {
                "text": phrase,
                "category": "general",
                "complexity": 1.5,
                "hours": 20,
                "source": "generated",
            }
        )

    return rows


def main() -> int:
    per_category = DEFAULT_PER_CATEGORY
    if "--per-category" in sys.argv:
        per_category = int(sys.argv[sys.argv.index("--per-category") + 1])

    rng = random.Random(RNG_SEED)  # noqa: S311 - deterministic seed for reproducible data, not security

    if REQUIREMENTS_DATA_PATH.exists():
        with REQUIREMENTS_DATA_PATH.open(encoding="utf-8") as handle:
            seed = json.load(handle)
    else:
        seed = []

    generated = _generate_corpus(rng, per_category)

    corpus = list(seed) + list(REAL_USER_REQUIREMENTS) + list(generated)

    seen: set[str] = set()
    deduped = []
    for row in corpus:
        key = row["text"].strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    with REQUIREMENTS_DATA_PATH.open("w", encoding="utf-8") as handle:
        json.dump(deduped, handle, ensure_ascii=False, indent=1)

    counts: dict[str, int] = {}
    for row in deduped:
        counts[row["category"]] = counts.get(row["category"], 0) + 1

    print(f"Wrote {len(deduped)} requirements to {REQUIREMENTS_DATA_PATH}")
    for category in sorted(counts):
        print(f"  {category:<22}{counts[category]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
