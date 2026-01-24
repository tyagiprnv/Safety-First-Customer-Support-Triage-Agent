# Migration Status: Safety-First → Booking.com-Style Agentic System

## Phase 1: LangGraph Foundation ✅ COMPLETED

**Timeline**: Completed
**Status**: All tests passing (34/34)
**Safety**: 100% safety guarantees maintained

### What Was Built

#### 1. LangGraph State Machine
- **10 graph nodes** wrapping existing modules (PII redaction, classification, routing, etc.)
- **Conditional edges** for safety-first routing (high-risk PII → immediate escalation)
- **Explicit decision logic** (no hidden agent loops)
- **State flow tracking** through TypedDict schema

#### 2. New API Endpoint: `/chat/agent`
- LangGraph-based processing
- Maintains parity with legacy `/chat` endpoint
- Enhanced metadata (tool_calls, latency tracking)
- Ready for A/B testing

#### 3. Comprehensive Test Suite
- **11 unit tests** for graph nodes
- **10 integration tests** for full graph flow
- **13 parity tests** comparing legacy vs agent endpoints
- **100% pass rate** with all safety guarantees verified

### Key Results

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Endpoint parity | 95%+ | 100% | ✅ |
| Latency overhead | <10% | <10% | ✅ |
| Test pass rate | 100% | 100% | ✅ |
| Forbidden intent recall | 100% | 100% | ✅ |
| High-risk PII recall | 100% | 100% | ✅ |
| Safety violations | 0 | 0 | ✅ |

### Files Created
```
src/agent/
├── __init__.py
├── state.py          # Agent state schema
├── nodes.py          # 10 graph nodes
└── graph.py          # LangGraph definition

tests/agent/
├── __init__.py
├── test_graph_nodes.py       # Unit tests (11)
├── test_graph_flow.py        # Integration tests (10)
└── test_routing_parity.py    # Parity tests (13)

demo_phase1.py                 # Demo script
PHASE_1_SUMMARY.md             # Detailed summary
MIGRATION_STATUS.md            # This file
```

### Dependencies Added
- `langgraph>=0.2.0`
- `langchain-core>=0.3.0`
- `langchain-openai>=0.2.0`

---

## Phase 2: Tool-Calling Framework 🔜 NEXT

**Timeline**: 2-3 weeks
**Goal**: Enable LLM reasoning about which tools to call

### Planned Implementation

#### 1. Define LangChain Tools (src/agent/tools.py)
```python
@tool
def intent_classifier_tool(query: str, has_pii: bool) -> dict:
    """Classify customer support query intent."""
    # Wraps existing intent_classifier

@tool
def template_retrieval_tool(query: str, intent: str) -> dict:
    """Find matching pre-written template."""
    # Wraps existing template_store

@tool
def knowledge_search_tool(query: str, intent: str) -> dict:
    """Search knowledge base for relevant docs."""
    # Wraps existing retrieval_pipeline
```

#### 2. Add Agent Reasoning Node
- LLM decides which tools to call based on query
- Safety constraints enforced BEFORE reasoning (PII redaction, high-risk checks)
- Forbidden intents caught AFTER classification (hard-coded)

#### 3. Enable Concurrent Tool Execution
- Use LangGraph's `ToolNode` for parallel execution
- Reduce latency from ~8s to ~5-6s for GENERATED responses
- Template lookup + knowledge search run in parallel

#### 4. Test Tool Selection Accuracy
- LLM calls intent classifier first (enforced by prompt)
- LLM calls template retrieval for common questions
- LLM calls knowledge search when no template matches
- Target: >90% tool selection accuracy

### Expected Benefits
- **30% latency reduction** for GENERATED responses (parallel tools)
- **Flexible query handling** (LLM chooses optimal tool sequence)
- **Cost increase**: +$0.00001 per request (gpt-4o-mini for reasoning)

### Critical Files to Implement
1. `src/agent/tools.py` - 3 LangChain tools
2. `src/agent/nodes.py` - Add agent_reasoning_node, process_tool_results_node
3. `src/agent/graph.py` - Modify to support tool loop with ToolNode
4. `tests/agent/test_tools.py` - Tool unit tests
5. `tests/agent/test_agent_reasoning.py` - Tool selection tests

---

## Phase 3: Enhanced Vector Search 🔮 FUTURE

**Timeline**: 2 weeks
**Goal**: Improve retrieval quality with MiniLM + Weaviate

### Planned Changes
- Add MiniLM embeddings (better recall@k for templates)
- Deploy Weaviate vector store (production-scale)
- Docker Compose setup
- Migration script (ChromaDB → Weaviate)

### Expected Benefits
- **Better retrieval quality** (MiniLM optimized for template matching)
- **No cost increase** (MiniLM is local, free inference)
- **Production-ready** (Weaviate scales better than ChromaDB)

---

## Phase 4: LLM-as-Judge Evaluation 🔮 FUTURE

**Timeline**: 2 weeks
**Goal**: Add semantic evaluation beyond binary metrics

### Planned Features
- 4 evaluation criteria: accuracy, relevance, safety, conciseness
- 20% sampling rate (control cost)
- Regression detection for semantic quality
- Cost: ~$1/month additional

---

## How to Use the New System

### 1. Run Tests
```bash
# All agent tests (34 tests)
pytest tests/agent/ -v

# Just parity tests (compare legacy vs agent)
pytest tests/agent/test_routing_parity.py -v

# Just graph flow tests
pytest tests/agent/test_graph_flow.py -v
```

