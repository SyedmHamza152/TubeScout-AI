"""Shared constants: formats, objectives, provenance labels, quota costs."""
from __future__ import annotations

SUPPORTED_FORMATS: dict[str, str] = {
    "in_stream": "In-Stream Ads",
    "shorts": "Shorts Ads",
    "in_feed": "In-Feed Video Ads",
}

MARKETING_OBJECTIVES: list[str] = [
    "Brand Awareness",
    "Video Views",
    "Website Traffic",
    "Leads",
    "Sales / Conversions",
]

SUBTYPE_TO_FORMAT: dict[str, str] = {
    "VIDEO_OUTSTREAM": "in_feed",
    "VIDEO_ACTION": "in_stream",
    "VIDEO_RESPONSIVE": "in_stream",
    "VIDEO_NON_SKIPPABLE": "in_stream",
    "VIDEO_BUMPER": "in_stream",
    "VIDEO_TRUE_VIEW_IN_DISPLAY": "in_feed",
    "VIDEO_EFFECTIVE_REACH": "in_stream",
}

# Mandatory provenance labels (data policy)
LABEL_LIVE = "LIVE DATA"
LABEL_PREDICTION = "MODEL PREDICTION"
LABEL_ESTIMATE = "ESTIMATED SCENARIO"
LABEL_INFERENCE = "INFERENCE"
LABEL_USER_INPUT = "USER INPUT"
LABEL_INSUFFICIENT = "INSUFFICIENT DATA"

SENTIMENT_CLASSES = ("positive", "negative", "neutral", "mixed", "uncertain")

QUOTA_COST = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1, "commentThreads": 1}

ASPECT_PACKS = ("product", "youtube_content")

AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55+"]
DEVICES = ["mobile", "desktop", "tablet", "tv"]

MARKET_CITIES = {
    "PK": ["Karachi", "Lahore", "Islamabad", "Rawalpindi", "Faisalabad", "Multani", "Peshawar", "Quetta"],
    "US": ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"],
    "UK": ["London", "Manchester", "Birmingham", "Leeds", "Glasgow"],
    "AE": ["Dubai", "Abu Dhabi", "Sharjah"],
    "SA": ["Riyadh", "Jeddah", "Dammam"],
}
