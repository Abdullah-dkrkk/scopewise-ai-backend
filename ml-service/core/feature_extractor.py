import re

# Used when a requirement matches no known feature pattern at all, so the
# caller always receives at least one module and a non-zero estimate.
DEFAULT_BASE_HOURS = 4

FEATURE_PATTERNS = {
    'authentication': {
        'patterns': [
            r'\b(login|log\s*in|sign\s*in|signin)s?\b',
            r'\b(register|registration|signup|sign\s*up)s?\b',
            r'\b(password|passwd|pwd)s?\b',
            r'\b(reset|forgot|recover)\b.*\b(password|credential|account)s?\b',
            r'\b(email|e-mail)s?\b.*\b(verif(y|ication|ied)|confirm(ation)?)\b',
            r'\b(oauth2?|social\s*login|sso|saml)\b',
            r'\b(two[.\s-]?factor|2fa|mfa|otp|authenticator|one[.\s-]?time\s*code)s?\b',
            r'\b(session|token|jwt|bearer|magic\s*link)s?\b',
            r'\b(role|permission|rbac|access\s*control)s?\b',
        ],
        'feature_type': 'Authentication & Authorization',
        'base_hours': 8,
    },
    'user_management': {
        'patterns': [
            r'\b(user\s*profile|user\s*account|account\s*setting)s?\b',
            r'\b(profile|account)s?\b',
            r'\b(admin|administrator)s?\b',
            r'\b(avatar|profile\s*pic(ture)?)s?\b',
            r'\b(preference|setting|configuration)s?\b',
            r'\b(organisation|organization|tenant|team)s?\b',
        ],
        'feature_type': 'User Management',
        'base_hours': 6,
    },
    'e_commerce': {
        'patterns': [
            r'\b(product|catalog(ue)?|item|listing|store|shop)s?\b',
            r'\b(cart|shopping\s*cart|basket)s?\b',
            r'\b(checkout|payment|pay|purchase|buy|order)s?\b',
            r'\b(order\s*(history|tracking)?)s?\b',
            r'\b(inventor(y|ies)|stock|warehouse)s?\b',
            r'\b(shipping|delivery|dispatch|carrier)s?\b',
            r'\b(refund|return|exchange)s?\b',
            r'\b(coupon|discount|promo(tion)?|offer|voucher|gift\s*card)s?\b',
            r'\b(wishlist|wish\s*list|save\s*for\s*later)s?\b',
            r'\b(price|pricing|subscription|billing)s?\b',
        ],
        'feature_type': 'E-Commerce',
        'base_hours': 10,
    },
    'dashboard_analytics': {
        'patterns': [
            r'\b(dashboard|dashboard\s*widget|analytics|report)s?\b',
            r'\b(chart|graph|visuali[sz]ation|diagram)s?\b',
            r'\b(kpi|metric|indicator|benchmark|cohort)s?\b',
            r'\b(real.?time|live|streaming)\b.*\b(data|update|monitor|feed|order)s?\b',
            r'\b(export|download)\b.*\b(pdf|csv|excel|xlsx)\b',
            r'\b(anomal|drill[.\s-]?down|trend)s?\b',
        ],
        'feature_type': 'Dashboard & Analytics',
        'base_hours': 8,
    },
    'content_management': {
        'patterns': [
            r'\b(cms|content\s*management|content\s*system)s?\b',
            r'\b(blog|post|article|page)s?\b',
            r'\b(editor|wysiwyg|rich\s*text|markdown)s?\b',
            r'\b(media|image|video|file|document)s?\b.*\b(upload|library|manage|resiz|embed)\b',
            r'\b(seo|meta|sitemap|search\s*engine)s?\b',
            r'\b(multilingual|multi[.\s-]?language|translation|i18n|l10n)\b',
            r'\b(version|revision|draft|publish|approval)s?\b',
            r'\b(faq|documentation|comment)s?\b',
        ],
        'feature_type': 'Content Management',
        'base_hours': 10,
    },
    'search_filter': {
        'patterns': [
            r'\b(search|query|queries|find|lookup)s?\b',
            r'\b(filter|faceted|refine|drill)s?\b',
            r'\b(sort|order|rank)s?\b',
            r'\b(autocomplete|auto.?suggest|typeahead)s?\b',
            r'\b(pagination|paginate|page\s*number)s?\b',
        ],
        'feature_type': 'Search & Filtering',
        'base_hours': 5,
    },
    'notification': {
        'patterns': [
            r'\b(notification|notify|alert|reminder)s?\b',
            r'\b(email|e-mail|push|sms)\b.*\b(send|template|notification|alert|code|message)s?\b',
            r'\b(sms|text\s*message|whatsapp)s?\b',
            r'\b(push\s*notification|mobile\s*notification)s?\b',
            r'\b(in.?app|inbox|message\s*cent(er|re)|feed)s?\b',
        ],
        'feature_type': 'Notifications',
        'base_hours': 6,
    },
    'api_integration': {
        'patterns': [
            r'\b(api|rest|graphql|soap)s?\b',
            r'\b(webhook|callback|hook)s?\b',
            r'\b(integrat(e|ion)|connect(or)?|sy?nc)s?\b',
            r'\b(third.?party|external)\b.*\b(api|service|system|provider)s?\b',
            r'\b(sdk|client|gateway|endpoint)s?\b',
        ],
        'feature_type': 'API & Integration',
        'base_hours': 8,
    },
    'file_management': {
        'patterns': [
            r'\b(upload|downloading|download|uploading)s?\b',
            r'\b(file\s*management|file\s*system|file\s*manager)s?\b',
            r'\b(document|pdf|spreadsheet|image|photo|video)s?\b',
            r'\b(storage|cdn|blob|s3|bucket)s?\b',
            r'\b(chunked|resumable)\b.*\buploads?\b',
        ],
        'feature_type': 'File Management',
        'base_hours': 6,
    },
    'ui_components': {
        'patterns': [
            r'\b(form|form\s*builder|form\s*validation)s?\b',
            r'\b(table|data\s*table|grid|list)s?\b',
            r'\b(modal|dialog|popup|drawer|sidebar|overlay)s?\b',
            r'\b(tab|tabs|accordion|collapsible)s?\b',
            r'\b(button|toggle|switch|checkbox|radio)s?\b',
            r'\b(responsive|mobile|tablet|adaptive|dark\s*mode)s?\b',
            r'\b(wizard|stepper|multi.?step)s?\b',
            r'\b(drag.?and.?drop|sortable|reorder|carousel)s?\b',
            r'\b(accessib(le|ility)|wcag|skeleton|animation)s?\b',
        ],
        'feature_type': 'UI Components',
        'base_hours': 5,
    },
    'security': {
        'patterns': [
            r'\b(security|secure|protection|encrypt(ion)?|decrypt)s?\b',
            r'\b(ssl|tls|https|certificate)s?\b',
            r'\b(csrf|xss|sql\s*injection|injection|vulnerab(le|ility))s?\b',
            r'\b(rate\s*limit|throttl(e|ing)|brute\s*force)s?\b',
            r'\b(backup|restore|disaster\s*recovery)s?\b',
            r'\b(audit|activity\s*log|access\s*log)s?\b',
            r'\b(compliance|gdpr|hipaa|pci|kyc)s?\b',
        ],
        'feature_type': 'Security',
        'base_hours': 8,
    },
    'payment': {
        'patterns': [
            r'\b(payment|pay|checkout|billing|invoic(e|ing))s?\b',
            r'\b(card|credit\s*card|debit\s*card)s?\b',
            r'\b(stripe|paypal|braintree|square|razorpay)s?\b',
            r'\b(receipt|statement)s?\b',
            r'\b(subscription|recurring|plan|pricing|tier)s?\b',
            r'\b(refund|chargeback|dispute)s?\b',
            r'\b(currency|tax|vat|gst)s?\b',
        ],
        'feature_type': 'Payment Processing',
        'base_hours': 12,
    },
    'realtime': {
        'patterns': [
            r'\b(real.?time|live|instant|streaming)s?\b',
            r'\b(websocket|socket|sse|server.sent)s?\b',
            r'\b(chat|messaging|conversation|presence|typing)s?\b',
            r'\b(collaborat(e|ion)|concurrent|multi.?user)s?\b',
            r'\b(online\s*status|indicator)s?\b',
        ],
        'feature_type': 'Real-Time Features',
        'base_hours': 10,
    },
    'geolocation': {
        'patterns': [
            r'\b(map|mapping|google\s*map|leaflet|mapbox)s?\b',
            r'\b(geo|location|geolocation|geocod(e|ing))s?\b',
            r'\b(address\s*autocomplete|latitude|longitude|coordinates)s?\b',
            r'\b(route|routing|direction|navigation|itinerary)s?\b',
            r'\b(distance|radius|nearby|proximity)s?\b',
        ],
        'feature_type': 'Geolocation & Maps',
        'base_hours': 8,
    },
    'ai_ml': {
        'patterns': [
            r'\b(ai|artificial\s*intelligence|machine\s*learning|ml|llm)s?\b',
            r'\b(nlp|natural\s*language|text\s*analysis|sentiment|chatbot|intent)s?\b',
            r'\b(recommendation|recommend(er)?|personaliz(e|ation))s?\b',
            r'\b(classif(y|ication)|predict(ion)?|forecast|anomal(y|ies))s?\b',
            r'\b(neural|deep\s*learning|model|train(ing)?|dataset)s?\b',
        ],
        'feature_type': 'AI & Machine Learning',
        'base_hours': 15,
    },
}


def extract_features(text: str) -> dict:
    text_lower = text.lower()
    detected_features = []
    total_hours = 0

    for config in FEATURE_PATTERNS.values():
        matches = []
        for pattern in config['patterns']:
            found = re.findall(pattern, text_lower)
            if found:
                matches.extend(found)

        if matches:
            unique_matches = list(set(matches))
            estimated_hours = config['base_hours'] + (len(unique_matches) - 1) * 2

            detected_features.append({
                'feature_type': config['feature_type'],
                'matches': unique_matches[:5],
                'match_count': len(unique_matches),
                'estimated_hours': estimated_hours,
            })
            total_hours += estimated_hours

    detected_features.sort(key=lambda x: x['match_count'], reverse=True)

    total_modules = len(detected_features)
    if total_modules == 0:
        total_modules = 1
        total_hours = DEFAULT_BASE_HOURS

    return {
        'features': detected_features,
        'total_features': total_modules,
        'total_estimated_hours': total_hours,
        'feature_summary': [f['feature_type'] for f in detected_features],
    }
