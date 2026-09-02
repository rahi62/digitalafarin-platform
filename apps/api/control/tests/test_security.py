import unittest

from control.security import issue_secret, parse_secret, verify_secret


class SecurityTests(unittest.TestCase):
    def test_agent_secret_round_trip(self):
        issued = issue_secret("agent")
        prefix, secret = parse_secret(issued.cleartext, "agent")

        self.assertEqual(prefix, issued.prefix)
        self.assertTrue(issued.cleartext.startswith("da_agent_"))
        self.assertEqual(len(issued.digest), 64)
        self.assertTrue(verify_secret(secret, issued.digest))
        self.assertFalse(verify_secret(secret + "x", issued.digest))

    def test_wrong_kind_is_rejected(self):
        issued = issue_secret("enroll")

        with self.assertRaises(ValueError):
            parse_secret(issued.cleartext, "agent")

    def test_unknown_secret_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            issue_secret("root")
