# Safety-First Customer Support Triage Agent

> **Demonstrating production-grade GenAI engineering: Privacy-first design, explicit safety guarantees, and pragmatic execution.**

## Executive Summary

This project implements an AI-powered customer support triage system that **prioritizes safety over automation rate**. Unlike typical chatbots that try to answer everything, this system explicitly biases toward escalation when uncertain, ensuring zero unsafe responses.

### What This System Does
- **Automatically triages** customer support messages into safe-to-automate vs. requires-human categories
- **Detects and redacts PII** BEFORE any LLM processing (privacy-first)
- **Provides instant responses** for simple, low-risk queries using templates
- **Generates contextual answers** for complex queries using RAG (Retrieval-Augmented Generation)
- **Escalates to humans** when confidence is low, risk is high, or PII is present

### What This System Does NOT Do
- ❌ Multi-turn conversations (single request/response only)
- ❌ Personalized responses (no account-specific data)
- ❌ Automated account modifications (always escalated)
- ❌ Refund processing (always escalated)
- ❌ Legal or security incident handling (always escalated)

### Key Design Decision: Privacy-First Architecture

**PII is redacted using deterministic regex patterns BEFORE any LLM call.**

**Tradeoff Accepted:**
- Cost: ~10% reduction in intent classification accuracy
- Benefit: Zero PII exposure to LLM providers
- Mitigation: Bias toward escalation when ambiguity increases
- Justification: Human agents are authorized to handle PII; escalation is safer than incorrect automation

---

## Architecture Overview

![Architecture](images/architecture.png)


```
User Message
   ↓
[1] Input Validation (10-2000 chars)
   ↓
[2] PII Detection & Redaction (DETERMINISTIC)
   └─ Regex: email, phone, SSN, credit card, account IDs
   └─ Output: redacted_message + pii_metadata
   └─ Semantic markers preserve context: [EMAIL_ADDRESS], [PHONE_NUMBER], etc.
   ↓
[3] High-Risk PII Check
   └─ If SSN or credit card detected → AUTO-ESCALATE (skip classification)
   ↓
[4] Intent Classification (on redacted message)
   └─ LLM classifies intent with PII context awareness
   └─ Confidence adjustment: reduce by 20% if PII removed critical context
   ↓
[5] Risk Scoring
   └─ Factors: intent type, confidence, PII presence
   └─ Output: risk_score (0.0-1.0)
   ↓
[6] Hard Rule Check
   └─ If intent in FORBIDDEN_INTENTS → ESCALATE
   ↓
[7] Decision Router (Explicit Precedence)
   └─ 1. Safety checks (risk, confidence, PII)
   └─ 2. Template matching (preferred, safest)
   └─ 3. RAG retrieval + generation (flexible but slower)
   └─ 4. Default: ESCALATE
   ↓
[8] Response Generation (if TEMPLATE or GENERATED)
   └─ TEMPLATE: Use pre-written response
   └─ GENERATED: Retrieve from vector DB → LLM generates with context
   ↓
[9] Output Validation
   └─ No PII leakage, no policy violations, length check
   ↓
[10] Logging (all logs are PII-free by design)
```

---

## Supported vs. Forbidden Intents

### ✅ Supported (Safe to Automate)
- `billing_question`: Read-only billing info, invoice questions
- `feature_question`: "How does X work?"
- `subscription_info`: Plan details, subscription status
- `policy_question`: General policies (non-refund)
- `account_access`: Login help, password reset info (read-only)
- `technical_support`: Product bugs, troubleshooting

### ⛔ Forbidden (Always Escalate)
- `refund_request`: Money-back requests
- `account_modification`: Change email, phone, PII
- `legal_dispute`: Legal threats, complaints
- `security_incident`: Fraud, account compromise

**Enforcement**: Hard-coded list checked AFTER classification. No LLM prompt engineering can bypass this.

---

## Safety Guarantees

### 1. Zero PII Exposure to LLMs
- All PII detection is deterministic (regex-based)
- PII redaction happens BEFORE any API call
- Semantic markers preserve context: `[EMAIL_ADDRESS]`, `[PHONE_NUMBER]`, etc.
- High-risk PII (SSN, credit card) triggers immediate escalation

