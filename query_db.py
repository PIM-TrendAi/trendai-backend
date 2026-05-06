import os
import sys
import django

sys.path.append('/Users/apple/Desktop/PIM 2/trendai-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from trends.models import FacebookReel
from django.db.models import Count

summary = FacebookReel.objects.values('niche').annotate(count=Count('id'))
print(list(summary))
