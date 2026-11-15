"""NLP unit tests — no database required."""
from app.nlp.sentiment import analyze_sentiment
from app.nlp.language import detect_language
from app.nlp.intents import detect_intents
from app.nlp.aspects import extract_aspects
from app.nlp.aspect_packs import get_pack


def test_positive_english():
    r = analyze_sentiment("Absolutely love this product, amazing quality!")
    assert r.label == "positive"
    assert r.score > 0.2


def test_negation_flips():
    r = analyze_sentiment("This is not good at all")
    assert r.label in ("negative", "neutral", "mixed")
    assert r.score <= 0.2


def test_mixed_clause_detection():
    r = analyze_sentiment("The camera is great but the battery is terrible")
    assert r.label == "mixed"
    assert r.score >= -1.0 and r.score <= 1.0


def test_roman_urdu_negative():
    r = analyze_sentiment("Bohat bekar product hai, paisa zaya")
    assert r.label == "negative"


def test_roman_urdu_positive():
    r = analyze_sentiment("Zabardast quality hai, bohat acha laga")
    assert r.label == "positive"


def test_uncertain_not_forced():
    r = analyze_sentiment("ok")
    assert r.label in ("neutral", "uncertain")
    assert 0.2 <= r.confidence <= 0.95


def test_confidence_bounds():
    r = analyze_sentiment("Great amazing excellent wonderful brilliant fantastic superb!")
    assert r.confidence <= 0.95
    assert r.confidence >= 0.22


def test_language_detection():
    assert detect_language("This camera is amazing").language == "english"
    assert detect_language("ye product bohat acha hai").language in ("roman_urdu", "mixed")
    assert detect_language("یہ پروڈکٹ بہت اچھا ہے").language in ("urdu", "mixed")


def test_intent_price_inquiry():
    flags = detect_intents("Price please?", "price please")
    assert flags["price_inquiry"] is True
    assert flags["purchase_intent"] is True


def test_intent_delivery():
    flags = detect_intents("Delivery kitne din mein hogi?", "delivery kitne din mein hogi")
    assert flags["delivery_concern"] is True


def test_youtube_content_pack():
    pack = get_pack("youtube_content")
    assert "content_quality" in pack
    assert "battery" not in pack
