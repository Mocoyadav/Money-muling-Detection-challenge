## Money Muling Detection Web App

Interactive web app for detecting **money muling** patterns from transaction CSV files.

### Input Format

Upload a CSV with the following columns (header names must match exactly):

- **transaction_id**
- **sender_id**
- **receiver_id**
- **amount**
- **timestamp**

`timestamp` can be any common date/time format parsable by pandas (for example `2025-01-31 13:45:00` or ISO8601).

### Detected Patterns

- **Cycles (fraud rings)**: directed loops of length **3–5** accounts.
- **Smurfing (structuring)**:
  - **Fan-in**: **10+** distinct senders → 1 receiver within **72 hours**.
  - **Fan-out**: 1 sender → **10+** distinct receivers within **72 hours**.
- **Shell chains**:
  - Directed paths with **≥3 hops** (3–6 by default).
  - All intermediate accounts have **low activity** (degree ≤ 3).

### Scoring (0–100)

Each account gets a **risk_score**:

- **Graph centrality**: high degree centrality adds base risk.
- **Smurfing involvement**:
  - Fan-in receiver / fan-out sender get the largest boost.
  - Counterparties get a smaller boost.
- **Shell chains**:
  - Low-activity intermediaries get strong risk.
  - Origin & destination get smaller boosts.
- **Fraud ring membership**:
  - Being part of any detected ring boosts risk.
- Final scores are normalized to the range **0–100** and sorted descending.

### JSON Output Format

Click **Download JSON** to get a file with this exact structure:

```json
{
  "graph": {
    "nodes": [
      { "id": "ACCOUNT_ID", "risk_score": 0.0 }
    ],
    "edges": [
      {
        "source": "SENDER_ID",
        "target": "RECEIVER_ID",
        "transaction_id": "TX_ID",
        "amount": 123.45,
        "timestamp": "2025-01-31T13:45:00"
      }
    ]
  },
  "accounts": [
    {
      "account_id": "ACCOUNT_ID",
      "risk_score": 87.5,
      "reasons": [
        "High degree centrality (0.123)",
        "Fan-in smurfing receiver from 12 senders",
        "Member of shell_chain ring"
      ]
    }
  ],
  "fraud_rings": [
    {
      "ring_id": "R0001",
      "members": ["A1", "A2", "A3"],
      "pattern_type": "cycle",
      "risk_score": 80.0,
      "details": {
        "length": 3
      }
    }
  ]
}
```

### Running Locally

1. **Create and activate a virtual environment** (recommended).
2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Start the app**:

   ```bash
   python main.py
   ```

4. Open your browser at `http://localhost:8000`.

### Web UI Features

- **CSV upload** (client-side validation for `.csv`).
- **Interactive graph** using Cytoscape.js:
  - Nodes sized and colored by **risk_score** (green → yellow → red).
  - **Click a node** to see risk explanations.
- **Fraud ring summary table**:
  - `ring_id`, `pattern_type`, `risk_score`, and member list.
- **Top risky accounts table**:
  - Top 50 accounts by risk with reasons.
- **Download JSON**:
  - Exactly the format shown above.

### Performance Notes

- Designed for **≤30s processing** on typical hackathon-sized datasets:
  - Uses NetworkX for graph operations.
  - Limits shell-chain search depth and focuses on low-activity intermediaries.
  - Smurfing detection uses sliding windows over sorted timestamps.
- For very large datasets, consider:
  - Sampling, batching by time window, or pre-aggregating transactions.

### Deployment (Example)

You can deploy this as a public web app on any FastAPI-compatible host, for example:

- **Render / Railway / Fly.io / Azure Web App / AWS Elastic Beanstalk**.

Typical steps:

1. Push this folder to a **GitHub repo**.
2. On your chosen platform:
   - Set the start command to:
     ```bash
     uvicorn main:app --host 0.0.0.0 --port 8000
     ```
   - Configure Python version and install from `requirements.txt`.
3. Once deployed, you’ll get a **public URL** to share.

### LinkedIn Demo Video Tips

- Show:
  - Uploading a **sample CSV**.
  - The **graph animating** into view.
  - The **fraud ring summary** and **top risky accounts**.
  - The **JSON download** and its structure.
- Talk through:
  - The **three detection patterns** (cycles, smurfing, shell chains).
  - How risk is combined into a **0–100 score**.
  - How this helps **reduce false positives** via pattern-based scoring instead of naive rules.

