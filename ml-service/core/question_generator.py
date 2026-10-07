

QUESTION_TEMPLATES = {
    'authentication': [
        {'question': 'What authentication methods do you need? (Email/Password, Social Login, SSO, 2FA)', 'category': 'authentication', 'priority': 'high'},
        {'question': 'What password policy should be enforced? (Min length, special chars, expiry)', 'category': 'authentication', 'priority': 'high'},
        {'question': 'Do you need role-based access control (RBAC)? What roles are required?', 'category': 'authentication', 'priority': 'high'},
        {'question': 'How should password reset work? (Email link, security questions, admin reset)', 'category': 'authentication', 'priority': 'medium'},
        {'question': 'Do you need session management features? (Concurrent sessions, session timeout)', 'category': 'authentication', 'priority': 'medium'},
    ],
'e_commerce': [
        {'question': 'What payment gateways should be integrated? (Stripe, PayPal, local methods)', 'category': 'payment', 'priority': 'high'},
        {'question': 'What product types will be sold? (Physical, digital, subscriptions, services)', 'category': 'e_commerce', 'priority': 'high'},
        {'question': 'Do you need multi-currency and tax calculation support?', 'category': 'e_commerce', 'priority': 'high'},
        {'question': 'What shipping and delivery options are required?', 'category': 'e_commerce', 'priority': 'medium'},
        {'question': 'Do you need inventory management with stock alerts?', 'category': 'e_commerce', 'priority': 'medium'},
        {'question': 'Should customers have wishlists and save-for-later functionality?', 'category': 'e_commerce', 'priority': 'low'},
    ],
    'dashboard': [
        {'question': 'What key metrics and KPIs should be displayed on the dashboard?', 'category': 'dashboard', 'priority': 'high'},
        {'question': 'Should the dashboard have real-time data updates? What refresh rate?', 'category': 'dashboard', 'priority': 'high'},
        {'question': 'What export formats are needed? (PDF, CSV, Excel, Print)', 'category': 'dashboard', 'priority': 'medium'},
        {'question': 'Do users need customizable dashboard layouts or widget arrangements?', 'category': 'dashboard', 'priority': 'medium'},
        {'question': 'What date range and filtering options should be available?', 'category': 'dashboard', 'priority': 'medium'},
    ],
    'api': [
        {'question': 'What authentication method should the API use? (JWT, API Key, OAuth)', 'category': 'api', 'priority': 'high'},
        {'question': 'What rate limiting requirements do you have?', 'category': 'api', 'priority': 'high'},
        {'question': 'Do you need API versioning? What versioning strategy? (URL, Header)', 'category': 'api', 'priority': 'medium'},
        {'question': 'What third-party APIs need to be integrated?', 'category': 'api', 'priority': 'high'},
        {'question': 'Do you need webhook support for event-driven integrations?', 'category': 'api', 'priority': 'medium'},
    ],
    'ui_design': [
        {'question': 'What devices and screen sizes must be supported? (Desktop, tablet, mobile)', 'category': 'ui_design', 'priority': 'high'},
        {'question': 'Should the UI support theming? (Light/dark mode, custom colors)', 'category': 'ui_design', 'priority': 'medium'},
        {'question': 'What accessibility standards must be met? (WCAG 2.1 Level A/AA)', 'category': 'ui_design', 'priority': 'high'},
        {'question': 'Do you need multi-language support? What languages?', 'category': 'ui_design', 'priority': 'medium'},
        {'question': 'What animation and transition effects are expected?', 'category': 'ui_design', 'priority': 'low'},
    ],
    'content_management': [
        {'question': 'What content types need to be managed? (Pages, blog posts, media, products)', 'category': 'content_management', 'priority': 'high'},
        {'question': 'Do you need a WYSIWYG editor or Markdown support?', 'category': 'content_management', 'priority': 'medium'},
        {'question': 'What SEO features are required? (Meta tags, sitemaps, canonical URLs)', 'category': 'content_management', 'priority': 'high'},
        {'question': 'Do you need content versioning and revision history?', 'category': 'content_management', 'priority': 'medium'},
        {'question': 'Is multi-language content management required?', 'category': 'content_management', 'priority': 'medium'},
    ],
    'marketing': [
        {'question': 'What email marketing features are needed? (Templates, scheduling, analytics)', 'category': 'marketing', 'priority': 'high'},
        {'question': 'Do you need A/B testing capabilities for campaigns?', 'category': 'marketing', 'priority': 'medium'},
        {'question': 'What analytics and tracking integrations are required?', 'category': 'marketing', 'priority': 'high'},
        {'question': 'Do you need social media integration and scheduling?', 'category': 'marketing', 'priority': 'medium'},
    ],
    'general': [
        {'question': 'What is the expected number of users/traffic for this feature?', 'category': 'general', 'priority': 'high'},
        {'question': 'Are there any performance requirements? (Response time, throughput)', 'category': 'general', 'priority': 'high'},
        {'question': 'What browser and device compatibility is required?', 'category': 'general', 'priority': 'medium'},
        {'question': 'Do you need audit logging for this feature?', 'category': 'general', 'priority': 'medium'},
        {'question': 'What testing coverage is expected? (Unit, integration, e2e)', 'category': 'general', 'priority': 'medium'},
    ],
    'integration': [
        {'question': 'What external systems need to be integrated?', 'category': 'integration', 'priority': 'high'},
        {'question': 'Is real-time data synchronization required between systems?', 'category': 'integration', 'priority': 'high'},
        {'question': 'What happens when the external system is unavailable? (Fallback, retry, queue)', 'category': 'integration', 'priority': 'high'},
        {'question': 'Do you need data transformation between different formats?', 'category': 'integration', 'priority': 'medium'},
    ],
}

