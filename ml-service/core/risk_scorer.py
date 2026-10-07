

# Categories whose dominant failure modes are regulatory, financial or
# access-related rather than purely technical. A category is a better signal
# than keyword counting here, because the words triggering the risk often do
# not appear in the requirement text at all.
#
# Keys must stay in sync with the category vocabulary in
# training_data/requirements.json.
COMPLIANCE_CATEGORIES = {
    'e-commerce': (
        'Regulated Payment Handling',
        'Commerce features typically handle card data and order state, which is subject to PCI DSS and financial audit',
        'Complete a PCI DSS scope assessment. Prefer a certified payment provider over handling card data directly. Plan refund and dispute flows before launch.',
        1.0,
    ),
    'authentication': (
        'Access Control Exposure',
        'Authentication and authorization changes can expose every protected resource in the system',
        'Plan a security review and threat model. Enforce authorization server-side and add tests for privilege escalation paths.',
        0.8,
    ),
    'api': (
        'Breaking Contract Risk',
        'API surface changes can break existing consumers that cannot be updated in lockstep',
        'Define a versioning strategy before release. Document the contract and notify known consumers before removing or altering fields.',
        0.7,
    ),
    'integration': (
        'Third-Party Availability Dependency',
        'The deliverable depends on systems outside the team control',
        'Verify the third party API availability, documentation and rate limits. Plan for timeouts, retries and a degraded mode.',
        0.7,
    ),
    'ui_design': (
        'Accessibility Compliance',
        'User interface work is subject to accessibility standards and review',
        'State the target conformance level (for example WCAG 2.1 AA) and verify it with automated and manual testing before release.',
        0.5,
    ),
    'content_management': (
        'Untrusted Content Injection',
        'Author-supplied content is a stored XSS and injection vector when rendered',
        'Sanitize on render, set a strict content security policy, and review every place stored content is displayed.',
        0.7,
    ),
}


def assess_risk(
    text: str,
    complexity_score: float,
    feature_count: int,
    category: str,
) -> dict:
    risk_factors = []
    risk_score = 0.0
    text_lower = text.lower()

    compliance = COMPLIANCE_CATEGORIES.get(category)

    if compliance:
        factor, description, mitigation, weight = compliance
        risk_factors.append({
            'factor': factor,
            'level': 'high',
            'description': description,
            'mitigation': mitigation,
        })
        risk_score += weight

    if complexity_score >= 4.0:
        risk_factors.append({
            'factor': 'High Technical Complexity',
            'level': 'high',
            'description': f'Complexity score of {complexity_score}/5.0 indicates significant technical challenges',
            'mitigation': 'Break down into smaller, manageable tasks. Use iterative development approach.',
        })
        risk_score += 2.0
    elif complexity_score >= 3.0:
        risk_factors.append({
            'factor': 'Moderate Technical Complexity',
            'level': 'medium',
            'description': f'Complexity score of {complexity_score}/5.0 requires careful planning',
            'mitigation': 'Create detailed technical specifications before development.',
        })
        risk_score += 1.0

    scope_creep_indicators = [
        r'\b(and|also|additionally|plus|moreover|furthermore)\b',
        r'\b(maybe|perhaps|possibly|might|could|should)\b',
        r'\b(nice.?to.?have|stretch|future|later|phase\s*2)\b',
        r'\b(simple|just|easy|quick|basic)\b',
        r'\b(everything|all|complete|full|entire)\b',
    ]

    import re
    scope_signals = sum(1 for p in scope_creep_indicators if re.search(p, text_lower))
    if scope_signals >= 3:
        risk_factors.append({
            'factor': 'Scope Creep Risk',
            'level': 'high',
            'description': f'Found {scope_signals} vague or ambiguous scope indicators',
            'mitigation': 'Define clear acceptance criteria. Create a detailed scope document. Use MoSCoW prioritization.',
        })
        risk_score += 1.5
    elif scope_signals >= 1:
        risk_factors.append({
            'factor': 'Potential Scope Ambiguity',
            'level': 'medium',
            'description': 'Some requirements may benefit from more specificity',
            'mitigation': 'Clarify ambiguous terms with stakeholders. Document assumptions.',
        })
        risk_score += 0.5

    vague_words = ['etc', 'and so on', 'and more', 'something like', 'kind of', 'sort of', 'basically', 'probably']
    vague_count = sum(1 for w in vague_words if w in text_lower)
    if vague_count >= 2:
        risk_factors.append({
            'factor': 'Vague Requirements',
            'level': 'high',
            'description': f'Found {vague_count} vague terms that need clarification',
            'mitigation': 'Request detailed specifications. Create user stories with clear acceptance criteria.',
        })
        risk_score += 1.0
    elif vague_count >= 1:
        risk_factors.append({
            'factor': 'Minor Ambiguity',
            'level': 'low',
            'description': 'Some terms could be more specific',
            'mitigation': 'Clarify specific terms during requirements review.',
        })
        risk_score += 0.3

    security_terms = ['security', 'encrypt', 'auth', 'password', 'token', 'payment', 'personal', 'private', 'gdpr', 'hipaa', 'pci']
    security_count = sum(1 for t in security_terms if t in text_lower)
    if security_count >= 3:
        risk_factors.append({
            'factor': 'Security Requirements',
            'level': 'high',
            'description': f'Found {security_count} security-related terms - requires security review',
            'mitigation': 'Conduct security audit. Implement OWASP guidelines. Plan penetration testing.',
        })
        risk_score += 1.5
    elif security_count >= 1:
        risk_factors.append({
            'factor': 'Security Considerations',
            'level': 'medium',
            'description': 'Some security aspects detected',
            'mitigation': 'Follow security best practices. Review OWASP Top 10.',
        })
        risk_score += 0.5

    integration_terms = ['integrate', 'third-party', 'external', 'api', 'webhook', 'sdk', 'plugin']
    integration_count = sum(1 for t in integration_terms if t in text_lower)
    if integration_count >= 2:
        risk_factors.append({
            'factor': 'External Dependencies',
            'level': 'medium',
            'description': f'Detected {integration_count} external integration points',
            'mitigation': 'Verify API availability and documentation. Plan for API changes.',
        })
        risk_score += 0.8

    if feature_count >= 8:
        risk_factors.append({
            'factor': 'Large Feature Scope',
            'level': 'high',
            'description': f'{feature_count} features detected - risk of timeline overrun',
            'mitigation': 'Prioritize features using MoSCoW. Consider phased delivery.',
        })
        risk_score += 1.0
    elif feature_count >= 5:
        risk_factors.append({
            'factor': 'Moderate Feature Scope',
            'level': 'medium',
            'description': f'{feature_count} features detected - ensure proper planning',
            'mitigation': 'Create detailed project plan with milestones.',
        })
        risk_score += 0.5

    word_count = len(text.split())
    if word_count < 15:
        risk_factors.append({
            'factor': 'Insufficient Detail',
            'level': 'high',
            'description': 'Requirement description is too brief for accurate analysis',
            'mitigation': 'Request more detailed requirements. Include user stories and acceptance criteria.',
        })
        risk_score += 1.0

    risk_score = min(10.0, risk_score)

    if risk_score >= 7.0:
        overall_risk = 'critical'
    elif risk_score >= 5.0:
        overall_risk = 'high'
    elif risk_score >= 3.0:
        overall_risk = 'medium'
    else:
        overall_risk = 'low'

    return {
        'overall_risk': overall_risk,
        'risk_score': round(risk_score, 2),
        'risk_factors': risk_factors,
        'total_risk_factors': len(risk_factors),
    }
