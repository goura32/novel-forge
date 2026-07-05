"""Tests for quality gate."""

from novel_forge.quality_gate import QualityGate


class TestQualityGate:
    def test_pass(self):
        qg = QualityGate()
        result = qg.check_scene({"score": 80, "issues": []})
        assert result.passed is True

    def test_score_is_ignored_when_no_severity_issues(self):
        qg = QualityGate()
        result = qg.check_scene({"score": 50, "issues": []})
        assert result.passed is True  # No critical issues = pass

    def test_fail_critical(self):
        qg = QualityGate()
        result = qg.check_scene(
            {
                "score": 90,
                "issues": [{"severity": "致命的", "field": "test", "description": "test", "suggestion": "", "before": "", "after": ""}],
            }
        )
        assert result.passed is False

    def test_fail_blocker(self):
        qg = QualityGate()
        result = qg.check_scene(
            {
                "score": 90,
                "issues": [{"severity": "致命的", "field": "test", "description": "test", "suggestion": "", "before": "", "after": ""}],
            }
        )
        assert result.passed is False
