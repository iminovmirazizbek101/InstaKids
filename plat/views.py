from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.db import transaction
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
import random
from datetime import timedelta
from .gmail_service import send_gmail_message
from django.utils import timezone
from .models import SocialState, EmailCode
import uuid


def _merge_owned_media(existing, incoming, username, allow_interactions=False):
    incoming_by_id = {item.get('id'): item for item in incoming if item.get('id')}
    merged = []
    for item in existing:
        item_id = item.get('id')
        if item.get('userId') == username:
            updated = incoming_by_id.pop(item_id, None)
            if updated:
                if allow_interactions:
                    likes = set(item.get('likes', [])) - {username}
                    if username in updated.get('likes', []):
                        likes.add(username)
                    updated['likes'] = list(likes)
                    comments = {comment.get('id'): comment for comment in item.get('comments', []) if comment.get('userId') != username}
                    comments.update({comment.get('id'): comment for comment in updated.get('comments', []) if comment.get('userId') == username})
                    updated['comments'] = list(comments.values())
                merged.append(updated)
            continue

        updated = incoming_by_id.pop(item_id, None)
        if allow_interactions and updated:
            old_likes = set(item.get('likes', []))
            new_likes = set(updated.get('likes', []))
            old_likes.discard(username)
            if username in new_likes:
                old_likes.add(username)
            item['likes'] = list(old_likes)
            comments = {comment.get('id'): comment for comment in item.get('comments', [])}
            for comment in updated.get('comments', []):
                if comment.get('userId') == username:
                    comments[comment.get('id')] = comment
            item['comments'] = list(comments.values())
        merged.append(item)

    merged.extend(item for item in incoming_by_id.values() if item.get('userId') == username)
    return merged


def _issue_code(email, purpose):
    email = email.strip().lower()

    recent = EmailCode.objects.filter(email=email, purpose=purpose, created_at__gt=timezone.now() - timedelta(seconds=30)).exists()
    if recent:
        raise ValueError('Yangi kod yuborishdan oldin 30 soniya kuting.')
    EmailCode.objects.filter(email=email, purpose=purpose, used=False).delete()
    code = f'{random.randint(0, 999999):06d}'
    EmailCode.objects.create(email=email, purpose=purpose, code=code)

    digits = ''.join(
        f'<span style="display:inline-block;width:44px;height:56px;line-height:56px;margin:0 4px;'
        f'border-radius:12px;background:#1a1a3a;color:#fff;font-size:28px;font-weight:700;'
        f'text-align:center;border:1px solid #3b3b6b">{d}</span>' for d in code
    )
    html = f'''<div style="background:#0b0b1a;padding:32px 12px;font-family:Arial,Helvetica,sans-serif">
<div style="max-width:440px;margin:0 auto;background:#12122a;border:1px solid #2a2a55;border-radius:20px;overflow:hidden">
<div style="padding:28px 24px;text-align:center;background:linear-gradient(135deg,#6366f1,#a855f7,#ec4899)">
<div style="font-size:32px;font-weight:700;color:#fff;font-family:Georgia,serif;font-style:italic">InstaKids</div>
</div>
<div style="padding:32px 24px;text-align:center;color:#e5e7eb">
<h2 style="margin:0 0 8px;font-size:20px;color:#fff">Parolni tiklash</h2>
<p style="margin:0 0 24px;font-size:14px;color:#9ca3af;line-height:1.5">Parolingizni tiklash uchun quyidagi kodni ilovaga kiriting.</p>
<div style="margin:0 0 24px">{digits}</div>
<p style="margin:0;font-size:13px;color:#9ca3af">Kod <b style="color:#fff">10 daqiqa</b> amal qiladi.</p>
</div>
<div style="padding:16px 24px;text-align:center;font-size:12px;color:#6b7280;border-top:1px solid #2a2a55">Agar bu so‘rovni siz yubormagan bo‘lsangiz, bu xatni e’tiborsiz qoldiring.<br>© InstaKids</div>
</div></div>'''
    send_gmail_message(
        email,
        'InstaKids: parolni tiklash kodi',
        f'InstaKids parolni tiklash kodi: {code}\nKod 10 daqiqa amal qiladi.',
        html_body=html,
    )
    return True


