import json
from pathlib import Path


def test_normalized_graph_entities_are_complete() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "processed"
        / "graph_entities.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))

    assert len(data["restaurants"]) == 20
    assert len(data["festivals"]) == 3
    assert len(data["transport_stops"]) == 7
    assert sum(
        "Wheelchair" in features
        for features in data["attraction_accessibility"].values()
    ) == 5
    assert "destination-level" in data["proximity_basis"]
