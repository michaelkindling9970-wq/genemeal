
def test_research_stress_page_renders(client):
    r = client.get("/research/stress-diet")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Stress, diet, and genetics" in body
    assert "Diet findings" in body
    assert "you.23andme.com/tools/data/" in body
    assert "www.23andme.org" not in body
    assert "Mediterranean" in body