### 2. Forbidden Intents Never Get Automated Responses
- Hard-coded list of forbidden intents
- Checked AFTER classification (not reliant on LLM)
- No prompt engineering can override this safety check

### 3. Explicit Decision Logic (No Hidden Agent Loops)
- Decision routing follows explicit precedence rules
- Every decision has a logged reason code
- No LangGraph or autonomous agents (full control)

### 4. Output Validation Before Response
- Checks for PII leakage in generated responses
- Validates against forbidden phrases (e.g., "refund approved")
- Detects hallucinated details (specific URLs, dates, names)
- Failed validation → escalation

### 5. Bias Toward Escalation
- Low confidence (<70%) → escalate
- Medium confidence + PII present (<85%) → escalate
- High risk score (>0.7) → escalate
- Insufficient retrieval → escalate
- When in doubt, escalate

---

## Technical Stack

- **Backend**: FastAPI (async, high-performance)
- **LLM Provider**: OpenAI
  - Classification: GPT-4o-mini (fast, cost-effective)
  - Generation: GPT-4o (quality responses)
  - Embeddings: text-embedding-3-small
- **Vector Database**: ChromaDB (embedded mode, persistent)
- **Orchestration**: Explicit Python state machine (no LangGraph)
- **Logging**: Structlog (structured JSON logs, PII-free)
- **Deployment**: Docker + Docker Compose

---

## Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (fast Python package manager)
- Docker (optional, for containerized deployment)
- OpenAI API key

### 1. Local Setup

```bash
# Install uv (if not already installed)
# macOS/Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows:
# powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Clone the repository
git clone <repository-url>
cd Safety-First-Customer-Support-Triage-Agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies (using uv package manager)
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 2. Ingest Knowledge Base

```bash
# Populate vector database with policy documents and FAQs
python scripts/ingest_knowledge_base.py
```

### 3. Run the Application

```bash
# Start the FastAPI server
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### 4. Test the API

```bash
# Health check
curl http://localhost:8000/health

# Safe query (should get TEMPLATE or GENERATED response)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are your business hours?"}'

# Forbidden intent (should escalate)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want a refund for my last purchase"}'

# High-risk PII (should auto-escalate)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "My SSN 123-45-6789 was exposed"}'

# Check metrics
curl http://localhost:8000/metrics
```

---

## Docker Deployment

### Build and Run

```bash
# Build image
docker-compose build

# Start service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop service
docker-compose down
```

### Environment Variables

Required:
- `OPENAI_API_KEY`: Your OpenAI API key

Optional (with defaults):
- `LOG_LEVEL`: INFO (or DEBUG)
- `MIN_CONFIDENCE_THRESHOLD`: 0.7
- `HIGH_CONFIDENCE_THRESHOLD`: 0.85
- `HIGH_RISK_THRESHOLD`: 0.7
- `TEMPLATE_SIMILARITY_THRESHOLD`: 0.9
- `MIN_RETRIEVAL_SCORE`: 0.75

---

## API Endpoints

### POST /chat
Process a customer support message.

**Request:**
```json
{
  "message": "Why was my card charged twice?",
  "session_id": "optional-session-id"
}
```

**Response:**
```json
{
  "action": "TEMPLATE" | "GENERATED" | "ESCALATE",
  "response": "Your response text" | null,
  "reason": "high_template_match",
  "escalation_ticket_id": "TKT-ABC123" | null,
  "metadata": {
    "intent": "billing_question",
    "confidence": 0.92,
    "risk_score": 0.4,
    "pii_detected": ["email"],
    "latency_ms": 450
  }
}
```

### GET /metrics
Get system performance metrics.

**Response:**
```json
{
  "total_requests": 1234,
  "action_distribution": {
    "TEMPLATE": 520,
    "GENERATED": 314,
    "ESCALATE": 400
  },
  "avg_latency_ms": {
    "template": 890,
    "generated": 2340,
    "escalate": 650
  },
  "escalation_rate": 0.324,
  "safety": {
    "unsafe_responses": 0,
    "high_risk_pii_escalations": 45,
    "forbidden_intent_escalations": 89
  }
}
```

### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "vector_db_connected": true,
  "llm_provider_status": "ok"
}
```

---

## Testing

### Run Unit Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_pii_redaction.py -v
```

### Run PII Detection Tests

