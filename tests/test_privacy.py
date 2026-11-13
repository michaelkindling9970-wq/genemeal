import logging

import blocked_states as B
import app as A


def test_deny_log_records_state_not_ip(monkeypatch, caplog):
    B.clear_cache()
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CA")
    A.app.config["TESTING"] = True
    client = A.app.test_client()
    with caplog.at_level(logging.INFO, logger=A.app.logger.name):
        response = client.get("/results", headers={"X-Forwarded-For": "198.51.100.24"})
    assert response.status_code == 451
    assert "state=CA" in caplog.text
    assert "198.51.100.24" not in caplog.text
