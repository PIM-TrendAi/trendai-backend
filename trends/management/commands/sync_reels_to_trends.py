"""
Management command: sync_reels_to_trends
Converts scraped facebook_reels into Trend entries grouped by niche/keyword.

Usage:
    python manage.py sync_reels_to_trends
    python manage.py sync_reels_to_trends --niche tech
    python manage.py sync_reels_to_trends --dry-run
"""
import re
from collections import Counter, defaultdict
from django.core.management.base import BaseCommand
from trends.models import FacebookReel, Trend


# Map niche slugs to human-readable hashtag prefixes and score ranges
NICHE_CONFIG = {
    'tech':        {'tag_prefix': 'Tech',        'color_start': '#6C5CE7', 'color_end': '#00C6FF'},
    'radio':       {'tag_prefix': 'Media',       'color_start': '#FD79A8', 'color_end': '#E84393'},
    'fitness':     {'tag_prefix': 'Fitness',     'color_start': '#00B894', 'color_end': '#55EFC4'},
    'finance':     {'tag_prefix': 'Finance',     'color_start': '#FDCB6E', 'color_end': '#E17055'},
    'entertainment': {'tag_prefix': 'Entertainment', 'color_start': '#A29BFE', 'color_end': '#6C5CE7'},
    'gaming':      {'tag_prefix': 'Gaming',      'color_start': '#00CEC9', 'color_end': '#55EFC4'},
    'fashion':     {'tag_prefix': 'Fashion',     'color_start': '#FD79A8', 'color_end': '#E17055'},
    'art':         {'tag_prefix': 'Art',         'color_start': '#E17055', 'color_end': '#FDCB6E'},
    'motivation':  {'tag_prefix': 'Motivation',  'color_start': '#74B9FF', 'color_end': '#0984E3'},
}

STOPWORDS = {'de', 'la', 'le', 'les', 'du', 'et', 'en', 'un', 'une', 'des', 'à', 'au',
             'est', 'sur', 'pour', 'par', 'pas', 'plus', 'avec', 'its', 'the', 'a', 'an',
             'of', 'in', 'to', 'is', 'it', 'at', 'on', 'are', 'was', 'we', 'i', 'this', 'that',
             'que', 'qui', 'ce', 'se', 'sa', 'son', 'ses', 'leur', 'leurs', 'si', 'ou', 'ni',
             'http', 'https', 'www', 'com', 'facebook', 'instagram', 'tiktok', 'reel', 'video'}


def extract_keywords(reels, top_n=5):
    """Extract most frequent meaningful words from reel texts."""
    words = []
    for reel in reels:
        text = (reel.text or '') + ' ' + (reel.reel_url or '')
        tokens = re.findall(r"[a-zA-ZÀ-ÿ]{4,}", text.lower())
        words.extend(t for t in tokens if t not in STOPWORDS)
    counter = Counter(words)
    return [w for w, _ in counter.most_common(top_n)]


def build_trend_from_reels(niche: str, reels) -> dict:
    """Convert a group of facebook_reels into a Trend dict."""
    config = NICHE_CONFIG.get(niche.lower(), {
        'tag_prefix': niche.title(),
        'color_start': '#6C5CE7',
        'color_end': '#00C6FF',
    })
    
    total_plays = sum(r.play_count for r in reels)
    keywords = extract_keywords(reels)
    hashtag = f"#{config['tag_prefix']}TN" if not keywords else f"#{keywords[0].title()}TN"
    
    # Normalize score (0-100) based on count of reels
    reel_count = len(reels)
    score = min(50 + reel_count * 2, 98.0)
    growth = min(100 + reel_count * 3.5, 350.0)
    
    views_raw = total_plays or (reel_count * 5000)
    views_str = f"{views_raw/1_000_000:.1f}M" if views_raw >= 1_000_000 else f"{views_raw//1000}K"
    
    analysis_texts = [
        f"{reel_count} reels scraped from Facebook in this niche.",
        f"Top keywords: {', '.join(keywords[:3]) if keywords else 'N/A'}.",
        "Facebook algorithm is actively promoting this content type.",
    ]

    return dict(
        hashtag=hashtag,
        platform='Facebook',
        score=round(score, 1),
        growth=round(growth, 1),
        views=views_str,
        type='video',
        color_start=config['color_start'],
        color_end=config['color_end'],
        analysis=analysis_texts,
        target_audience='18-45',
        avg_video_length='30-90s',
        dominant_format='Reels',
        best_posting_time='6-9 PM',
        total_views=views_raw,
        total_likes=int(views_raw * 0.04),
        total_shares=int(views_raw * 0.01),
        chart_data=[
            {'day': d, 'value': max(10, int(score * (0.6 + d * 0.06)))}
            for d in range(1, 8)
        ],
    )


class Command(BaseCommand):
    help = 'Sync facebook_reels → trends table (platform=Facebook)'

    def add_arguments(self, parser):
        parser.add_argument('--niche', type=str, default=None, help='Only process a specific niche')
        parser.add_argument('--dry-run', action='store_true', help='Preview without saving')

    def handle(self, *args, **options):
        target_niche = options.get('niche')
        dry_run = options.get('dry_run', False)

        qs = FacebookReel.objects.all()
        if target_niche:
            qs = qs.filter(niche__icontains=target_niche)

        # Group reels by niche
        grouped = defaultdict(list)
        for reel in qs:
            key = (reel.niche or 'general').lower()
            grouped[key].append(reel)

        self.stdout.write(f"Found {len(grouped)} niche group(s): {list(grouped.keys())}")

        created_count = 0
        updated_count = 0
        for niche, reels in grouped.items():
            trend_data = build_trend_from_reels(niche, reels)
            self.stdout.write(
                f"  [{niche}] → {trend_data['hashtag']} | score={trend_data['score']} | "
                f"growth={trend_data['growth']}% | reels={len(reels)}"
            )
            if not dry_run:
                obj, created = Trend.objects.update_or_create(
                    hashtag=trend_data['hashtag'],
                    platform='Facebook',
                    defaults={k: v for k, v in trend_data.items() if k not in ('hashtag', 'platform')},
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing saved.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Done! Created {created_count} new trend(s), updated {updated_count}.'
            ))
