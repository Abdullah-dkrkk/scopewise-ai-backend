import re

# Used when a requirement matches no known feature pattern at all, so the
# caller always receives at least one module and a non-zero estimate.
DEFAULT_BASE_HOURS = 4

FEATURE_PATTERNS = {
    'authentication': {
        'patterns': [
            r'\b(login|log\s*in|sign\s*in|signin)\b',
            r'\b(register|registration|signup|sign\s*up)\b',
            r'\b(password|passwd|pwd)\b',
            r'\b(reset|forgot)\b.*\b(password|credential)\b',
            r'\b(email|e-mail)\b.*\b(verify|verification|confirm)\b',
            r'\b(social\s*login|oauth|google|github|facebook|twitter)\b',
            r'\b(two.?factor|2fa|otp|sms.*code|email.*code)\b',
            r'\b(session|token|jwt|bearer)\b',
            r'\b(role|permission|rbac|access\s*control)\b',
        ],
        'feature_type': 'Authentication & Authorization',
        'base_hours': 8,
    },
    'user_management': {
        'patterns': [
            r'\b(user\s*profile|user\s*account|account\s*settings)\b',
            r'\b(admin|administrator)\b',
            r'\b(role|permission|access)\b',
            r'\b(user\s*list|user\s*management|manage\s*users)\b',
            r'\b(avatar|profile\s*pic|profile\s*picture)\b',
            r'\b(preferences|settings|config)\b',
        ],
        'feature_type': 'User Management',
        'base_hours': 6,
    },
    'e_commerce': {
        'patterns': [
            r'\b(product|catalog|item|listing)\b',
            r'\b(cart|shopping\s*cart|basket)\b',
            r'\b(checkout|payment|pay|purchase|buy)\b',
            r'\b(order|order\s*history|order\s*tracking)\b',
            r'\b(inventory|stock|warehouse)\b',
            r'\b(shipping|delivery|dispatch)\b',
            r'\b(refund|return|exchange)\b',
            r'\b(coupon|discount|promo|offer)\b',
            r'\b(wishlist|wish\s*list|save\s*for\s*later)\b',
        ],
        'feature_type': 'E-Commerce',
        'base_hours': 10,
    },
    'dashboard_analytics': {
        'patterns': [
            r'\b(dashboard|dashboard\s*widget)\b',
            r'\b(chart|graph|visualization|diagram)\b',
            r'\b(report|analytics|statistics|stats)\b',
            r'\b(kpi|metric|indicator|benchmark)\b',
            r'\b(real.?time|live|streaming)\b.*\b(data|update|monitor)\b',
            r'\b(export|download)\b.*\b(pdf|csv|excel|xlsx)\b',
        ],
        'feature_type': 'Dashboard & Analytics',
        'base_hours': 8,
    },
    'content_management': {
        'patterns': [
            r'\b(cms|content\s*management|content\s*system)\b',
            r'\b(blog|post|article|page)\b',
            r'\b(editor|wysiwyg|rich\s*text|markdown)\b',
            r'\b(media|image|video|file)\b.*\b(upload|library|manage)\b',
            r'\b(seo|meta|sitemap|search\s*engine)\b',
            r'\b(multilingual|translation|language|i18n|l10n)\b',
            r'\b(version|revision|draft|publish)\b',
        ],
        'feature_type': 'Content Management',
        'base_hours': 10,
    },
    'search_filter': {
        'patterns': [
            r'\b(search|query|find|lookup)\b',
            r'\b(filter|faceted|refine)\b',
            r'\b(sort|order|rank)\b',
            r'\b(autocomplete|auto.?suggest|typeahead)\b',
            r'\b(pagination|paginate|page\s*number)\b',
        ],
        'feature_type': 'Search & Filtering',
        'base_hours': 5,
    },
    'notification': {
        'patterns': [
            r'\b(notification|notify|alert|reminder)\b',
            r'\b(email|e-mail)\b.*\b(send|template|notification)\b',
            r'\b(sms|text\s*message)\b',
            r'\b(push\s*notification|mobile\s*notification)\b',
            r'\b(in.?app|inbox|message\s*center)\b',
        ],
        'feature_type': 'Notifications',
        'base_hours': 6,
    },
    'api_integration': {
        'patterns': [
            r'\b(api|rest|graphql|soap)\b',
            r'\b(webhook|callback|hook)\b',
            r'\b(integration|integrate|connect)\b',
            r'\b(third.?party|external)\b.*\b(api|service|system)\b',
            r'\b(sdk|library|client)\b',
        ],
        'feature_type': 'API & Integration',
        'base_hours': 8,
    },
    'file_management': {
        'patterns': [
            r'\b(upload|uploading)\b',
            r'\b(download|downloading)\b',
            r'\b(file\s*management|file\s*system|file\s*manager)\b',
            r'\b(document|doc|pdf|spreadsheet)\b',
            r'\b(image|photo|picture|video|media)\b',
            r'\b(storage|cdn|blob|s3|aws)\b',
        ],
        'feature_type': 'File Management',
        'base_hours': 6,
    },
    'ui_components': {
        'patterns': [
            r'\b(form|form\s*builder|form\s*validation)\b',
            r'\b(table|data\s*table|grid|list)\b',
            r'\b(modal|dialog|popup|drawer|sidebar)\b',
            r'\b(tab|tabs|accordion|collapsible)\b',
            r'\b(button|toggle|switch|checkbox|radio)\b',
            r'\b(responsive|mobile|tablet|adaptive)\b',
            r'\b(wizard|stepper|multi.?step)\b',
            r'\b(drag.?and.?drop|sortable|reorder)\b',
        ],
        'feature_type': 'UI Components',
        'base_hours': 5,
    },
    'security': {
        'patterns': [
            r'\b(security|secure|protection)\b',
            r'\b(encrypt|decrypt|cipher)\b',
            r'\b(ssl|tls|https|certificate)\b',
            r'\b(csrf|xss|sql\s*injection|injection)\b',
            r'\b(rate\s*limit|throttl|brute\s*force)\b',
            r'\b(backup|restore|disaster\s*recovery)\b',
            r'\b(audit|audit\s*log|activity\s*log)\b',
            r'\b(compliance|gdpr|hipaa|pci)\b',
        ],
        'feature_type': 'Security',
        'base_hours': 8,
    },
    'payment': {
        'patterns': [
            r'\b(payment|pay|checkout|billing)\b',
            r'\b(stripe|paypal|braintree|square)\b',
            r'\b(invoice|receipt|billing)\b',
            r'\b(subscription|recurring|plan|pricing)\b',
            r'\b(refund|chargeback|dispute)\b',
            r'\b(currency|tax|vat|gst)\b',
        ],
        'feature_type': 'Payment Processing',
        'base_hours': 12,
    },
    'realtime': {
        'patterns': [
            r'\b(real.?time|live|instant|streaming)\b',
            r'\b(websocket|socket|sse|server.sent)\b',
            r'\b(chat|messaging|conversation)\b',
            r'\b(collaborat|multi.?user|concurrent)\b',
            r'\b(typing\s*indicator|online\s*status|presence)\b',
        ],
        'feature_type': 'Real-Time Features',
        'base_hours': 10,
    },
    'geolocation': {
        'patterns': [
            r'\b(map|mapping|google\s*map|leaflet|mapbox)\b',
            r'\b(geo|location|geolocation|geocod)\b',
            r'\b(address|autocomplete|places)\b',
            r'\b(route|routing|direction|navigation)\b',
            r'\b(distance|radius|nearby|proximity)\b',
        ],
        'feature_type': 'Geolocation & Maps',
        'base_hours': 8,
    },
    'ai_ml': {
        'patterns': [
            r'\b(ai|artificial\s*intelligence|machine\s*learning|ml)\b',
            r'\b(nlp|natural\s*language|text\s*analysis|sentiment)\b',
            r'\b(recommendation|suggest|personaliz)\b',
            r'\b(classif|predict|forecast|anomal)\b',
            r'\b(chatbot|virtual\s*assistant|voice)\b',
            r'\b(neural|deep\s*learning|model|train)\b',
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
