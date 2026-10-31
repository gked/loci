"""A rebound Host is refused by the real server, not just by the test client.

DNS rebinding sends the attacker's domain name as Host to 127.0.0.1. No browser
is needed to show the refusal: the header is all the attack changes.
"""
import httpx


def test_a_foreign_host_is_refused_and_the_real_one_is_served(api_server):
    served = httpx.get(f"{api_server}/api/health")
    rebound = httpx.get(f"{api_server}/api/nodes", headers={"Host": "evil.example"})

    assert served.status_code == 200
    assert rebound.status_code == 403
    assert "allowed_hosts" in rebound.text
