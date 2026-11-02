import json
from urllib.parse import parse_qs, urlparse

from fdc import FdcClient, extract_macros


def test_extract_macros_from_search_and_detail_shapes():
    search_food = {
        "foodNutrients": [
            {"nutrientId": 1008, "nutrientName": "Energy", "unitName": "KCAL", "value": 389},
            {"nutrientId": 1003, "nutrientName": "Protein", "unitName": "G", "value": 16.9},
        ]
    }
    detail_food = {
        "foodNutrients": [
            {"nutrient": {"id": 1008, "name": "Energy", "unitName": "kcal"}, "amount": 208},
            {"nutrient": {"id": 1003, "name": "Protein", "unitName": "g"}, "amount": 20.4},
        ]
    }
    assert extract_macros(search_food) == (389, 16.9)
    assert extract_macros(detail_food) == (208, 20.4)


def test_search_and_detail_use_transport_not_network():
    calls = []

    def transport(url):
        calls.append(url)
        parsed = urlparse(url)
        if parsed.path.endswith("/foods/search"):
            query = parse_qs(parsed.query)
            assert query["api_key"] == ["test-key"]
            assert query["query"] == ["oats, raw"]
            return {"foods": [{"fdcId": 171705, "description": "Oats, raw"}]}
        assert parsed.path.endswith("/food/171705")
        assert parse_qs(parsed.query)["api_key"] == ["test-key"]
        return {
            "fdcId": 171705,
            "description": "Oats, raw",
            "foodNutrients": [
                {"nutrientId": 1008, "value": 389, "unitName": "KCAL"},
                {"nutrientId": 1003, "value": 16.9, "unitName": "G"},
            ],
        }

    client = FdcClient(api_key="test-key", transport=transport, min_interval=0)
    found = client.lookup("oats, raw")
    assert found["fdc_id"] == 171705
    assert found["kcal_per_100g"] == 389
    assert len(calls) == 2
    again = client.lookup("oats, raw")
    assert again["description"] == "Oats, raw"
    assert len(calls) == 2


def test_disk_cache_survives_a_new_client(tmp_path):
    calls = []
    cache = tmp_path / "fdc_cache.json"

    def transport(url):
        calls.append(url)
        return {"foods": [{"fdcId": 5, "description": "Cached oats", "foodNutrients": [{"nutrientId": 1008, "value": 100}]}]}

    first = FdcClient(api_key="test-key", transport=transport, cache_path=cache, min_interval=0)
    assert first.search("oats")["foods"][0]["fdcId"] == 5
    assert cache.exists()
    saved = json.loads(cache.read_text())
    assert saved

    def boom(_url):
        raise AssertionError("cache miss")

    second = FdcClient(api_key="test-key", transport=boom, cache_path=cache, min_interval=0)
    assert second.search("oats")["foods"][0]["description"] == "Cached oats"
    assert len(calls) == 1


def test_rate_limit_paces_requests():
    clock = {"t": 0.0}
    slept = []

    def now():
        return clock["t"]

    def sleep(seconds):
        slept.append(seconds)
        clock["t"] += seconds

    def transport(_url):
        return {"ok": True}

    client = FdcClient(api_key="k", transport=transport, min_interval=0.4, now=now, sleep=sleep)
    client.search("a")
    client.search("b")
    assert slept and abs(slept[0] - 0.4) < 0.05


def test_missing_key_does_not_call_out():
    client = FdcClient(api_key="", transport=None, min_interval=0)
    assert client.lookup("oats") is None
