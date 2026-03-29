import sys
import os
import django

sys.path.append('c:/Users/dell/Downloads/PIMobile/trendai-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import RequestFactory
from n8n_integration.views import N8nCallbackView

factory = RequestFactory()
request = factory.post('/api/n8n/callback/', {
    'session_id': 'sess1',
    'video_url': 'http://vid',
    'tts_url': 'http://tts'
}, content_type='application/json')
view = N8nCallbackView.as_view()

try:
    response = view(request)
    print("SUCCESS")
    print(response.content)
except Exception as e:
    import traceback
    traceback.print_exc()
