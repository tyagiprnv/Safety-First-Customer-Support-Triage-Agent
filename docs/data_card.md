# Data Card: Knowledge Base and Test Set

This document provides provenance and composition details for all data used in this project.

---

## Knowledge Base

### Overview
The knowledge base consists of policy documents and FAQs used for RAG (Retrieval-Augmented Generation) responses.

**Total Documents:** ~30-40 chunks after processing
**Sources:** Public SaaS policy templates, rewritten for this demo
**Language:** English only
**Last Updated:** January 2024

---

### Policy Documents

#### 1. Billing Policy (`billing_policy.md`)
- **Source:** Inspired by Stripe and Shopify billing policies
- **Methodology:** Rewritten from scratch, no copy-paste
- **Content:** Billing cycle, payment methods, invoice access, dispute process
- **Format:** Markdown
- **Chunks:** ~15-20 chunks (500 chars each with 50 char overlap)

#### 2. Subscription Policy (`subscription_policy.md`)
- **Source:** Common SaaS subscription patterns
- **Methodology:** Rewritten, de-branded
- **Content:** Plan tiers, upgrades/downgrades, cancellation, free trial terms
- **Format:** Markdown
- **Chunks:** ~15-20 chunks

#### 3. Account Policy (`account_policy.md`)
- **Source:** Standard account security practices
- **Methodology:** Rewritten
- **Content:** Password requirements, 2FA, login troubleshooting, account deletion
- **Format:** Markdown
- **Chunks:** ~15-20 chunks

**Chunk Processing:**
- Chunk size: 500 characters
- Overlap: 50 characters
- Boundary detection: Sentence or paragraph endings
- Metadata: source file, category, chunk index

---

### FAQ Documents

#### 1. Billing FAQs (`billing_faqs.json`)
- **Count:** 10 Q&A pairs
- **Source:** Synthesized from common SaaS billing questions
- **Topics:** Payment methods, billing dates, invoices, failed payments, disputes
- **Format:** JSON with question, answer, keywords
- **Embedding:** Each FAQ embedded as single document (question + answer)

#### 2. Feature FAQs (`feature_faqs.json`)
- **Count:** 10 Q&A pairs
- **Source:** Common product feature questions
- **Topics:** User management, file sharing, integrations, data export, API access
- **Format:** JSON

#### 3. Technical FAQs (`technical_faqs.json`)
- **Count:** 10 Q&A pairs
- **Source:** Standard technical support questions
- **Topics:** Performance, uploads, offline mode, browser support, mobile apps
- **Format:** JSON

**Total FAQs:** 30 Q&A pairs

---

### Response Templates

**File:** `response_templates.json`
**Count:** 20 templates
**Intent Coverage:**
- billing_question: 5 templates
- subscription_info: 4 templates
- account_access: 3 templates
- feature_question: 3 templates
- policy_question: 1 template
- technical_support: 4 templates

**Template Structure:**
```json
{
  "id": "template_001",
  "intent": "billing_question",
  "risk": "low",
  "confidence_required": 0.8,
  "keywords": ["billing date", "when charged"],
  "template": "Response text..."
}
```

**Matching Algorithm:** Keyword-based with intent filter

---

## Test Dataset

### Evaluation Test Set (`test_set_v1.json`)

**Total Examples:** 50 (in current version, plan calls for 100-150)

**Composition:**
- Safe answerable: 20 examples (40%)
- PII handling: 4 examples (8%)
- Forbidden intents: 8 examples (16%)
- Ambiguous: 5 examples (10%)
- Adversarial: 5 examples (10%)
- Complex: 3 examples (6%)
- Edge cases: 5 examples (10%)

**Example Structure:**
```json
{
  "id": "safe_001",
  "original_message": "When will I be charged?",
  "expected_intent": "billing_question",
  "expected_action": "TEMPLATE",
  "expected_reason": "high_template_match",
  "notes": "Simple billing question",
  "category": "safe_answerable"
}
```

---

### PII Test Cases (`pii_test_cases.json`)

