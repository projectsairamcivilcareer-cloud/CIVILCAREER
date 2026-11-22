import os
import unittest

# Use a test-only secret before importing the application.
os.environ["SECRET_KEY"] = "csrf-integration-test-secret-not-for-production"

from app import app, CSRF_SESSION_KEY


# Test-only endpoint: verifies CSRF middleware without depending on application routes.
@app.route("/_csrf-test-post", methods=["POST"])
def csrf_test_post():
    return "", 204


class CsrfMiddlewareIntegrationTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SECRET_KEY=os.environ["SECRET_KEY"])
        self.client = app.test_client()

    def test_get_request_creates_session_token(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as sess:
            token = sess.get(CSRF_SESSION_KEY)
        self.assertTrue(token)
        self.assertGreaterEqual(len(token), 32)

    def test_post_without_token_is_rejected(self):
        response = self.client.post("/_csrf-test-post")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"CSRF validation failed", response.data)

    def test_post_with_invalid_token_is_rejected(self):
        with self.client.session_transaction() as sess:
            sess[CSRF_SESSION_KEY] = "expected-token"
        response = self.client.post("/_csrf-test-post", data={"csrf_token": "wrong-token"})
        self.assertEqual(response.status_code, 400)

    def test_post_with_valid_form_token_is_allowed(self):
        with self.client.session_transaction() as sess:
            sess[CSRF_SESSION_KEY] = "valid-test-token"
        response = self.client.post("/_csrf-test-post", data={"csrf_token": "valid-test-token"})
        self.assertEqual(response.status_code, 204)

    def test_post_with_valid_header_token_is_allowed(self):
        with self.client.session_transaction() as sess:
            sess[CSRF_SESSION_KEY] = "valid-test-token"
        response = self.client.post("/_csrf-test-post", headers={"X-CSRF-Token": "valid-test-token"})
        self.assertEqual(response.status_code, 204)


if __name__ == "__main__":
    unittest.main()
