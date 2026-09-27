"""
Comprehensive Test Suite for Vera Bot
=====================================
Validates all endpoints, idempotency, multi-turn state transitions,
auto-reply detection, hostile de-escalation, and rubric compliance.
"""

import unittest
import json
import time
from fastapi.testclient import TestClient
from bot import app, contexts, suppressed_keys
from conversation_handlers import conv_manager


class TestVeraBot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        # Reset state before each test
        contexts.clear()
        suppressed_keys.clear()
        conv_manager.conversations.clear()

    def test_healthz_and_metadata(self):
        # Test healthz
        resp = self.client.get("/v1/healthz")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("uptime_seconds", data)
        self.assertIn("contexts_loaded", data)

        # Test metadata
        resp_meta = self.client.get("/v1/metadata")
        self.assertEqual(resp_meta.status_code, 200)
        data_meta = resp_meta.json()
        self.assertIn("team_name", data_meta)
        self.assertIn("version", data_meta)
        self.assertIn("contact_email", data_meta)
        self.assertIn("model", data_meta)

    def test_context_push_and_idempotency(self):
        category_payload = {
            "slug": "dentists",
            "voice": {"tone": "peer_clinical", "vocab_taboo": ["guaranteed", "100% safe"]},
            "offer_catalog": [{"id": "den_001", "title": "Dental Cleaning @ ₹299"}]
        }

        # First push (version 1)
        r1 = self.client.post("/v1/context", json={
            "scope": "category",
            "context_id": "dentists",
            "version": 1,
            "payload": category_payload
        })
        self.assertEqual(r1.status_code, 200)
        self.assertTrue(r1.json()["accepted"])

        # Version bump (version 2 -> should return 200 accepted)
        category_payload["peer_stats"] = {"avg_ctr": 0.035}
        r2 = self.client.post("/v1/context", json={
            "scope": "category",
            "context_id": "dentists",
            "version": 2,
            "payload": category_payload
        })
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json()["accepted"])

        # Duplicate push (same version 2 -> idempotent no-op returns 200)
        r3 = self.client.post("/v1/context", json={
            "scope": "category",
            "context_id": "dentists",
            "version": 2,
            "payload": category_payload
        })
        self.assertEqual(r3.status_code, 200)
        self.assertTrue(r3.json()["accepted"])

        # Stale push (lower version 1 -> should return 409 stale_version)
        r4 = self.client.post("/v1/context", json={
            "scope": "category",
            "context_id": "dentists",
            "version": 1,
            "payload": category_payload
        })
        self.assertEqual(r4.status_code, 409)
        self.assertFalse(r4.json()["accepted"])
        self.assertEqual(r4.json()["reason"], "stale_version")

    def test_auto_reply_hell(self):
        """Simulates judge's auto-reply hell scenario."""
        auto_msg = "Thank you for contacting us! Our team will respond shortly."
        mid = "m_001_drmeera"

        # Turn 1 auto-reply: should return action wait
        r1 = self.client.post("/v1/reply", json={
            "conversation_id": "conv_auto_test",
            "merchant_id": mid,
            "from_role": "merchant",
            "message": auto_msg,
            "turn_number": 1
        })
        self.assertEqual(r1.status_code, 200)
        data1 = r1.json()
        self.assertEqual(data1["action"], "wait")
        self.assertGreaterEqual(data1.get("wait_seconds", 0), 3600)

        # Repeated auto-reply by turn 3: should return action end
        r3 = self.client.post("/v1/reply", json={
            "conversation_id": "conv_auto_test",
            "merchant_id": mid,
            "from_role": "merchant",
            "message": auto_msg,
            "turn_number": 3
        })
        self.assertEqual(r3.status_code, 200)
        data3 = r3.json()
        self.assertEqual(data3["action"], "end")

    def test_intent_transition(self):
        """Simulates judge's intent transition scenario."""
        mid = "m_001_drmeera"
        commitment = "Ok lets do it. Whats next?"

        r = self.client.post("/v1/reply", json={
            "conversation_id": "conv_intent_test",
            "merchant_id": mid,
            "from_role": "merchant",
            "message": commitment,
            "turn_number": 2
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["action"], "send")
        body = data.get("body", "").lower()

        actioning = ["done", "sending", "draft", "here", "confirm", "proceed", "next"]
        qualifying = ["would you", "do you", "can you tell", "what if", "how about"]

        # MUST contain actioning keywords
        self.assertTrue(any(w in body for w in actioning), f"Expected actioning words in: {body}")
        # MUST NOT contain qualifying keywords
        self.assertFalse(any(w in body for w in qualifying), f"Unexpected qualifying words in: {body}")

    def test_hostile_handling(self):
        """Simulates judge's hostile opt-out scenario."""
        mid = "m_001_drmeera"
        hostile = "Stop messaging me. This is useless spam."

        r = self.client.post("/v1/reply", json={
            "conversation_id": "conv_hostile_test",
            "merchant_id": mid,
            "from_role": "merchant",
            "message": hostile,
            "turn_number": 2
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["action"], "end")

    def test_tick_action_generation(self):
        """Tests full context push and tick generation."""
        # 1. Push category
        self.client.post("/v1/context", json={
            "scope": "category",
            "context_id": "dentists",
            "version": 1,
            "payload": {
                "slug": "dentists",
                "voice": {"tone": "peer_clinical", "vocab_taboo": ["guaranteed"]},
                "offer_catalog": [{"id": "den_001", "title": "Dental Cleaning @ ₹299"}],
                "digest": [{
                    "id": "d_2026W17_jida_fluoride",
                    "source": "JIDA Oct 2026, p.14",
                    "trial_n": 2100,
                    "summary": "3-month fluoride recall cuts caries 38% better."
                }]
            }
        })

        # 2. Push merchant
        self.client.post("/v1/context", json={
            "scope": "merchant",
            "context_id": "m_001_drmeera",
            "version": 1,
            "payload": {
                "merchant_id": "m_001_drmeera",
                "category_slug": "dentists",
                "identity": {"name": "Dr. Meera's Dental Clinic", "city": "Delhi", "locality": "Lajpat Nagar", "owner_first_name": "Meera", "languages": ["en"]},
                "performance": {"views": 2410, "calls": 18, "ctr": 0.021},
                "offers": [{"id": "o1", "title": "Dental Cleaning @ ₹299", "status": "active"}]
            }
        })

        # 3. Push trigger
        self.client.post("/v1/context", json={
            "scope": "trigger",
            "context_id": "trg_001_research",
            "version": 1,
            "payload": {
                "id": "trg_001_research",
                "scope": "merchant",
                "kind": "research_digest",
                "merchant_id": "m_001_drmeera",
                "payload": {"category": "dentists", "top_item_id": "d_2026W17_jida_fluoride"},
                "suppression_key": "suppress:trg_001"
            }
        })

        # 4. Call tick
        resp = self.client.post("/v1/tick", json={
            "now": "2026-04-26T10:00:00Z",
            "available_triggers": ["trg_001_research"]
        })
        self.assertEqual(resp.status_code, 200)
        actions = resp.json()["actions"]
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["send_as"], "vera")
        self.assertIn("JIDA", action["body"])
        self.assertIn("2,100", action["body"])
        self.assertIn("38%", action["body"])


if __name__ == "__main__":
    unittest.main()
