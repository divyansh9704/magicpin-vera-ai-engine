"""
Script to generate submission.jsonl for all 30 test pairs from expanded/test_pairs.json
"""

import json
import os
import sys

# Ensure UTF-8 output in Windows console
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach(), errors="replace")

from composer import compose

def main():
    with open("expanded/test_pairs.json", encoding="utf-8") as f:
        pairs = json.load(f)["pairs"]

    # Load categories
    categories = {}
    for f in os.listdir("expanded/categories"):
        if f.endswith(".json"):
            slug = f.replace(".json", "")
            with open(os.path.join("expanded/categories", f), encoding="utf-8") as cf:
                categories[slug] = json.load(cf)

    # Load merchants
    merchants = {}
    for f in os.listdir("expanded/merchants"):
        if f.endswith(".json"):
            mid = f.replace(".json", "")
            with open(os.path.join("expanded/merchants", f), encoding="utf-8") as mf:
                data = json.load(mf)
                merchants[mid] = data
                if "merchant_id" in data:
                    merchants[data["merchant_id"]] = data

    # Load customers
    customers = {}
    for f in os.listdir("expanded/customers"):
        if f.endswith(".json"):
            cid = f.replace(".json", "")
            with open(os.path.join("expanded/customers", f), encoding="utf-8") as cf:
                data = json.load(cf)
                customers[cid] = data
                if "customer_id" in data:
                    customers[data["customer_id"]] = data

    # Load triggers
    triggers = {}
    for f in os.listdir("expanded/triggers"):
        if f.endswith(".json"):
            tid = f.replace(".json", "")
            with open(os.path.join("expanded/triggers", f), encoding="utf-8") as tf:
                data = json.load(tf)
                triggers[tid] = data
                if "id" in data:
                    triggers[data["id"]] = data

    submission_lines = []
    print(f"Generating submission for {len(pairs)} canonical test pairs...")

    for p in pairs:
        test_id = p["test_id"]
        trg_id = p["trigger_id"]
        m_id = p["merchant_id"]
        c_id = p.get("customer_id")

        trg = triggers.get(trg_id)
        if not trg:
            raise ValueError(f"Trigger {trg_id} not found!")

        merchant = merchants.get(m_id)
        if not merchant:
            raise ValueError(f"Merchant {m_id} not found!")

        cat_slug = merchant.get("category_slug", "restaurants")
        category = categories.get(cat_slug, {})

        customer = customers.get(c_id) if c_id else None

        result = compose(category, merchant, trg, customer)

        submission_entry = {
            "test_id": test_id,
            "body": result["body"],
            "cta": result["cta"],
            "send_as": result["send_as"],
            "suppression_key": result["suppression_key"],
            "rationale": result["rationale"]
        }
        submission_lines.append(submission_entry)
        safe_body_preview = result['body'][:65].replace("\n", " ")
        print(f"[{test_id}] send_as={result['send_as']:<18} cta={result['cta']:<18} body: {safe_body_preview}...")

    output_path = "submission.jsonl"
    with open(output_path, "w", encoding="utf-8") as out_f:
        for entry in submission_lines:
            out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\nSuccessfully generated {len(submission_lines)} lines to {output_path}!")

if __name__ == "__main__":
    main()