GENERAL_QUESTIONS = [
    {'question': 'What is the target launch date for this feature/project?', 'category': 'timeline', 'priority': 'high'},
    {'question': 'What is the estimated team size and composition?', 'category': 'planning', 'priority': 'high'},
    {'question': 'Are there any dependencies on other features or teams?', 'category': 'dependencies', 'priority': 'high'},
    {'question': 'What are the acceptance criteria for this requirement?', 'category': 'scope', 'priority': 'high'},
    {'question': 'Should we consider mobile responsiveness for this feature?', 'category': 'ui_design', 'priority': 'medium'},
    {'question': 'Do you need email notifications for user actions in this feature?', 'category': 'notification', 'priority': 'medium'},
]


def generate_questions(
    text: str,
    category: str,
    complexity_score: float,
    detected_features: list[str],
) -> list[dict]:
    questions = []
    text_lower = text.lower()

    # The trained model emits corpus labels verbatim, where e-commerce keeps
    # its hyphen. Question templates key on the underscore form, so normalise
    # both the category and every feature key before matching.
    category_key = category.replace('-', '_')

    if category_key in QUESTION_TEMPLATES:
        for q in QUESTION_TEMPLATES[category_key]:
            if not any(kw in text_lower for kw in _get_skip_keywords(q['category'])):
                questions.append(q)

    for feature in detected_features:
        feature_key = feature.lower().replace(' & ', '_').replace(' ', '_').replace('-', '_')
        if feature_key in QUESTION_TEMPLATES and feature_key != category_key:
            for q in QUESTION_TEMPLATES[feature_key][:2]:
                if not any(eq['question'] == q['question'] for eq in questions):
                    questions.append(q)

    if complexity_score >= 3.5:
        questions.append({
            'question': 'This feature has high complexity. Should it be broken into phases for delivery?',
            'category': 'scope',
            'priority': 'high',
        })
        questions.append({
            'question': 'Do you have the technical expertise in-house for this complexity level, or is external support needed?',
            'category': 'planning',
            'priority': 'medium',
        })

    for gq in GENERAL_QUESTIONS[:3]:
        if not any(eq['question'] == gq['question'] for eq in questions):
            questions.append(gq)

    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    questions.sort(key=lambda x: priority_order.get(x['priority'], 2))

    seen = set()
    unique_questions = []
    for q in questions:
        if q['question'] not in seen:
            seen.add(q['question'])
            unique_questions.append(q)

    return unique_questions[:15]


def _get_skip_keywords(category: str) -> list[str]:
    skip_map = {
        'authentication': ['login', 'password', 'register', 'oauth', 'token', 'auth'],
        'payment': ['payment', 'pay', 'checkout', 'stripe', 'paypal', 'billing'],
        'dashboard': ['dashboard', 'chart', 'graph', 'report', 'analytics'],
        'api': ['api', 'rest', 'graphql', 'webhook', 'endpoint'],
        'ui_design': ['responsive', 'mobile', 'design', 'theme', 'dark mode', 'layout'],
        'content_management': ['blog', 'cms', 'editor', 'content', 'page'],
        'e_commerce': ['product', 'cart', 'order', 'shipping', 'inventory'],
        'marketing': ['email', 'campaign', 'seo', 'marketing'],
        'integration': ['integrate', 'integration', 'third-party', 'external', 'api'],
        'notification': ['notification', 'email', 'sms', 'push', 'alert'],
        'scope': ['scope', 'deadline', 'launch', 'date', 'timeline'],
        'planning': ['team', 'size', 'planning', 'resource'],
        'timeline': ['deadline', 'launch', 'date', 'timeline', 'schedule'],
        'dependencies': ['depend', 'prerequisite', 'blocker', 'dependent'],
        'general': [],
    }
    return skip_map.get(category, [])
