"""
Django management command to seed the database with sample trend data.
Run: python manage.py seed_data
"""
from django.core.management.base import BaseCommand
from trends.models import Trend


TRENDS = [
    {
        "hashtag": "#AIRevolution",
        "platform": "TikTok",
        "score": 94.0,
        "growth": 156.0,
        "views": "2.4M",
        "type": "hashtag",
        "color_start": "#EC4899",
        "color_end": "#A855F7",
        "analysis": [
            "AI-generated content is exploding across all platforms",
            "Tech-savvy audience highly engaged with innovation topics",
            "Perfect timing with recent AI breakthroughs",
        ],
        "target_audience": "Tech Enthusiasts 18-34",
        "avg_video_length": "45-60 seconds",
        "dominant_format": "Educational + Demo",
        "best_posting_time": "6-8 PM",
        "total_views": 8200000,
        "total_likes": 1500000,
        "total_shares": 342000,
        "chart_data": [
            {"day": "Mon", "value": 45}, {"day": "Tue", "value": 52},
            {"day": "Wed", "value": 61}, {"day": "Thu", "value": 73},
            {"day": "Fri", "value": 85}, {"day": "Sat", "value": 91},
            {"day": "Sun", "value": 94},
        ],
    },
    {
        "hashtag": "#ProductivityHacks",
        "platform": "Instagram",
        "score": 87.0,
        "growth": 89.0,
        "views": "1.8M",
        "type": "hashtag",
        "color_start": "#F97316",
        "color_end": "#EC4899",
        "analysis": ["Productivity content resonates with young professionals"],
        "target_audience": "Professionals 25-40",
        "avg_video_length": "30-45 seconds",
        "dominant_format": "Tips & Lists",
        "best_posting_time": "12 PM",
        "total_views": 5400000,
        "total_likes": 980000,
        "total_shares": 210000,
        "chart_data": [
            {"day": "Mon", "value": 38}, {"day": "Tue", "value": 50},
            {"day": "Wed", "value": 60}, {"day": "Thu", "value": 70},
            {"day": "Fri", "value": 80}, {"day": "Sat", "value": 87},
            {"day": "Sun", "value": 84},
        ],
    },
    {
        "hashtag": "Epic Transition Sound",
        "platform": "TikTok",
        "score": 91.0,
        "growth": 203.0,
        "views": "3.2M",
        "type": "audio",
        "color_start": "#3B82F6",
        "color_end": "#06B6D4",
        "analysis": ["Viral audio trending in editing communities"],
        "target_audience": "Creators 16-28",
        "avg_video_length": "15-30 seconds",
        "dominant_format": "Transition / Showcase",
        "best_posting_time": "8-10 PM",
        "total_views": 9100000,
        "total_likes": 2200000,
        "total_shares": 512000,
        "chart_data": [
            {"day": "Mon", "value": 60}, {"day": "Tue", "value": 72},
            {"day": "Wed", "value": 79}, {"day": "Thu", "value": 85},
            {"day": "Fri", "value": 88}, {"day": "Sat", "value": 91},
            {"day": "Sun", "value": 89},
        ],
    },
    {
        "hashtag": "#FinanceTips",
        "platform": "YouTube",
        "score": 82.0,
        "growth": 67.0,
        "views": "1.5M",
        "type": "hashtag",
        "color_start": "#22C55E",
        "color_end": "#10B981",
        "analysis": ["Personal finance evergreen content with high retention"],
        "target_audience": "Adults 22-45",
        "avg_video_length": "60-90 seconds",
        "dominant_format": "Educational",
        "best_posting_time": "7-9 AM",
        "total_views": 4300000,
        "total_likes": 780000,
        "total_shares": 156000,
        "chart_data": [
            {"day": "Mon", "value": 55}, {"day": "Tue", "value": 62},
            {"day": "Wed", "value": 68}, {"day": "Thu", "value": 72},
            {"day": "Fri", "value": 78}, {"day": "Sat", "value": 82},
            {"day": "Sun", "value": 80},
        ],
    },
    {
        "hashtag": "#TechReview",
        "platform": "YouTube",
        "score": 88.0,
        "growth": 112.0,
        "views": "2.1M",
        "type": "video",
        "color_start": "#EF4444",
        "color_end": "#F97316",
        "analysis": ["Gadget review content sustains high watch time"],
        "target_audience": "Tech Buyers 20-40",
        "avg_video_length": "60-90 seconds",
        "dominant_format": "Review / Comparison",
        "best_posting_time": "5-7 PM",
        "total_views": 6800000,
        "total_likes": 1100000,
        "total_shares": 280000,
        "chart_data": [
            {"day": "Mon", "value": 50}, {"day": "Tue", "value": 60},
            {"day": "Wed", "value": 70}, {"day": "Thu", "value": 78},
            {"day": "Fri", "value": 85}, {"day": "Sat", "value": 88},
            {"day": "Sun", "value": 86},
        ],
    },
    {
        "hashtag": "#FitnessMotivation",
        "platform": "Instagram",
        "score": 85.0,
        "growth": 98.0,
        "views": "1.9M",
        "type": "hashtag",
        "color_start": "#A855F7",
        "color_end": "#EC4899",
        "analysis": ["Fitness content peaks in January and post-summer"],
        "target_audience": "Fitness Enthusiasts 18-35",
        "avg_video_length": "30-60 seconds",
        "dominant_format": "Workout / Before-After",
        "best_posting_time": "6-8 AM",
        "total_views": 5700000,
        "total_likes": 1300000,
        "total_shares": 320000,
        "chart_data": [
            {"day": "Mon", "value": 60}, {"day": "Tue", "value": 65},
            {"day": "Wed", "value": 70}, {"day": "Thu", "value": 75},
            {"day": "Fri", "value": 80}, {"day": "Sat", "value": 85},
            {"day": "Sun", "value": 82},
        ],
    },
    {
        "hashtag": "Viral Dance Beat",
        "platform": "TikTok",
        "score": 92.0,
        "growth": 187.0,
        "views": "4.1M",
        "type": "audio",
        "color_start": "#06B6D4",
        "color_end": "#3B82F6",
        "analysis": ["Dance challenges explode engagement on TikTok"],
        "target_audience": "Gen Z 13-25",
        "avg_video_length": "15-30 seconds",
        "dominant_format": "Dance Challenge",
        "best_posting_time": "7-9 PM",
        "total_views": 12000000,
        "total_likes": 3400000,
        "total_shares": 890000,
        "chart_data": [
            {"day": "Mon", "value": 55}, {"day": "Tue", "value": 68},
            {"day": "Wed", "value": 78}, {"day": "Thu", "value": 85},
            {"day": "Fri", "value": 90}, {"day": "Sat", "value": 92},
            {"day": "Sun", "value": 88},
        ],
    },
]


class Command(BaseCommand):
    help = "Seed the database with sample trend data."

    def handle(self, *args, **kwargs):
        created = 0
        for trend_data in TRENDS:
            _, was_created = Trend.objects.get_or_create(
                hashtag=trend_data["hashtag"],
                platform=trend_data["platform"],
                defaults=trend_data,
            )
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Seeded {created} new trends ({len(TRENDS) - created} already existed)."))