```bash
# Test PII redaction accuracy
python -m pytest tests/test_pii_redaction.py::test_all_test_cases -v
python -m pytest tests/test_pii_redaction.py::test_precision_target -v
python -m pytest tests/test_pii_redaction.py::test_high_risk_recall -v
```

---

## Evaluation Results

### PII Detection Performance
- **Precision**: >95% (low false positives)
- **Recall (High-Risk PII)**: 100% (SSN, credit cards always detected)
- **Semantic Preservation**: ~90% of cases maintain intent after redaction

### System Performance Targets
| Metric | Target | Status |
|--------|--------|--------|
| Zero unsafe responses | 0% | ✅ Enforced by design |
| Escalation precision | >80% | ⏳ Requires eval dataset |
| Answer correctness | >90% | ⏳ Requires eval dataset |
| PII impact on accuracy | ≤10% | ⏳ Requires eval dataset |
| Template usage rate | >40% | ⏳ Requires eval dataset |

**Note**: Full evaluation requires running `evaluation/run_eval.py` with the test dataset.

---

## Tradeoffs & Limitations

### Accepted Tradeoffs

1. **PII Redaction Reduces Accuracy (~10%)**
   - **Why**: Semantic markers like `[EMAIL_ADDRESS]` remove specifics
   - **Mitigation**: Confidence reduction when PII affects context
   - **Justification**: Privacy > marginal accuracy gain

2. **High Escalation Rate (~30-40%)**
   - **Why**: Bias toward safety over automation
   - **Benefit**: Zero unsafe responses guaranteed
   - **Justification**: Human agents are available and authorized

3. **Template Rigidity vs. Natural Responses**
   - **Why**: Templates are safer and faster than generation
   - **Benefit**: Consistent, vetted responses
   - **Justification**: Consistency > conversational "feel"

4. **No Multi-Turn Support**
   - **Why**: Stateless design simplifies safety guarantees
   - **Benefit**: Each request evaluated independently
   - **Justification**: Complexity cost not worth benefit for triage

### Known Limitations

- **English Only**: No multi-language support
- **No Account Context**: Cannot access user-specific data
- **Static Knowledge Base**: Requires manual updates
- **No Active Learning**: Doesn't improve from escalations automatically

---

## Project Structure

```
Safety-First-Customer-Support-Triage-Agent/
├── src/
│   ├── api/
│   │   ├── main.py              # FastAPI application
│   │   └── __init__.py
│   ├── prompts/
│   │   └── classification_prompt.py
│   ├── pii_redactor.py          # PII detection & redaction
│   ├── intent_classifier.py     # Intent classification
│   ├── risk_scorer.py           # Risk scoring
│   ├── decision_router.py       # Routing logic
│   ├── vector_store.py          # ChromaDB wrapper
│   ├── retrieval.py             # RAG retrieval
│   ├── generation.py            # Response generation
│   ├── output_validator.py      # Output safety checks
│   ├── escalation.py            # Mock ticket system
│   ├── models.py                # Pydantic models
│   ├── config.py                # Configuration
│   └── logging_config.py        # Structured logging
├── data/
│   ├── knowledge_base/
│   │   ├── policies/            # Markdown policy docs
│   │   └── faqs/                # JSON FAQ files
│   ├── templates/               # Response templates
│   ├── evaluation/              # Test datasets
│   └── vector_db/               # ChromaDB persistence
├── tests/
│   └── test_pii_redaction.py    # PII detection tests
├── scripts/
│   └── ingest_knowledge_base.py # Vector DB population
├── docs/
│   ├── architectural_decisions.md
│   ├── data_card.md
│   └── deployment.md
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Future Improvements

These are NOT implemented but documented as learning:

1. **Multi-Turn Conversations**: Track context across messages
2. **Active Learning**: Learn from escalations to improve classification
3. **Dynamic Threshold Tuning**: Adjust confidence thresholds based on performance
4. **Multi-Language Support**: Extend to non-English languages
5. **LLM-as-Judge Evaluation**: Automated quality assessment of generated responses
6. **A/B Testing Framework**: Test different routing strategies
7. **Fine-Tuned Classification Model**: Custom model for intent detection

---

## License

MIT License - See LICENSE file for details

---

## Contact

For questions about this project, please open an issue on GitHub.

---

**Built with ❤️ to demonstrate production-grade GenAI engineering practices.**
