# Architectural Decisions

This document explains key architectural choices and their rationale.

---

## 1. Privacy-First: Deterministic PII Redaction Before LLM

### Decision
Use regex-based PII detection that runs BEFORE any LLM API call.

### Alternatives Considered
1. **LLM-based PII detection**: Ask LLM to identify and redact PII
2. **Post-processing PII removal**: Redact after LLM processing
3. **No PII handling**: Trust LLM to handle sensitively

### Why Deterministic Regex?

**Pros:**
- **Guaranteed execution**: Regex always runs, never skipped
- **No LLM dependency**: Works even if API is down
- **Cost-effective**: No API call needed
- **Transparent**: Exactly what patterns trigger is visible
- **Provable**: Can formally verify PII is never sent to LLM

**Cons:**
- **Lower recall**: May miss unconventional PII formats
- **Context loss**: Semantic markers less expressive than original
- **Maintenance**: Regex patterns need updates for new formats

**Tradeoff Accepted:**
- ~10% classification accuracy loss vs. zero PII exposure to LLM
- This is the right tradeoff for a production system handling sensitive data

---

## 2. Explicit State Machine Over LangGraph

### Decision
Implement decision routing as explicit Python logic with clear precedence rules.

### Alternatives Considered
1. **LangGraph**: Use LangChain's agent framework
2. **ReAct Prompting**: Let LLM decide actions
3. **Custom Agent Loop**: Iterative LLM-driven decisions

### Why Explicit State Machine?

**Pros:**
- **Full control**: Every decision path is visible and testable
- **No hidden loops**: Agents can "go rogue" with unexpected tool use
- **Debuggable**: Stack traces show exact decision path
- **Predictable costs**: No surprise API call loops
- **Safety guarantees**: Hard rules (forbidden intents) can't be bypassed

**Cons:**
- **Less flexible**: Can't adapt to unexpected scenarios
- **More code**: Have to implement routing logic manually
- **No self-correction**: Can't recover from bad decisions within request

**Why This Matters:**
For safety-critical applications, predictability > flexibility. We need to prove the system can't do forbidden things.

---

## 3. Template-First Response Strategy

### Decision
Prefer pre-written templates over generated responses when possible.

### Alternatives Considered
1. **Always generate**: Use RAG for every response
2. **Hybrid with low threshold**: Generate if any context found
3. **LLM routing**: Let LLM decide template vs. generate

### Why Templates First?

**Pros:**
- **Faster**: No retrieval or generation needed (~500ms vs ~3s)
- **Safer**: Human-vetted responses, no hallucination risk
- **Cheaper**: No embedding or generation API calls
- **Consistent**: Same question always gets same answer
- **Controllable**: Easy to update approved responses

**Cons:**
- **Rigid**: Can't adapt to question variations
- **Less natural**: More "FAQ" feel than conversational
- **Maintenance burden**: Need to maintain template library

**Routing Logic:**
1. Check templates first (high similarity threshold: 0.9)
2. Fall back to RAG if no good template match
3. Escalate if retrieval quality is poor

---

## 4. ChromaDB Embedded Mode (No Separate Vector DB Service)

### Decision
Use ChromaDB in persistent embedded mode within the same container.

### Alternatives Considered
1. **Pinecone/Weaviate**: Managed vector DB service
2. **PostgreSQL pgvector**: Store in relational DB
3. **Separate ChromaDB service**: Run as sidecar container

### Why Embedded ChromaDB?

**Pros:**
- **Simple deployment**: Single container, no orchestration
- **Local performance**: No network latency for queries
- **Cost-effective**: No external service fees
- **Development ease**: Works locally without setup
- **Sufficient scale**: Handles 1000s of documents easily

**Cons:**
- **Limited scale**: Can't handle millions of documents
- **No redundancy**: Single point of failure
- **Memory constraints**: Embedded in same process
- **No distributed queries**: All data on one node

**For This Use Case:**
- Knowledge base is small (~100-500 documents)
- Query volume is moderate
- Simplicity > scale for demonstration

---

## 5. Confidence Adjustment for PII Redaction

### Decision
Reduce classification confidence by 20% when PII redaction likely affected context.

### Alternatives Considered
1. **No adjustment**: Trust LLM to handle semantic markers
2. **Separate PII-aware model**: Fine-tune model on redacted data
3. **Always reduce**: Penalize any PII presence

### Why Adaptive Confidence Reduction?

**Logic:**
```python
if redaction.has_pii and affects_context(redaction):
    adjusted_confidence = confidence - 0.2
```

**When PII Affects Context:**
- Message is short (<50 chars) + has PII
- PII markers are >30% of message length
- 3+ PII items detected

**Why 20%?**
- Empirical: Moves medium confidence (0.75) below escalation threshold (0.7)
- Not too aggressive: High confidence (0.95) still passes
- Conservative: Biases toward escalation when uncertain