**Total Cases:** 20
**Coverage:**
- Email detection: 3 cases
- Phone detection: 3 cases
- SSN detection: 1 case
- Credit card detection: 2 cases
- Multiple PII: 3 cases
- False positive prevention: 2 cases
- No PII: 2 cases
- Edge cases: 4 cases

**Purpose:** Validate PII detection accuracy
**Target Metrics:**
- Precision: >95%
- Recall (high-risk PII): 100%
- False positive rate: <5%

---

## Data Provenance

### Sources
All knowledge base content is:
1. Inspired by public SaaS policies (Stripe, Shopify, common patterns)
2. Completely rewritten (no copy-paste)
3. De-branded (no real company names)
4. Sanitized (no real user data, account numbers, etc.)

### Methodology
1. **Research:** Review 5-10 public SaaS help centers
2. **Extract Patterns:** Identify common policies and questions
3. **Rewrite:** Create original content following patterns
4. **Verify:** Ensure no copied text (manual review)

### Licensing
- Original content created for this project
- No third-party content copied
- Safe for public demonstration and portfolio use

---

## Data Quality Assurance

### Knowledge Base
- ✅ All sources documented
- ✅ Content rewritten from scratch
- ✅ No real customer data used
- ✅ Consistent terminology
- ✅ Markdown formatting validated

### Test Dataset
- ✅ Covers all supported intents
- ✅ Includes forbidden intents
- ✅ Adversarial examples included
- ✅ Edge cases documented
- ⏳ Inter-rater agreement (would do 20% double-review in production)

### PII Test Cases
- ✅ All PII types covered
- ✅ False positive tests included
- ✅ High-risk PII prioritized
- ✅ Edge cases (international formats, unusual spacing)

---

## Limitations and Biases

### Language
- **English only:** No multilingual support
- **US-centric:** Phone/SSN formats assume US patterns
- **Informal tone:** May not match formal enterprise support

### Domain
- **Generic SaaS:** Not specific to any industry
- **B2B/B2C hybrid:** Covers both personal and business scenarios
- **Feature assumptions:** Assumes common SaaS features (API, integrations, etc.)

### Test Dataset
- **Small size:** 50 examples vs. production need of 500+
- **Manual creation:** No real user queries
- **Artificial adversarial:** May not cover all attack vectors

---

## Future Data Improvements

### Knowledge Base
1. **Expand coverage:** Add more policy domains (refund, security, compliance)
2. **Real FAQs:** Collect from actual support tickets (if available)
3. **Versioning:** Track policy updates over time
4. **Multi-language:** Add translated versions

### Test Dataset
1. **Scale up:** 100-150 examples as per plan
2. **Real queries:** Sample from actual support tickets
3. **Inter-rater agreement:** Have multiple reviewers label 20% of cases
4. **Continuous updates:** Add new failure cases discovered in operation

### PII Detection
1. **International formats:** Non-US phone/address patterns
2. **Rare PII types:** Passport numbers, driver's licenses
3. **Contextual PII:** Inferred from context (e.g., "my mom Mary" → name)

---

## Data Refresh Policy

**Frequency:** Quarterly (in production scenario)

**Triggers for Update:**
- New product features requiring policy updates
- Common user queries not covered by current KB
- Test case failures indicating gaps
- Regulatory changes affecting policies

**Process:**
1. Review metrics: What queries are escalating most?
2. Identify gaps: What info is missing from KB?
3. Author new content: Follow same provenance process
4. Validate: Ensure quality and coverage
5. Re-embed: Update vector database
6. Re-evaluate: Run test suite on updated KB

---

## Summary

**Knowledge Base:**
- 3 policy documents (~45-60 chunks)
- 30 FAQ Q&A pairs
- 20 response templates
- All content original and publicly shareable

**Test Data:**
- 50 evaluation examples (target: 100-150)
- 20 PII test cases
- Covers all critical scenarios

**Quality:**
- High quality, manually curated
- Documented provenance
- No copied content
- Production-ready patterns

This data card would accompany any model/system release for transparency and reproducibility.