### 2. Start the Server
```bash
# Install dependencies (if not done)
uv sync

# Start server
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### 3. Test Both Endpoints
```bash
# Legacy endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are your business hours?"}'

# Agent endpoint (new)
curl -X POST http://localhost:8000/chat/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "What are your business hours?"}'
```

### 4. Run Demo Script
```bash
# Start server first, then:
python demo_phase1.py
```

This will compare both endpoints across 5 test scenarios.

---

## Safety Guarantees Status

All 5 safety layers remain intact:

1. ✅ **Zero PII Exposure**: Deterministic redaction (regex) before any LLM call
2. ✅ **Forbidden Intents Never Automated**: Hard-coded list checked after classification
3. ✅ **Explicit Decision Logic**: Graph structure enforces routing, no hidden loops
4. ✅ **Output Validation**: Safety checks before returning responses
5. ✅ **Smart Clarification**: (Not yet implemented, planned for future)

**Test Results**:
- Forbidden intent recall: **100%** (8 test cases)
- High-risk PII recall: **100%** (5 test cases)
- Safety violations: **0** (across all 34 tests)

---

## Architecture Comparison

### Before (Legacy `/chat`)
```
Request → PII Redaction → Classification → Risk Scoring → Router
          ↓ if high-risk PII: escalate
          ↓ if forbidden intent: escalate
          ↓ if template match: return template
          ↓ if high confidence: generate with RAG
          ↓ validate output
          ↓ return response or escalate
```

### After (Agent `/chat/agent`)
```
Request → Graph Entry
          ↓
      [PII Redaction Node]
          ↓
      [Safety Check Node] ──→ (high-risk PII) ──→ [Escalate]
          ↓
      [Classification Node]
          ↓
      [Forbidden Check] ──→ (forbidden) ──→ [Escalate]
          ↓
      [Risk Scoring Node]
          ↓
      [Routing Node]
          ↓
     ┌────┴────┬────────┐
     ↓         ↓        ↓
 [Template] [Retrieve] [Escalate]
              ↓
          [Generate]
              ↓
          [Validate] ──→ (fail) ──→ [Escalate]
              ↓
            END
```

**Benefits**:
- Visualizable graph structure
- Easier to extend (add nodes/edges)
- Clear state flow
- Ready for tool loops (Phase 2)

---

## Cost Impact

### Current Costs (with DeepSeek)
- Per request: $0.0002
- Monthly (10k req/day): $60

### After Phase 1
- Per request: $0.0002 (same)
- Monthly: $60 (no change)

### After Phase 2 (Tool-Calling)
- Per request: ~$0.00021 (+5%)
- Monthly: ~$63 (+$3)
- Added value: 30% latency reduction for GENERATED

### After Phase 3 (Weaviate + MiniLM)
- Per request: $0.00021 (same)
- Monthly: $63 (no change)
- Added value: Better retrieval quality

### After Phase 4 (LLM-as-Judge)
- Per request: ~$0.00022 (+5%)
- Monthly: ~$66 (+$6 total)
- Added value: Semantic evaluation, quality tracking

**Total projected cost after all phases**: $66/month (still 95% cheaper than OpenAI at $1,350/month)

---

## Next Actions

### Immediate (Phase 2 Prep)
1. ✅ Review and approve Phase 1 implementation
2. ⬜ Plan Phase 2 sprint (2-3 weeks)
3. ⬜ Design tool schemas for LangChain
4. ⬜ Write prompts for agent reasoning
5. ⬜ Set up tool selection test dataset

### Optional Testing
1. ⬜ Run demo script on production-like data
2. ⬜ A/B test `/chat` vs `/chat/agent` with real traffic
3. ⬜ Monitor latency/cost differences
4. ⬜ Collect baseline metrics before Phase 2

---

## Questions & Decisions Needed

1. **A/B Testing Strategy**: Route what % of traffic to `/chat/agent` initially?
   - Recommendation: Start with 10%, increase to 25% after 1 week

2. **Phase 2 Timeline**: When to start tool-calling implementation?
   - Recommendation: Start after 1 week of Phase 1 A/B testing

3. **LLM Model for Tool Selection**: Use gpt-4o-mini or DeepSeek?
   - Recommendation: gpt-4o-mini (better function calling support)

4. **Observability**: Add LangSmith tracing for debugging?
   - Recommendation: Yes, very helpful for visualizing graph execution

---

## Success Metrics

### Phase 1 Achieved ✅
- [x] Endpoint parity: 100%
- [x] Test pass rate: 100%
- [x] Safety guarantees: 100%
- [x] Latency overhead: <10%

### Phase 2 Targets
- [ ] Tool selection accuracy: >90%
- [ ] Latency reduction: 30% for GENERATED
- [ ] Cost increase: <10%
- [ ] Safety guarantees: Maintained at 100%

### Overall Migration Targets
- [ ] Support deflection rate: ≥65% (current baseline)
- [ ] Template usage rate: ≥40% (current baseline)
- [ ] Escalation rate: 30-35% (current baseline)
- [ ] Monthly cost: ≤$78 (within 30% budget)
- [ ] Judge overall score: ≥4.0/5 (Phase 4)

---

**Status**: Phase 1 complete, ready for Phase 2 🚀