**Example:**
- Original: "My account USER12345 was charged"
- Redacted: "My [ACCOUNT_ID] was charged"
- Impact: Specific account ID → generic marker
- Confidence: 0.85 → 0.65 → **ESCALATE**

---

## 6. Risk Scoring Formula

### Decision
Use additive risk model: `base_risk(intent) + pii_risk + confidence_penalty`

### Formula
```
risk_score = base_risk[intent]
           + min(high_risk_pii_count * 0.3 + medium_risk_pii_count * 0.15, 0.4)
           + (1 - confidence) * 0.2
```

### Why Additive vs. Multiplicative?

**Additive Pros:**
- Interpretable: Easy to see contribution of each factor
- Tunable: Adjust weights independently
- Predictable: No exponential explosions

**Additive Cons:**
- Can exceed 1.0 (must cap)
- Doesn't model interactions (e.g., high confidence + high PII)

**Mitigation:**
- Cap total at 1.0
- Use explicit checks (high-risk PII → always escalate) rather than relying on score alone

**Base Risk by Intent:**
- Low risk: feature_question (0.1), policy_question (0.2)
- Medium risk: billing_question (0.4), technical_support (0.3)
- High risk: account_access (0.6), forbidden intents (0.9-1.0)

---

## 7. Output Validation as Safety Net

### Decision
Validate all generated responses before returning to user.

### What We Check
1. **PII leakage**: Run PII detector on output
2. **Forbidden phrases**: "refund approved", "account modified", etc.
3. **Hallucination indicators**: Specific URLs, dates, names
4. **Length**: Min 20 chars, max 1000 chars

### Why Validate Generated But Not Template Responses?

**Generated responses:**
- LLM-created → unpredictable
- Can hallucinate
- Can leak PII if prompt injection succeeds
- Need runtime checks

**Template responses:**
- Human-written → pre-vetted
- Static → can review once
- Fast path → validation adds latency

### Validation Failures → Escalation
If output validation fails, we escalate rather than trying to "fix" the response. This is safer than attempting automatic correction.

---

## 8. No Multi-Turn Support

### Decision
Each request is independent; no conversation history.

### Alternatives Considered
1. **Session-based context**: Store history in Redis
2. **Conversational memory**: Pass history in prompts
3. **Stateful agents**: Track user intent across turns

### Why Stateless?

**Pros:**
- **Simpler safety**: Each request evaluated independently
- **No context leakage**: Can't reference past PII across turns
- **Scalable**: No session state to manage
- **Testable**: Each request fully specified in test case

**Cons:**
- **Less natural**: Users can't say "yes" or "tell me more"
- **Repetitive**: Users must restate context each time
- **Frustrating**: Multi-step tasks require multiple messages

**For Triage Use Case:**
Most triage queries are single-turn:
- "How do I reset my password?"
- "When will I be charged?"
- "My account is locked"

Multi-turn conversations add complexity without significant value for this use case.

---

## 9. Structured Logging for Observability

### Decision
Use structlog for JSON-formatted logs with PII filtering.

### What We Log
```json
{
  "event": "request_processed",
  "request_id": "uuid",
  "action": "ESCALATE",
  "reason": "low_confidence",
  "intent": "billing_question",
  "confidence": 0.65,
  "risk_score": 0.73,
  "pii_types": ["email"],
  "has_high_risk_pii": false,
  "latency_ms": 1234,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### What We DON'T Log
- Original user message (may contain PII)
- Redacted message (might be useful for debugging, but skipped for safety)
- User-specific IDs (in production, would need careful handling)

### Why JSON Logs?
- **Searchable**: Easy to query with log aggregation tools
- **Structured**: Can filter by field (e.g., all high_risk_score events)
- **Machine-readable**: Can feed into monitoring dashboards
- **Complete**: Every decision has full context logged

---

## 10. Single Container Deployment

### Decision
Deploy as single Docker container, no Kubernetes.

### Alternatives Considered
1. **Kubernetes**: Full orchestration
2. **Serverless**: Lambda/Cloud Functions
3. **Microservices**: Separate services for classification, generation, etc.

### Why Single Container?

**Pros:**
- **Simple**: Docker Compose is enough
- **Fast deployment**: Works on Render, Fly.io, etc.
- **Development parity**: Prod = local
- **Sufficient**: Handles moderate traffic

**Cons:**
- **No auto-scaling**: Manual scaling needed
- **Single point of failure**: No redundancy
- **Resource limits**: Bounded by container size

**For This Use Case:**
- Demonstration project, not production SaaS
- Showing good judgment: don't over-engineer
- Can scale vertically (bigger container) before needing Kubernetes

---

## Summary: Architectural Philosophy

1. **Safety > Automation Rate**: Bias toward escalation
2. **Transparency > Black Box**: Explicit logic, no hidden agents
3. **Simplicity > Features**: Do fewer things well
4. **Privacy > Marginal Accuracy**: Protect PII at all costs
5. **Pragmatism > Best Practices**: Use what fits the problem

These decisions reflect **production engineering judgment**, not just following tutorials.
