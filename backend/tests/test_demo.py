from backend import db
from backend.scripts.demo import seed


def test_demo_seeds_reviewable_work_without_authorizing_actions(client):
    # Adapt TestClient's root URL to the same prefixed routes used by the real HTTP client.
    class API:
        def request(self, method, path, **kwargs):
            return client.request(method, "/api/v1" + path, **kwargs)

    result = seed(API())
    assert client.get(f"/api/v1/actions/{result['action_id']}").json()["data"]["state"] == "draft"
    with db.transaction() as connection:
        assert not db.all_records(connection, "approval")
        assert not db.all_records(connection, "job")
        assert not db.get(connection, result["policy_id"])["data"]["active"]
        assert not db.all_records(connection, "rule")[0]["data"]["confirmed"]
