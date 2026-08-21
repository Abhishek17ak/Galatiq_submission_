# Invoice Processing Automation — Galatiq Case Study

A working multi-agent system that automates Acme Corp's invoice processing pipeline end-to-end: ingestion, inventory validation, VP-level approval (with a self-critique loop), and payment — built to address a **$2M/year loss, 30% error rate, and 5-day processing delays** from manual handling.

## Business Impact (measured against the real dataset)

Running the full pipeline against 20 real invoices spanning 5 file formats (txt, csv, json, xml, pdf):

| Metric | Result |
|---|---|
| Invoices processed | 20 / 20, zero crashes |
| Auto-approved & paid | 11 invoices — **$59,340.00** |
| Correctly held for review | 9 invoices — **$203,758.60** |
| Processing time per invoice | Seconds, not 5 days |
| Error rate | 0% silent failures — every problematic invoice was caught and flagged with a specific, auditable reason |

Every held invoice comes with a full reasoning trail (draft decision + a self-critique step that re-examines it), so a human reviewer isn't starting from scratch — they're confirming or overriding a documented judgment call, not re-doing the analysis. See `reports/` for a full HTML/CSV breakdown of a sample run.

## Architecture

Four agents, orchestrated as a LangGraph `StateGraph`, passing a single shared Pydantic state object end-to-end:

```
Ingestion → Validation → Approval → Payment
```

- **Ingestion** (`agents/ingestion_agent.py`) — reads any invoice format (PDF via `pdfplumber`, txt/csv/json/xml as raw text) and extracts structured fields (vendor, amount, items, due date) using an LLM with constrained structured output. Includes a self-correction retry if extraction comes back empty or fails validation.
- **Validation** (`agents/validation_agent.py`) — deterministic checks against a local SQLite inventory catalog: unknown items, stock exceeded, zero-stock (fraud-flavored) items, negative quantities. No LLM call needed here — it's a lookup/comparison task, kept fast and 100% reproducible.
- **Approval** (`agents/approval_agent.py`) — simulates VP-level review. A rule-based gate flags invoices over $10,000 for extra scrutiny, then the LLM drafts a decision and **critiques its own draft** in a second pass before finalizing — the self-correction/reflection loop this case study asks for. Includes its own retry wrapper for structured-output failures.
- **Payment** (`agents/payment_agent.py`) — calls the mock payment function on approval, or logs a structured rejection with the full reasoning attached.

Full state (including every intermediate field) is written to `logs/` as JSON after every CLI run, giving a complete audit trail per invoice.

## Tech Stack & Design Decisions

- **LLM: Claude (Anthropic API)** — substituted for the suggested xAI Grok API, which the case study explicitly permits. Chosen for reliable structured-output support and fast setup.
- **Orchestration: LangGraph** — the workflow is a pipeline with each stage's outcome feeding the next, which maps directly onto an explicit state graph rather than free-form multi-agent chat.
- **PDF parsing: `pdfplumber`** — handles all three provided PDF invoices cleanly.
- **DB: SQLite** — as specified, seeded to reproduce every scenario in the original test spec (stock-exceeded, unknown item, zero-stock/fraud item, negative quantity).

## Setup

```bash
git clone <this-repo-url>
cd galatiq-invoice-automation
pip3 install -r requirements.txt --break-system-packages
```

Create a `.env` file in the project root:
```
ANTHROPIC_API_KEY=your-key-here
```

Initialize the inventory database (already included, but regeneratable):
```bash
python3 db/setup_db.py
```

## Running

Process a single invoice:
```bash
python3 main.py --invoice_path=data/invoices/invoice_1002.txt
```

Run the full batch across every provided invoice and generate a summary report:
```bash
python3 tests/run_all_invoices.py
```
This prints a console summary and writes both a CSV and a styled HTML report to `reports/`.

Launch the interactive UI:
```bash
pip3 install streamlit --break-system-packages
streamlit run app.py
```
Opens in your browser — pick any sample invoice from the dropdown and click **Process Invoice** to see the full pipeline result: decision badge, extracted fields, validation flags, and the approval agent's reasoning + self-critique, all rendered live.

## Testing

Unit tests cover the Validation and Approval agents' logic deterministically (mocked LLM calls, no API key needed, runs instantly):
```bash
python3 -m unittest discover tests
```

For end-to-end proof against real data, `tests/run_all_invoices.py` runs the full pipeline (real LLM calls) against every invoice in `data/invoices/` and reports pass/fail — this is what produced the business impact numbers above.

## Known Data Quirks Handled

- `invoice_1014.xml` is priced in EUR — extraction notes this explicitly rather than silently treating it as USD.
- `invoice_1004` and `invoice_1004_revised` are a revision pair — both process independently and correctly.
- `invoice_1013`'s stated total doesn't reconcile exactly with subtotal + tax (~$50 off) — the system doesn't specifically flag this discrepancy type, but the invoice is still correctly rejected on the stock-exceeded flags present in the same document.

## Possible Extensions

- An explicit total-reconciliation check (subtotal + tax vs. stated total) as an additional validation flag type
- Persisting inventory decrements across invoices to simulate real depleting stock, rather than treating each invoice independently
- Tool-calling refinement: give the Approval agent an actual callable inventory-lookup tool rather than reading pre-computed validation flags, for a more literal "LLM decides to invoke a tool" interaction