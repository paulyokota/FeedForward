"""
Classifier tests using labeled fixtures.

Run with: pytest tests/test_classifier.py -v
"""

import json
import pytest
from pathlib import Path
from collections import Counter

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES_FILE = PROJECT_ROOT / "data" / "labeled_fixtures.json"


def load_fixtures():
    """Load labeled fixtures."""
    with open(FIXTURES_FILE) as f:
        return json.load(f)["labeled"]


def train_test_split(fixtures, test_ratio=0.3, seed=42):
    """
    Stratified split to ensure each issue type appears in both sets.
    """
    import random
    random.seed(seed)

    # Group by issue type
    by_type = {}
    for f in fixtures:
        t = f["issue_type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(f)

    train, test = [], []
    for issue_type, samples in by_type.items():
        random.shuffle(samples)
        n_test = max(1, int(len(samples) * test_ratio))
        test.extend(samples[:n_test])
        train.extend(samples[n_test:])

    return train, test


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def all_fixtures():
    return load_fixtures()


@pytest.fixture(scope="module")
def train_fixtures(all_fixtures):
    train, _ = train_test_split(all_fixtures)
    return train


@pytest.fixture(scope="module")
def test_fixtures(all_fixtures):
    _, test = train_test_split(all_fixtures)
    return test


# -----------------------------------------------------------------------------
# Import classifier
# -----------------------------------------------------------------------------

import sys
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from classifier import classify_conversation


# -----------------------------------------------------------------------------
# Evaluation helpers
# -----------------------------------------------------------------------------

def accuracy(predictions: list, labels: list) -> float:
    """Calculate accuracy."""
    if not predictions:
        return 0.0
    correct = sum(1 for p, l in zip(predictions, labels) if p == l)
    return correct / len(predictions)


def precision_recall(predictions: list, labels: list, positive_class=True) -> tuple:
    """Calculate precision and recall for binary classification."""
    tp = sum(1 for p, l in zip(predictions, labels) if p == positive_class and l == positive_class)
    fp = sum(1 for p, l in zip(predictions, labels) if p == positive_class and l != positive_class)
    fn = sum(1 for p, l in zip(predictions, labels) if p != positive_class and l == positive_class)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    return precision, recall


def per_class_accuracy(predictions: list, labels: list) -> dict:
    """Calculate accuracy per class."""
    classes = set(labels)
    results = {}
    for cls in classes:
        cls_preds = [p for p, l in zip(predictions, labels) if l == cls]
        cls_labels = [l for l in labels if l == cls]
        results[cls] = accuracy(cls_preds, cls_labels)
    return results


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------

class TestClassifierImplementation:
    """Test that classifier is implemented."""

    def test_classifier_exists(self):
        """Classifier function should be implemented."""
        try:
            result = classify_conversation("test message")
            assert isinstance(result, dict)
        except NotImplementedError:
            pytest.fail("Classifier not yet implemented")

    def test_classifier_returns_required_fields(self):
        """Classifier should return all required fields."""
        result = classify_conversation("How do I cancel my subscription?")

        assert "issue_type" in result
        assert "sentiment" in result
        assert "churn_risk" in result
        assert "priority" in result


class TestIssueTypeClassification:
    """Test issue type classification accuracy."""

    VALID_TYPES = [
        "bug_report", "feature_request", "product_question",
        "plan_question", "marketing_question", "billing",
        "account_access", "feedback", "other"
    ]

    def test_returns_valid_issue_type(self):
        """Should return a valid issue type."""
        result = classify_conversation("My pins aren't posting")
        assert result["issue_type"] in self.VALID_TYPES

    def test_overall_accuracy(self, test_fixtures):
        """Issue type accuracy should be >= 80%."""
        predictions = []
        labels = []

        for fixture in test_fixtures:
            result = classify_conversation(fixture["input_text"])
            predictions.append(result["issue_type"])
            labels.append(fixture["issue_type"])

        acc = accuracy(predictions, labels)
        assert acc >= 0.80, f"Issue type accuracy {acc:.1%} < 80% threshold"

    def test_no_zero_recall_category(self, test_fixtures):
        """No category should have 0% recall (catastrophic failure)."""
        predictions = []
        labels = []

        for fixture in test_fixtures:
            result = classify_conversation(fixture["input_text"])
            predictions.append(result["issue_type"])
            labels.append(fixture["issue_type"])

        per_class = per_class_accuracy(predictions, labels)
        for cls, acc in per_class.items():
            assert acc > 0, f"Category {cls} has 0% recall"


class TestChurnRiskDetection:
    """Test churn risk detection."""

    def test_returns_boolean(self):
        """Churn risk should be boolean."""
        result = classify_conversation("I want to cancel")
        assert isinstance(result["churn_risk"], bool)

    def test_churn_recall(self, test_fixtures):
        """Churn risk recall should be >= 85%."""
        predictions = []
        labels = []

        for fixture in test_fixtures:
            result = classify_conversation(fixture["input_text"])
            predictions.append(result["churn_risk"])
            labels.append(fixture.get("churn_risk", False))

        _, recall = precision_recall(predictions, labels, positive_class=True)
        assert recall >= 0.85, f"Churn risk recall {recall:.1%} < 85% threshold"

    def test_churn_precision(self, test_fixtures):
        """Churn risk precision should be >= 75%."""
        predictions = []
        labels = []

        for fixture in test_fixtures:
            result = classify_conversation(fixture["input_text"])
            predictions.append(result["churn_risk"])
            labels.append(fixture.get("churn_risk", False))

        precision, _ = precision_recall(predictions, labels, positive_class=True)
        assert precision >= 0.75, f"Churn risk precision {precision:.1%} < 75% threshold"


class TestSentimentAnalysis:
    """Test sentiment analysis."""

    VALID_SENTIMENTS = ["frustrated", "neutral", "satisfied"]

    def test_returns_valid_sentiment(self):
        """Should return a valid sentiment."""
        result = classify_conversation("This is so annoying!")
        assert result["sentiment"] in self.VALID_SENTIMENTS

    def test_sentiment_accuracy(self, test_fixtures):
        """Sentiment accuracy should be >= 75%."""
        predictions = []
        labels = []

        for fixture in test_fixtures:
            result = classify_conversation(fixture["input_text"])
            predictions.append(result["sentiment"])
            labels.append(fixture["sentiment"])

        acc = accuracy(predictions, labels)
        assert acc >= 0.75, f"Sentiment accuracy {acc:.1%} < 75% threshold"


class TestPriorityScoring:
    """Test priority scoring."""

    VALID_PRIORITIES = ["urgent", "high", "normal", "low"]

    def test_returns_valid_priority(self):
        """Should return a valid priority."""
        result = classify_conversation("I can't log in!")
        assert result["priority"] in self.VALID_PRIORITIES

    def test_priority_accuracy(self, test_fixtures):
        """Priority accuracy should be >= 70%."""
        predictions = []
        labels = []

        for fixture in test_fixtures:
            result = classify_conversation(fixture["input_text"])
            predictions.append(result["priority"])
            labels.append(fixture["priority"])

        acc = accuracy(predictions, labels)
        assert acc >= 0.70, f"Priority accuracy {acc:.1%} < 70% threshold"


class TestLatency:
    """Test classifier performance."""

    def test_single_classification_under_3s(self, test_fixtures):
        """Single classification should complete in < 3 seconds."""
        import time

        sample = test_fixtures[0]
        start = time.time()
        classify_conversation(sample["input_text"])
        elapsed = time.time() - start

        assert elapsed < 3.0, f"Classification took {elapsed:.1f}s, exceeds 3s limit"


# -----------------------------------------------------------------------------
# Evaluation runner (for manual testing)
# -----------------------------------------------------------------------------

def run_full_evaluation():
    """Run full evaluation and print results."""
    fixtures = load_fixtures()
    train, test = train_test_split(fixtures)

    print(f"Train: {len(train)}, Test: {len(test)}")
    print(f"Test distribution: {Counter(f['issue_type'] for f in test)}")

    # Run predictions
    results = {
        "issue_type": {"predictions": [], "labels": []},
        "sentiment": {"predictions": [], "labels": []},
        "churn_risk": {"predictions": [], "labels": []},
        "priority": {"predictions": [], "labels": []},
    }

    for fixture in test:
        try:
            pred = classify_conversation(fixture["input_text"])
            for key in results:
                results[key]["predictions"].append(pred[key])
                results[key]["labels"].append(fixture.get(key))
        except NotImplementedError:
            print("Classifier not implemented yet")
            return

    # Calculate metrics
    print("\n=== EVALUATION RESULTS ===\n")

    issue_acc = accuracy(results["issue_type"]["predictions"], results["issue_type"]["labels"])
    print(f"Issue Type Accuracy: {issue_acc:.1%} (target: 80%)")

    sent_acc = accuracy(results["sentiment"]["predictions"], results["sentiment"]["labels"])
    print(f"Sentiment Accuracy: {sent_acc:.1%} (target: 75%)")

    churn_prec, churn_rec = precision_recall(
        results["churn_risk"]["predictions"],
        results["churn_risk"]["labels"],
        positive_class=True
    )
    print(f"Churn Risk Precision: {churn_prec:.1%} (target: 75%)")
    print(f"Churn Risk Recall: {churn_rec:.1%} (target: 85%)")

    prio_acc = accuracy(results["priority"]["predictions"], results["priority"]["labels"])
    print(f"Priority Accuracy: {prio_acc:.1%} (target: 70%)")


if __name__ == "__main__":
    run_full_evaluation()
