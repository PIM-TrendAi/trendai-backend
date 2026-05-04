import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from trends.models import ThreadsPost

# 1. Clean up invalid data
ThreadsPost.objects.filter(post_id='undefined').delete()

# 2. Add sample posts (based on your scraped data)
sample_posts = [
    {
        "post_id": "3874529470695193469",
        "post_url": "https://www.threads.net/post/DXFGAaEkbt9",
        "username": "natgeo",
        "text": "South Sudan for a stunning and rare view of the world’s largest animal migration. Ancient Indus Valley metropolis of Mohenjo Daro...",
        "like_count": 18,
        "niche": "Threads Trends",
        "has_video": False,
        "thumbnail_url": "https://images.pexels.com/photos/1743366/pexels-photo-1743366.jpeg?auto=compress&cs=tinysrgb&w=600"
    },
    {
        "post_id": "3874529470695193470",
        "username": "traveler_pro",
        "text": "Check out this amazing sunset in Bali! #travel #threads",
        "like_count": 142,
        "niche": "Threads Trends",
        "has_video": True,
        "thumbnail_url": "https://images.pexels.com/photos/1072179/pexels-photo-1072179.jpeg?auto=compress&cs=tinysrgb&w=400"
    },
    {
        "post_id": "3874529470695193471",
        "username": "cooking_master",
        "text": "Best pasta recipe you will ever try. 🍝",
        "like_count": 89,
        "niche": "Threads Trends",
        "has_video": True,
        "thumbnail_url": "https://images.pexels.com/photos/1437267/pexels-photo-1437267.jpeg?auto=compress&cs=tinysrgb&w=400"
    },
    {
        "post_id": "3874529470695193472",
        "username": "tech_insider",
        "text": "The new AI chips are here and they are insane. ⚡",
        "like_count": 567,
        "niche": "Threads Trends",
        "has_video": False,
        "thumbnail_url": "https://images.pexels.com/photos/2582937/pexels-photo-2582937.jpeg?auto=compress&cs=tinysrgb&w=400"
    },
    {
        "post_id": "3874529470695193473",
        "username": "fitness_motivation",
        "text": "No excuses. 5 AM club. 🏃‍♂️",
        "like_count": 312,
        "niche": "Threads Trends",
        "has_video": True,
        "thumbnail_url": "https://images.pexels.com/photos/1552242/pexels-photo-1552242.jpeg?auto=compress&cs=tinysrgb&w=400"
    },
    {
        "post_id": "3874529470695193474",
        "username": "nature_shots",
        "text": "The mountains are calling. 🏔️",
        "like_count": 25,
        "niche": "Threads Trends",
        "has_video": False,
        "thumbnail_url": "https://images.pexels.com/photos/417074/pexels-photo-417074.jpeg?auto=compress&cs=tinysrgb&w=400"
    }
]

for p in sample_posts:
    ThreadsPost.objects.update_or_create(post_id=p['post_id'], defaults=p)

print(f"Successfully populated {len(sample_posts)} items into the database!")
