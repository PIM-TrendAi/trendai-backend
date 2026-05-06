import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from n8n_integration.models import CreatorSession
from django.db import connection

def get_session_status_mock(session_id):
    try:
        session = CreatorSession.objects.get(session_id=session_id)
    except CreatorSession.DoesNotExist:
        return {"error": "Session not found"}

    payload = {
        "session_id": session.session_id,
        "creator_id": session.creator_id,
        "niche": session.niche,
        "status": session.status,
        "selected_video_id": session.selected_video_id,
        "script_id": None, "script_content": None, "script_status": None,
        "video_id": None, "video_url": None, "video_thumbnail": None, "video_status": None,
        "tiktok_post_url": None,
    }

    if session.platform == "facebook":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, script_content, script_text, hook, body, cta, "
                "hook_text, video_prompt, caption, hashtags, music_vibe, "
                "reel_id, video_url, status "
                "FROM facebook_generated_videos "
                "WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                [int(session.creator_id)]
            )
            row = cursor.fetchone()
            if row:
                (gen_id, script_content, script_text, hook, body, cta,
                 hook_text, video_prompt, caption, hashtags, music_vibe,
                 reel_id, video_url, gen_status) = row
                full_script = script_content or script_text or ""
                payload["script_id"] = str(gen_id)
                payload["script_content"] = full_script
                payload["script_status"] = gen_status
                
                # Applying the new logic
                if gen_status == "done":
                    payload["status"] = "ready"
                elif gen_status == "processing":
                    if full_script:
                        payload["status"] = "script_pending"
                    else:
                        payload["status"] = "processing"
                elif gen_status == "approved":
                    payload["status"] = "processing"
                elif gen_status in ("published", "posted"):
                    payload["status"] = "posted"
                elif gen_status == "rejected":
                    payload["status"] = "declined"
                else:
                    payload["status"] = "script_generation"

                if full_script and gen_status in ("processing", "done", "approved"):
                    payload["script_status"] = "pending_approval"
                    
    return payload

session_id = "1_1777219794494"
result = get_session_status_mock(session_id)
print(json.dumps(result, indent=2))
