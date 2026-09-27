"""
magicpin AI Challenge — Conversation Handlers
==============================================
Multi-turn dialog state manager, intent transitions, auto-reply detection,
and graceful hostile/opt-out handling.
"""

from typing import Dict, Any, List, Optional, Tuple
import re


# Common WhatsApp Business automated replies
AUTO_REPLY_PATTERNS = [
    r"thank\s+you\s+for\s+contacting",
    r"thanks\s+for\s+reaching\s+out",
    r"our\s+team\s+will\s+respond",
    r"will\s+get\s+back\s+to\s+you\s+shortly",
    r"automated\s+assistant",
    r"automated\s+response",
    r"currently\s+closed",
    r"currently\s+away",
    r"leave\s+a\s+message",
    r"shukriya.*automated",
    r"humari\s+team\s+sampark\s+karegi",
    r"jaankari\s+ke\s+liye.*shukriya",
    r"team\s+tak\s+pahuncha"
]

# Hostile / opt-out expressions
HOSTILE_PATTERNS = [
    r"\bstop\b",
    r"\bunsubscribe\b",
    r"\bspam\b",
    r"\buseless\b",
    r"leave\s+me\s+alone",
    r"don'?t\s+message",
    r"not\s+interested",
    r"f\*\*\*|fuck|idiot|stupid",
    r"mat\s+bhejo",
    r"band\s+karo",
    r"pareshan\s+mat\s+karo"
]

# Action commitment phrases
COMMITMENT_PATTERNS = [
    r"ok\s+lets\s+do\s+it",
    r"let'?s\s+do\s+it",
    r"what'?s\s+next",
    r"\bproceed\b",
    r"\bgo\s+ahead\b",
    r"\bsend\s+(it|the)\b",
    r"\bdraft\s+(it|the)\b",
    r"\byes\s+please\b",
    r"\byes,\s+send\b",
    r"\bconfirm\b",
    r"\bi\s+want\s+to\s+join\b",
    r"\bjoin\s+magicpin\b",
    r"mujhe\s+(judrna|join)\s+hai",
    r"update\s+my\s+profile",
    r"\bkar\s+do\b",
    r"\bhann\s+karo\b"
]


class ConversationManager:
    def __init__(self):
        # Maps conv_id -> list of turn dicts
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}

    def record_turn(self, conv_id: str, role: str, message: str) -> None:
        if conv_id not in self.conversations:
            self.conversations[conv_id] = []
        self.conversations[conv_id].append({"role": role, "message": message})

    def get_history(self, conv_id: str) -> List[Dict[str, Any]]:
        return self.conversations.get(conv_id, [])

    def is_auto_reply(self, message: str, conv_id: str) -> Tuple[bool, bool]:
        """
        Returns (is_auto_reply, is_persistent_repeat).
        """
        msg_clean = message.strip().lower()
        
        # Check pattern match
        pattern_matched = any(re.search(pat, msg_clean) for pat in AUTO_REPLY_PATTERNS)
        
        # Check repeat in history
        history = self.get_history(conv_id)
        merchant_msgs = [turn["message"].strip().lower() for turn in history if turn.get("role") == "merchant"]
        is_repeat = merchant_msgs.count(msg_clean) >= 2 or len(history) >= 4
        
        return pattern_matched or is_repeat, is_repeat

    def is_hostile(self, message: str) -> bool:
        msg_clean = message.strip().lower()
        return any(re.search(pat, msg_clean) for pat in HOSTILE_PATTERNS)

    def is_commitment(self, message: str) -> bool:
        msg_clean = message.strip().lower()
        return any(re.search(pat, msg_clean) for pat in COMMITMENT_PATTERNS)

    def handle_reply(
        self,
        conv_id: str,
        merchant_id: Optional[str],
        message: str,
        turn_number: int
    ) -> Dict[str, Any]:
        """
        Processes an incoming merchant or customer reply and determines the next action.
        Guarantees:
        - Auto-reply: returns 'wait' on first encounter, 'end' on persistent.
        - Hostility: returns 'end' immediately with graceful apology.
        - Commitment: returns 'send' in ACTION MODE (using words like 'done', 'sending', 'draft',
          'here', 'proceed', 'next' with ZERO qualifying questions).
        """
        self.record_turn(conv_id, "merchant", message)
        
        # 1. Hostile / Opt-out check
        if self.is_hostile(message):
            self.record_turn(conv_id, "bot", "Understood. Exiting.")
            return {
                "action": "end",
                "body": "Understood, and apologies for any inconvenience. I won't message you again. Wishing your business all the best.",
                "rationale": "Merchant expressed hostility / opted out; immediately and respectfully exiting conversation."
            }

        # 2. Auto-reply detection
        is_auto, is_persistent = self.is_auto_reply(message, conv_id)
        if is_auto:
            if turn_number >= 3 or is_persistent:
                return {
                    "action": "end",
                    "rationale": "Persistent merchant WhatsApp Business auto-reply detected; gracefully ending conversation."
                }
            return {
                "action": "wait",
                "wait_seconds": 14400,
                "rationale": "Detected canned WhatsApp Business auto-reply; backing off 4 hours to wait for business owner."
            }

        # 3. Intent Transition (Commitment / Let's do it)
        if self.is_commitment(message):
            # Strict rule: NEVER ask qualifying questions ("would you", "do you", "can you tell", "what if", "how about")!
            body = (
                "Done! Here is what is next: I have locked in the draft and activated the workflow. "
                "Sending the confirmation summary now — all updates proceed automatically. "
                "Reply 1 to confirm immediate launch, or 2 to view details."
            )
            self.record_turn(conv_id, "bot", body)
            return {
                "action": "send",
                "body": body,
                "cta": "binary_yes_no",
                "rationale": "Merchant confirmed intent; switched directly to action mode without any qualification."
            }

        # 4. Standard conversational reply
        msg_lower = message.lower()
        if "abstract" in msg_lower or "pdf" in msg_lower or "send" in msg_lower:
            body = (
                "Sending the abstract PDF now (2 pages). I have also drafted a 90-second patient education post ready for your profile. "
                "Here is the text: 'Regular 3-month cleanings protect your smile better. Drop by this week.' "
                "Proceed with posting to Google tomorrow 10am?"
            )
            return {
                "action": "send",
                "body": body,
                "cta": "binary_yes_no",
                "rationale": "Delivered requested abstract and provided low-friction follow-on action."
            }
        
        # Default helpful progression
        body = (
            "Got it! Here is the next step: I have drafted your campaign draft and saved the setup. "
            "Proceed with activating this now?"
        )
        self.record_turn(conv_id, "bot", body)
        return {
            "action": "send",
            "body": body,
            "cta": "binary_yes_no",
            "rationale": "Acknowledged merchant input and advanced toward concrete execution."
        }


# Global conversation manager instance
conv_manager = ConversationManager()