def _check_code(email, purpose, code):
    entry = EmailCode.objects.filter(email=email, purpose=purpose, code=str(code).strip(), used=False, created_at__gt=timezone.now() - timedelta(minutes=10)).order_by('-created_at').first()
    if not entry:
        return False
    entry.used = True
    entry.save(update_fields=['used'])
    return True


@api_view(['POST'])
def send_code(request):
    purpose = 'reset'
    email = request.data.get('email', '').strip().lower()
    username = request.data.get('username', '').strip().lower()
    user = User.objects.filter(username=username).first() or User.objects.filter(email=email).exclude(email='').first() or User.objects.filter(email=username).exclude(email='').first()
    if not user or not user.email:
        return Response({'error': 'Bu akkauntga email biriktirilmagan'}, status=status.HTTP_404_NOT_FOUND)
    email = user.email
    if '@' not in email:
        return Response({'error': 'Email noto‘g‘ri'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        sent = _issue_code(email, purpose)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as exc:
        message = str(exc).strip() or 'Gmail API bilan ulanishda xatolik'
        return Response({'error': f'Gmailga kod yuborilmadi: {message}'}, status=status.HTTP_502_BAD_GATEWAY)
    if not sent:
        return Response({'error': '30 soniya kuting va qayta urinib ko‘ring'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    masked = email[0] + '***' + email[email.index('@'):]
    return Response({'sent': True, 'email': masked})


@api_view(['POST'])
def reset_password(request):
    username = request.data.get('username', '').strip().lower()
    user = User.objects.filter(username=username).first() or User.objects.filter(email=username).exclude(email='').first()
    new_password = request.data.get('new_password', '')
    if not user or not user.email or not _check_code(user.email, 'reset', request.data.get('code', '')):
        return Response({'error': 'Kod noto‘g‘ri yoki muddati o‘tgan'}, status=status.HTTP_400_BAD_REQUEST)
    if len(new_password) < 4:
        return Response({'error': 'Yangi parol kamida 4 ta belgi bo‘lsin'}, status=status.HTTP_400_BAD_REQUEST)
    user.set_password(new_password)
    user.save(update_fields=['password'])
    return Response({'message': 'Parol o‘zgartirildi'})


def home(request):
    return JsonResponse({'message': 'Backend ishlayapti'})


@ensure_csrf_cookie
def csrf_token(request):
    return JsonResponse({'csrfToken': get_token(request)})


@api_view(['POST'])
def register(request):
    username = request.data.get('username', '').strip().lower()
    name = request.data.get('name', '').strip()
    password = request.data.get('password', '')
    email = request.data.get('email', '').strip().lower()

    if len(username) < 3:
        return Response({'error': 'Username kamida 3 ta belgi'}, status=status.HTTP_400_BAD_REQUEST)
    if not name:
        return Response({'error': 'Ismingizni kiriting'}, status=status.HTTP_400_BAD_REQUEST)
    if len(password) < 4:
        return Response({'error': 'Parol kamida 4 ta belgi'}, status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(username=username).exists():
        return Response({'error': 'Bu username band'}, status=status.HTTP_409_CONFLICT)
    if '@' not in email or '.' not in email.split('@')[-1]:
        return Response({'error': 'Email noto‘g‘ri kiritilgan'}, status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(email=email).exists():
        return Response({'error': 'Bu email band'}, status=status.HTTP_409_CONFLICT)
    existing_user = None
    if existing_user:
        if existing_user.check_password(password):
            auth_login(request._request, existing_user)
            return Response({'id': existing_user.id, 'username': existing_user.username, 'name': existing_user.first_name, 'csrfToken': get_token(request._request)})
        return Response({'error': 'Bu username band'}, status=status.HTTP_409_CONFLICT)

    user = User.objects.create_user(username=username, first_name=name[:150], password=password, email=email)
    auth_login(request._request, user)
    return Response({'id': user.id, 'username': user.username, 'name': user.first_name, 'csrfToken': get_token(request._request)}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def login(request):
    username = request.data.get('username', '').strip().lower()
    password = request.data.get('password', '')
    user = authenticate(request, username=username, password=password)
    if not user:
        return Response({'error': 'Username yoki parol noto‘g‘ri'}, status=status.HTTP_401_UNAUTHORIZED)
    auth_login(request._request, user)
    return Response({'id': user.id, 'username': user.username, 'name': user.first_name, 'csrfToken': get_token(request._request)})


@api_view(['GET', 'DELETE'])
def users(request):
    if request.method == 'DELETE':
        if not request.user.is_authenticated or not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Faqat admin foydalanuvchilarni o‘chira oladi'}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data or {}
        username = payload.get('username') or payload.get('user')
        if not username:
            return Response({'error': 'Username ko‘rsatilmagan'}, status=status.HTTP_400_BAD_REQUEST)

        target = User.objects.filter(username=username).exclude(pk=request.user.pk).first()
        if not target:
            return Response({'error': 'Foydalanuvchi topilmadi'}, status=status.HTTP_404_NOT_FOUND)
        if target.is_staff or target.is_superuser:
            return Response({'error': 'Admin foydalanuvchini o‘chirish mumkin emas'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            state = SocialState.objects.filter(pk=1).first()
            if state:
                payload = state.payload or {}
                deleted_story_ids = {
                    item.get('id') for item in payload.get('stories', [])
                    if item.get('userId') == username
                }
                payload['posts'] = [
                    item for item in payload.get('posts', [])
                    if item.get('userId') != username
                ]
                for post in payload['posts']:
                    post['likes'] = [user for user in post.get('likes', []) if user != username]
                    post['comments'] = [
                        comment for comment in post.get('comments', [])
                        if comment.get('userId') != username
                    ]
                payload['reels'] = [
                    item for item in payload.get('reels', [])
                    if item.get('userId') != username
                ]
                for reel in payload['reels']:
                    reel['likes'] = [user for user in reel.get('likes', []) if user != username]
                payload['stories'] = [
                    item for item in payload.get('stories', [])
                    if item.get('userId') != username
                ]
                payload['seenStories'] = [
                    item for item in payload.get('seenStories', [])
                    if item.get('viewerId') != username and item.get('storyId') not in deleted_story_ids
                ]
                payload['follows'] = [
                    item for item in payload.get('follows', [])
                    if item.get('a') != username and item.get('b') != username
                ]
                for key in ('messages', 'deletedMessages'):
                    payload[key] = [
                        item for item in payload.get(key, [])
                        if item.get('from') != username and item.get('to') != username
                    ]
                payload['notifs'] = [
                    item for item in payload.get('notifs', [])
                    if item.get('from') != username and item.get('to') != username
                ]
                payload.get('saved', {}).pop(username, None)
                payload.get('profiles', {}).pop(username, None)
                payload.get('presence', {}).pop(username, None)
                payload['signals'] = [
                    item for item in payload.get('signals', [])
                    if item.get('from') != username and item.get('to') != username
                ]
                payload['callSessions'] = [
                    item for item in payload.get('callSessions', [])
                    if item.get('from') != username and item.get('to') != username
                ]
                state.payload = payload
                state.save(update_fields=['payload', 'updated_at'])
            EmailCode.objects.filter(email=target.email).delete()
            target.delete()
        return Response({'message': 'Foydalanuvchi o‘chirildi', 'username': username})

    state = SocialState.objects.filter(pk=1).first()
    profiles = (state.payload or {}).get('profiles', {}) if state else {}
    accounts = User.objects.filter(is_active=True).exclude(is_staff=True).exclude(is_superuser=True).order_by('username')
    return Response([
        {
            'id': user.id,
            'username': user.username,
            'name': profiles.get(user.username, {}).get('name', user.first_name),
            'bio': profiles.get(user.username, {}).get('bio', ''),
            'avatar': profiles.get(user.username, {}).get('avatar'),
        }
        for user in accounts
    ])


@api_view(['POST'])
def change_password(request):
    username = request.data.get('username', '').strip().lower()
    current_password = request.data.get('current_password', '')
    new_password = request.data.get('new_password', '')
    user = authenticate(request, username=username, password=current_password)
    if not user:
        return Response({'error': 'Joriy parol noto‘g‘ri'}, status=status.HTTP_401_UNAUTHORIZED)
    if len(new_password) < 4:
        return Response({'error': 'Yangi parol kamida 4 ta belgi bo‘lsin'}, status=status.HTTP_400_BAD_REQUEST)
    user.set_password(new_password)
    user.save()
    update_session_auth_hash(request._request, user)
    return Response({'message': 'Parol o‘zgartirildi'})


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def logout(request):
    auth_logout(request._request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'PUT'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def social_state(request):
    state, _ = SocialState.objects.get_or_create(pk=1)
    payload = state.payload or {}
    username = request.user.username
    keys = ('posts', 'reels', 'stories', 'seenStories', 'follows', 'messages', 'deletedMessages', 'notifs', 'saved')

    if request.method == 'GET':
        response_data = {key: payload.get(key, [] if key != 'saved' else {}) for key in keys}
        deleted_ids = {item.get('id') for item in response_data['deletedMessages']}
        response_data['messages'] = [
            item for item in response_data['messages']
            if (item.get('from') == username or item.get('to') == username) and item.get('id') not in deleted_ids
        ]
        response_data['deletedMessages'] = [
            item for item in response_data['deletedMessages']
            if item.get('from') == username or item.get('to') == username
        ]
        response_data['notifs'] = [item for item in response_data['notifs'] if item.get('to') == username]
        owned_story_ids = {item.get('id') for item in response_data['stories'] if item.get('userId') == username}
        response_data['seenStories'] = [
            item for item in response_data['seenStories']
            if item.get('viewerId') == username or item.get('storyId') in owned_story_ids
        ]
        response_data['saved'] = {username: response_data['saved'].get(username, [])}
        return Response(response_data)

    incoming = request.data
    if not isinstance(incoming, dict):
        return Response({'error': 'Noto‘g‘ri ma’lumot formati'}, status=status.HTTP_400_BAD_REQUEST)

    profile = incoming.get('profile')
    if profile is not None:
        if not isinstance(profile, dict):
            return Response({'error': 'Profil formati noto‘g‘ri'}, status=status.HTTP_400_BAD_REQUEST)
        profile_name = str(profile.get('name', request.user.first_name)).strip()[:150]
        profile_bio = str(profile.get('bio', ''))[:5000]
        avatar = profile.get('avatar')
        if avatar is not None and (not isinstance(avatar, str) or len(avatar) > 2_000_000):
            return Response({'error': 'Profil rasmi hajmi juda katta'}, status=status.HTTP_400_BAD_REQUEST)
        profiles = payload.setdefault('profiles', {})
        profiles[username] = {'name': profile_name, 'bio': profile_bio, 'avatar': avatar}
        if request.user.first_name != profile_name:
            request.user.first_name = profile_name
            request.user.save(update_fields=['first_name'])

    for key in ('posts', 'reels', 'stories'):
        old_items = payload.get(key, [])
        new_items = incoming.get(key, [])
        if not isinstance(new_items, list):
            return Response({'error': f'{key} ro‘yxat bo‘lishi kerak'}, status=status.HTTP_400_BAD_REQUEST)
        payload[key] = _merge_owned_media(old_items, new_items, username, allow_interactions=key in ('posts', 'reels', 'stories'))

    new_seen_stories = incoming.get('seenStories', [])
    if not isinstance(new_seen_stories, list):
        return Response({'error': 'seenStories ro‘yxat bo‘lishi kerak'}, status=status.HTTP_400_BAD_REQUEST)
    payload['seenStories'] = [
        item for item in payload.get('seenStories', []) if item.get('viewerId') != username
    ] + [item for item in new_seen_stories if item.get('viewerId') == username]

    new_follows = incoming.get('follows', [])
    if not isinstance(new_follows, list):
        return Response({'error': 'follows ro‘yxat bo‘lishi kerak'}, status=status.HTTP_400_BAD_REQUEST)
    payload['follows'] = [item for item in payload.get('follows', []) if item.get('a') != username] + [
        item for item in new_follows if item.get('a') == username
    ]

    old_messages = payload.get('messages', [])
    new_messages = incoming.get('messages', [])
    if not isinstance(new_messages, list):
        return Response({'error': 'messages ro‘yxat bo‘lishi kerak'}, status=status.HTTP_400_BAD_REQUEST)
    message_map = {item.get('id'): item for item in old_messages}
    for item in new_messages:
        message_id = item.get('id')
        old_item = message_map.get(message_id)
        if old_item:
            if old_item.get('from') == username:
                for key in ('text', 'src', 'mediaType', 'edited', 'storyId', 'storyOwner'):
                    if key in item:
                        old_item[key] = item[key]
            if old_item.get('to') == username:
                old_item['read'] = bool(item.get('read'))
            hidden_for = set(old_item.get('hiddenFor', []))
            hidden_for.discard(username)
            if username in item.get('hiddenFor', []):
                hidden_for.add(username)
            old_item['hiddenFor'] = list(hidden_for)
        elif not old_item and item.get('from') == username and User.objects.filter(username=item.get('to')).exists():
            message_map[message_id] = item
    payload['messages'] = list(message_map.values())

    deleted_messages = {item.get('id'): item for item in payload.get('deletedMessages', [])}
    new_deleted_messages = incoming.get('deletedMessages', [])
    if not isinstance(new_deleted_messages, list):
        return Response({'error': 'deletedMessages ro‘yxat bo‘lishi kerak'}, status=status.HTTP_400_BAD_REQUEST)
    for item in new_deleted_messages:
        message = message_map.get(item.get('id'))
        if message and message.get('from') == username:
            deleted_messages[item.get('id')] = {'id': item.get('id'), 'from': username, 'to': message.get('to')}
    payload['deletedMessages'] = list(deleted_messages.values())

    old_notifs = payload.get('notifs', [])
    new_notifs = incoming.get('notifs', [])
    if not isinstance(new_notifs, list):
        return Response({'error': 'notifs ro‘yxat bo‘lishi kerak'}, status=status.HTTP_400_BAD_REQUEST)
    notif_map = {item.get('id'): item for item in old_notifs if item.get('to') != username}
    for item in old_notifs:
        if item.get('to') == username:
            notif_map[item.get('id')] = item
    for item in new_notifs:
        if item.get('to') == username and item.get('id') in notif_map:
            notif_map[item.get('id')]['read'] = bool(item.get('read'))
        elif item.get('from') == username and User.objects.filter(username=item.get('to')).exists():
            notif_map[item.get('id')] = item
    payload['notifs'] = list(notif_map.values())

    saved = payload.get('saved', {})
    incoming_saved = incoming.get('saved', {})
    if isinstance(incoming_saved, dict):
        saved[username] = incoming_saved.get(username, [])
    payload['saved'] = saved
    state.payload = payload
    state.save(update_fields=['payload', 'updated_at'])
    return Response({'saved': True})


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def set_follow(request):
    target_username = request.data.get('username', '').strip().lower()
    following = request.data.get('following')
    if not target_username or not isinstance(following, bool):
        return Response({'error': 'Follow ma’lumoti noto‘g‘ri'}, status=status.HTTP_400_BAD_REQUEST)
    if target_username == request.user.username:
        return Response({'error': 'O‘zingizni follow qila olmaysiz'}, status=status.HTTP_400_BAD_REQUEST)
    if not User.objects.filter(username=target_username).exists():
        return Response({'error': 'Foydalanuvchi topilmadi'}, status=status.HTTP_404_NOT_FOUND)

    username = request.user.username
    with transaction.atomic():
        state, _ = SocialState.objects.select_for_update().get_or_create(pk=1)
        payload = state.payload or {}
        follows = payload.get('follows', [])
        already_following = any(
            item.get('a') == username and item.get('b') == target_username
            for item in follows
        )
        if following and not already_following:
            follows.append({'a': username, 'b': target_username})
            notifications = payload.setdefault('notifs', [])
            notifications.insert(0, {
                'id': request.data.get('notificationId') or uuid.uuid4().hex,
                'to': target_username,
                'from': username,
                'type': 'follow',
                't': int(timezone.now().timestamp() * 1000),
                'read': False,
            })
        elif not following:
            follows = [
                item for item in follows
                if not (item.get('a') == username and item.get('b') == target_username)
            ]
        payload['follows'] = follows
        state.payload = payload
        state.save(update_fields=['payload', 'updated_at'])
    return Response({'following': following})


@api_view(['GET', 'POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def realtime(request):
    username = request.user.username
    now = timezone.now().timestamp()
    with transaction.atomic():
        state, _ = SocialState.objects.select_for_update().get_or_create(pk=1)
        payload = state.payload or {}
        presence = payload.get('presence', {})
        presence = {
            name: seen_at for name, seen_at in presence.items()
            if isinstance(seen_at, (int, float)) and now - seen_at < 25
            and User.objects.filter(username=name, is_active=True).exists()
        }
        presence[username] = now
        payload['presence'] = presence
        signals = [
            signal for signal in payload.get('signals', [])
            if now - signal.get('created', 0) < 180
        ]
        sessions = [
            call for call in payload.get('callSessions', [])
            if now - call.get('created', 0) < 180
        ]

        if request.method == 'GET':
            state.payload = {**payload, 'signals': signals, 'callSessions': sessions}
            state.save(update_fields=['payload', 'updated_at'])
            return Response({
                'online': [name for name in presence if name != username],
                'signals': [signal for signal in signals if signal.get('to') == username],
            })

        incoming = request.data
        kind = incoming.get('kind')
        if kind == 'ack':
            acknowledged = set(incoming.get('ids', []))
            signals = [
                signal for signal in signals
                if signal.get('to') != username or signal.get('id') not in acknowledged
            ]
        elif kind == 'signal':
            target = str(incoming.get('to', '')).strip().lower()
            call_id = str(incoming.get('callId', '')).strip()
            signal_type = incoming.get('type')
            data = incoming.get('data', {})
            if (signal_type not in {'offer', 'answer', 'candidate', 'decline', 'end'}
                    or not target or target == username or not call_id
                    or len(call_id) > 100 or not isinstance(data, (dict, list))
                    or len(str(data)) > 150000):
                return Response({'error': 'Qo‘ng‘iroq signali noto‘g‘ri'}, status=status.HTTP_400_BAD_REQUEST)
            if not User.objects.filter(username=target, is_active=True).exists():
                return Response({'error': 'Foydalanuvchi topilmadi'}, status=status.HTTP_404_NOT_FOUND)

            call = next((item for item in sessions if item.get('id') == call_id), None)
            if signal_type == 'offer':
                if call:
                    return Response({'error': 'Qo‘ng‘iroq identifikatori band'}, status=status.HTTP_409_CONFLICT)
                sessions.append({'id': call_id, 'from': username, 'to': target, 'created': now})
            elif not call or {username, target} != {call.get('from'), call.get('to')}:
                return Response({'error': 'Qo‘ng‘iroq topilmadi'}, status=status.HTTP_404_NOT_FOUND)

            signals.append({
                'id': uuid.uuid4().hex,
                'callId': call_id,
                'from': username,
                'to': target,
                'type': signal_type,
                'data': data,
                'created': now,
            })
            signals = signals[-300:]
        else:
            return Response({'error': 'So‘rov turi noto‘g‘ri'}, status=status.HTTP_400_BAD_REQUEST)

        state.payload = {**payload, 'signals': signals, 'callSessions': sessions}
        state.save(update_fields=['payload', 'updated_at'])
    return Response({'saved': True})
