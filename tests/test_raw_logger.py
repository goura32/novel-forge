
import json
from novel_tool.llm.raw_logger import RawLogger


def test_raw_logger_writes_debuggable_json(tmp_path):
    logger = RawLogger(tmp_path)
    path = logger.write("series_plan", {"request": {"model": "m"}, "response_raw": "{}", "api_key": "secret"})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["kind"] == "series_plan"
    assert "created_at" in data
    assert "api_key" not in data["payload"]
