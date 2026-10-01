from django.conf import settings
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from unittest.mock import patch
from .models import SocialState


class RegistrationTests(APITestCase):
	@patch('plat.views._issue_code', side_effect=RuntimeError('private credential detail'))
	def test_password_reset_does_not_expose_email_service_errors(self, _issue_code):
		User.objects.create_user(username='reset_user', email='reset@example.com', password='secret123')
		response = self.client.post('/plat/send-code/', {'username': 'reset_user'}, format='json')

		self.assertEqual(response.status_code, 502)
		self.assertNotIn('private credential detail', str(response.data))

	def test_vite_dev_server_is_trusted_for_csrf(self):
		self.assertIn('http://localhost:5173', settings.CSRF_TRUSTED_ORIGINS)
		self.assertIn('http://127.0.0.1:5173', settings.CSRF_TRUSTED_ORIGINS)

	def test_csrf_endpoint_sets_token_cookie(self):
		response = self.client.get('/plat/csrf/')

		self.assertEqual(response.status_code, 200)
		self.assertIn('csrftoken', response.cookies)

	def test_register_creates_user_with_hashed_password(self):
		response = self.client.post('/plat/register/', {
			'username': 'new_user',
			'name': 'New User',
			'email': 'new_user@example.com',
			'password': 'secret123',
		}, format='json')

		self.assertEqual(response.status_code, 201)
		user = User.objects.get(username='new_user')
		self.assertTrue(user.check_password('secret123'))

	def test_register_rejects_duplicate_username(self):
		User.objects.create_user(username='taken', password='secret123')
		response = self.client.post('/plat/register/', {
			'username': 'taken',
			'name': 'New User',
			'password': 'different123',
		}, format='json')

		self.assertEqual(response.status_code, 409)

	def test_register_retry_recovers_existing_account(self):
		User.objects.create_user(username='existing', password='secret123')
		response = self.client.post('/plat/register/', {
			'username': 'existing',
			'name': 'Existing User',
			'password': 'secret123',
		}, format='json')

		self.assertEqual(response.status_code, 200)

	def test_login_accepts_valid_credentials(self):
		User.objects.create_user(username='login_user', password='secret123')
		response = self.client.post('/plat/login/', {
			'username': 'login_user',
			'password': 'secret123',
		}, format='json')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['username'], 'login_user')

	def test_login_rejects_invalid_credentials(self):
		User.objects.create_user(username='login_user', password='secret123')
		response = self.client.post('/plat/login/', {
			'username': 'login_user',
			'password': 'wrong-pass',
		}, format='json')

		self.assertEqual(response.status_code, 401)

	def test_users_returns_registered_accounts(self):
		user = User.objects.create_user(username='visible_user', first_name='Visible')
		self.client.force_login(user)
		response = self.client.get('/plat/users/')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data[0]['username'], 'visible_user')

	def test_users_does_not_expose_accounts_to_anonymous_visitors(self):
		User.objects.create_user(username='private_user', first_name='Private', password='secret123')
		response = self.client.get('/plat/users/')

		self.assertEqual(response.status_code, 403)

	def test_profile_avatar_is_shared_and_only_owner_can_update_it(self):
		owner = User.objects.create_user(username='profile_owner', first_name='Owner', password='password123')
		viewer = User.objects.create_user(username='profile_viewer', password='password123')
		self.client.force_login(owner)
		response = self.client.put('/plat/social/', {
			'profile': {'name': 'Updated Owner', 'bio': 'Hello', 'avatar': 'data:image/jpeg;base64,abc'},
			'profiles': {'profile_viewer': {'avatar': 'forbidden'}},
		}, format='json')
		self.assertEqual(response.status_code, 200)

		self.client.force_login(viewer)
		response = self.client.get('/plat/users/')
		owner_profile = next(user for user in response.data if user['username'] == 'profile_owner')
		viewer_profile = next(user for user in response.data if user['username'] == 'profile_viewer')
		self.assertEqual(owner_profile['name'], 'Updated Owner')
		self.assertEqual(owner_profile['bio'], 'Hello')
		self.assertEqual(owner_profile['avatar'], 'data:image/jpeg;base64,abc')
		self.assertIsNone(viewer_profile['avatar'])

	def test_profile_update_endpoint_shares_avatar_with_other_accounts(self):
		owner = User.objects.create_user(username='avatar_owner', password='password123')
		viewer = User.objects.create_user(username='avatar_viewer', password='password123')
		self.client.force_login(owner)
		response = self.client.put('/plat/profile/', {
			'name': 'Avatar Owner',
			'bio': 'Hello',
			'avatar': 'data:image/jpeg;base64,shared-avatar',
		}, format='json')
		self.assertEqual(response.status_code, 200)

		self.client.force_login(viewer)
		accounts = self.client.get('/plat/users/').data
		owner_profile = next(account for account in accounts if account['username'] == 'avatar_owner')
		self.assertEqual(owner_profile['avatar'], 'data:image/jpeg;base64,shared-avatar')

	def test_admin_users_are_hidden_from_public_user_list(self):
		User.objects.create_user(username='visible_user', first_name='Visible')
		admin = User.objects.create_superuser(username='admin', email='admin@example.com', password='admin123')
		self.client.force_login(admin)
		response = self.client.get('/plat/users/')

		self.assertEqual(response.status_code, 200)
		usernames = [user['username'] for user in response.data]
		self.assertNotIn('admin', usernames)
		self.assertIn('visible_user', usernames)

	def test_admin_can_delete_user_and_login_fails_afterward(self):
		admin = User.objects.create_superuser(username='admin', email='admin@example.com', password='admin123')
		User.objects.create_user(username='ghost_user', password='secret123')
		User.objects.create_user(username='keeper', password='secret123')
		state = SocialState.objects.create(payload={
			'posts': [{'id': 'ghost-post', 'userId': 'ghost_user', 'likes': [], 'comments': []}],
			'reels': [
				{'id': 'ghost-reel', 'userId': 'ghost_user', 'likes': ['ghost_user'], 'comments': []},
				{'id': 'keeper-reel', 'userId': 'keeper', 'likes': ['ghost_user'], 'comments': [
					{'id': 'ghost-comment', 'userId': 'ghost_user'},
					{'id': 'keeper-comment', 'userId': 'keeper'},
				]},
			],
			'stories': [{'id': 'ghost-story', 'userId': 'ghost_user'}],
			'seenStories': [{'storyId': 'ghost-story', 'viewerId': 'other'}],
			'follows': [{'a': 'other', 'b': 'ghost_user'}],
			'messages': [{'id': 'ghost-message', 'from': 'ghost_user', 'to': 'other'}],
			'deletedMessages': [],
			'notifs': [{'id': 'ghost-notif', 'from': 'other', 'to': 'ghost_user'}],
			'saved': {
				'ghost_user': ['ghost-post', 'reel:ghost-reel'],
				'keeper': ['ghost-post', 'reel:ghost-reel', 'reel:keeper-reel'],
			},
			'presence': {'ghost_user': 123},
			'signals': [{'id': 'signal-1', 'from': 'ghost_user', 'to': 'other'}],
			'callSessions': [{'id': 'call-1', 'from': 'other', 'to': 'ghost_user'}],
		})
		self.client.force_login(admin)
		response = self.client.delete('/plat/users/', {'username': 'ghost_user'}, format='json')

		self.assertEqual(response.status_code, 200)
		self.assertFalse(User.objects.filter(username='ghost_user').exists())
		state.refresh_from_db()
		self.assertFalse(state.payload['posts'])
		self.assertEqual([reel['id'] for reel in state.payload['reels']], ['keeper-reel'])
		self.assertEqual(state.payload['reels'][0]['likes'], [])
		self.assertEqual(state.payload['reels'][0]['comments'], [{'id': 'keeper-comment', 'userId': 'keeper'}])
		self.assertFalse(state.payload['stories'])
		self.assertFalse(state.payload['seenStories'])
		self.assertFalse(state.payload['follows'])
		self.assertFalse(state.payload['messages'])
		self.assertFalse(state.payload['notifs'])
		self.assertNotIn('ghost_user', state.payload['saved'])
		self.assertEqual(state.payload['saved']['keeper'], ['reel:keeper-reel'])
		self.assertNotIn('ghost_user', state.payload['presence'])
		self.assertFalse(state.payload['signals'])
		self.assertFalse(state.payload['callSessions'])

		login_response = self.client.post('/plat/login/', {
			'username': 'ghost_user',
			'password': 'secret123',
		}, format='json')
		self.assertEqual(login_response.status_code, 401)

	def test_change_password_updates_password_after_verification(self):
		user = User.objects.create_user(username='password_user', password='oldpass')
		response = self.client.post('/plat/change-password/', {
			'username': 'password_user',
			'current_password': 'oldpass',
			'new_password': 'newpass',
		}, format='json')

		self.assertEqual(response.status_code, 200)
		user.refresh_from_db()
		self.assertTrue(user.check_password('newpass'))

	def test_change_password_rejects_wrong_current_password(self):
		User.objects.create_user(username='password_user', password='oldpass')
		response = self.client.post('/plat/change-password/', {
			'username': 'password_user',
			'current_password': 'wrongpass',
			'new_password': 'newpass',
		}, format='json')

		self.assertEqual(response.status_code, 401)

	def test_social_state_requires_login(self):
		response = self.client.get('/plat/social/')

		self.assertEqual(response.status_code, 403)

	def test_message_sync_is_authenticated_and_scoped_to_current_user(self):
		owner = User.objects.create_user(username='message_owner', password='password123')
		SocialState.objects.create(payload={'messages': [
			{'id': 'visible', 'from': 'message_owner', 'to': 'friend'},
			{'id': 'private', 'from': 'stranger', 'to': 'someone_else'},
		]})
		self.assertEqual(self.client.get('/plat/messages/').status_code, 403)

		self.client.force_login(owner)
		response = self.client.get('/plat/messages/')

		self.assertEqual(response.status_code, 200)
		self.assertEqual([item['id'] for item in response.data['messages']], ['visible'])

	def test_reel_message_is_saved_immediately_for_recipient(self):
		sender = User.objects.create_user(username='reel_sender', password='password123')
		User.objects.create_user(username='reel_receiver', password='password123')
		self.client.force_login(sender)
		response = self.client.post('/plat/messages/', {
			'id': 'shared-reel-message',
			'to': 'reel_receiver',
			'text': '🎬 Reels: Yangi video',
			'reelId': 'saved-reel-1',
			'src': 'data:video/mp4;base64,AAAA',
			'mediaType': 'video',
		}, format='json')
		self.assertEqual(response.status_code, 201)

		self.client.force_login(User.objects.get(username='reel_receiver'))
		messages = self.client.get('/plat/messages/').data['messages']
		self.assertEqual(len(messages), 1)
		self.assertEqual(messages[0]['reelId'], 'saved-reel-1')
		self.assertEqual(messages[0]['mediaType'], 'video')
		self.assertEqual(messages[0]['src'], 'data:video/mp4;base64,AAAA')

	def test_message_reactions_sync_without_overwriting_other_users(self):
		sender = User.objects.create_user(username='reaction_sender', password='password123')
		reactor = User.objects.create_user(username='reaction_user', password='password123')
		SocialState.objects.create(payload={'messages': [{
			'id': 'shared-message', 'from': 'reaction_sender', 'to': 'reaction_user', 'text': 'Hello', 'likes': [],
		}]})
		self.client.force_login(reactor)
		response = self.client.put('/plat/social/', {
			'messages': [{
				'id': 'shared-message', 'from': 'reaction_sender', 'to': 'reaction_user',
				'text': 'Hello', 'likes': ['reaction_user'],
			}],
		}, format='json')
		self.assertEqual(response.status_code, 200)

		self.client.force_login(sender)
		messages = self.client.get('/plat/messages/').data['messages']
		self.assertEqual(messages[0]['likes'], ['reaction_user'])

	def test_follow_changes_are_saved_immediately_and_can_be_undone(self):
		owner = User.objects.create_user(username='follow_owner', password='password123')
		target = User.objects.create_user(username='follow_target', password='password123')
		self.assertEqual(self.client.get('/plat/notifications/').status_code, 403)
		self.client.force_login(owner)

		response = self.client.post('/plat/follow/', {
			'username': 'follow_target', 'following': True, 'notificationId': 'follow-event-1',
		}, format='json')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.client.get('/plat/social/').data['follows'], [
			{'a': 'follow_owner', 'b': 'follow_target'},
		])
		self.assertEqual(self.client.get('/plat/notifications/').status_code, 200)
		self.client.force_login(target)
		notifications = self.client.get('/plat/notifications/').data['notifications']
		self.assertEqual(len(notifications), 1)
		self.assertEqual(notifications[0]['type'], 'follow')
		self.assertEqual(notifications[0]['from'], 'follow_owner')

		self.client.force_login(owner)
		response = self.client.post('/plat/follow/', {
			'username': 'follow_target', 'following': False,
		}, format='json')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.client.get('/plat/social/').data['follows'], [])

	def test_realtime_presence_and_call_signals_are_private(self):
		caller = User.objects.create_user(username='caller', password='password123')
		receiver = User.objects.create_user(username='receiver', password='password123')
		other = User.objects.create_user(username='other', password='password123')

		self.client.force_login(caller)
		response = self.client.get('/plat/realtime/')
		self.assertEqual(response.status_code, 200)
		response = self.client.post('/plat/realtime/', {
			'kind': 'signal', 'to': 'receiver', 'callId': 'call-1',
			'type': 'offer', 'data': {'sdp': 'offer-sdp', 'mode': 'video'},
		}, format='json')
		self.assertEqual(response.status_code, 200)

		self.client.force_login(receiver)
		response = self.client.get('/plat/realtime/')
		self.assertEqual(response.status_code, 200)
		self.assertIn('caller', response.data['online'])
		self.assertEqual(response.data['signals'][0]['data']['mode'], 'video')
		signal_id = response.data['signals'][0]['id']
		self.client.post('/plat/realtime/', {'kind': 'ack', 'ids': [signal_id]}, format='json')
		self.assertFalse(self.client.get('/plat/realtime/').data['signals'])

		self.client.force_login(other)
		self.assertFalse(self.client.get('/plat/realtime/').data['signals'])

	def test_social_state_saves_and_returns_owner_data_without_other_private_messages(self):
		owner = User.objects.create_user(username='owner', password='password123')
		other = User.objects.create_user(username='other', password='password123')
		self.client.force_login(owner)
		response = self.client.put('/plat/social/', {
			'posts': [{'id': 'p1', 'userId': 'owner'}],
			'messages': [
				{'id': 'm1', 'from': 'owner', 'to': 'other'},
				{'id': 'm2', 'from': 'other', 'to': 'elsewhere'},
			],
		}, format='json')

		self.assertEqual(response.status_code, 200)
		state = SocialState.objects.get(pk=1)
		self.assertEqual(state.payload['posts'], [{'id': 'p1', 'userId': 'owner'}])
		response = self.client.get('/plat/social/')
		self.assertEqual([message['id'] for message in response.data['messages']], ['m1'])

	def test_story_likes_persist_and_are_visible_to_story_owner(self):
		owner = User.objects.create_user(username='story_owner', password='password123')
		liker = User.objects.create_user(username='story_liker', password='password123')
		SocialState.objects.create(payload={'stories': [
			{'id': 'persistent-story', 'userId': 'story_owner', 'likes': []},
		]})
		self.client.force_login(liker)
		response = self.client.put('/plat/social/', {
			'stories': [{'id': 'persistent-story', 'userId': 'story_owner', 'likes': ['story_liker']}],
		}, format='json')
		self.assertEqual(response.status_code, 200)

		self.client.force_login(owner)
		stories = self.client.get('/plat/social/').data['stories']
		self.assertEqual(stories[0]['likes'], ['story_liker'])

	def test_comment_like_persists_and_only_author_can_delete(self):
		author = User.objects.create_user(username='comment_author', password='password123')
		liker = User.objects.create_user(username='comment_liker', password='password123')
		SocialState.objects.create(payload={'posts': [{
			'id': 'comment-post', 'userId': 'comment_author', 'likes': [],
			'comments': [{'id': 'comment-1', 'userId': 'comment_author', 'text': 'Hello', 'likes': []}],
		}]})
		self.client.force_login(liker)
		response = self.client.post('/plat/comments/action/', {
			'mediaType': 'post', 'mediaId': 'comment-post', 'commentId': 'comment-1', 'action': 'like',
		}, format='json')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['likes'], ['comment_liker'])

		response = self.client.post('/plat/comments/action/', {
			'mediaType': 'post', 'mediaId': 'comment-post', 'commentId': 'comment-1', 'action': 'delete',
		}, format='json')
		self.assertEqual(response.status_code, 403)

		self.client.force_login(author)
		response = self.client.post('/plat/comments/action/', {
			'mediaType': 'post', 'mediaId': 'comment-post', 'commentId': 'comment-1', 'action': 'delete',
		}, format='json')
		self.assertEqual(response.status_code, 200)
		state = SocialState.objects.get(pk=1)
		self.assertFalse(state.payload['posts'][0]['comments'])

	def test_social_state_keeps_other_posts_and_merges_only_current_users_interactions(self):
		owner = User.objects.create_user(username='owner', password='password123')
		self.client.force_login(owner)
		SocialState.objects.create(payload={'posts': [
			{'id': 'other-post', 'userId': 'other', 'likes': [], 'comments': []},
			{'id': 'owner-post', 'userId': 'owner', 'likes': [], 'comments': []},
		]})
		response = self.client.put('/plat/social/', {
			'posts': [{
				'id': 'other-post', 'userId': 'other', 'likes': ['owner'],
				'comments': [{'id': 'comment-1', 'userId': 'owner', 'text': 'Nice'}],
			}],
		}, format='json')

		self.assertEqual(response.status_code, 200)
		posts = {post['id']: post for post in SocialState.objects.get(pk=1).payload['posts']}
		self.assertNotIn('owner-post', posts)
		self.assertEqual(posts['other-post']['likes'], ['owner'])
		self.assertEqual(posts['other-post']['comments'][0]['userId'], 'owner')

	def test_social_state_returns_seen_stories_only_for_current_viewer(self):
		viewer = User.objects.create_user(username='viewer', password='password123')
		self.client.force_login(viewer)
		SocialState.objects.create(payload={'seenStories': [
			{'viewerId': 'viewer', 'storyId': 'story-1'},
			{'viewerId': 'another', 'storyId': 'story-2'},
		]})

		response = self.client.get('/plat/social/')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['seenStories'], [{'viewerId': 'viewer', 'storyId': 'story-1'}])

	def test_story_like_and_view_are_visible_to_owner_and_survive_owner_sync(self):
		owner = User.objects.create_user(username='story_owner', password='password123')
		viewer = User.objects.create_user(username='story_viewer', password='password123')
		SocialState.objects.create(payload={'stories': [
			{'id': 'story-1', 'userId': 'story_owner', 'likes': [], 'comments': []},
		], 'seenStories': []})

		self.client.force_login(viewer)
		response = self.client.put('/plat/social/', {
			'stories': [{'id': 'story-1', 'userId': 'story_owner', 'likes': ['story_viewer'], 'comments': []}],
			'seenStories': [{'viewerId': 'story_viewer', 'storyId': 'story-1'}],
		}, format='json')
		self.assertEqual(response.status_code, 200)

		self.client.force_login(owner)
		response = self.client.put('/plat/social/', {
			'stories': [{'id': 'story-1', 'userId': 'story_owner', 'likes': [], 'comments': []}],
			'seenStories': [],
		}, format='json')
		self.assertEqual(response.status_code, 200)

		response = self.client.get('/plat/social/')
		self.assertEqual(response.data['stories'][0]['likes'], ['story_viewer'])
		self.assertEqual(response.data['seenStories'], [{'viewerId': 'story_viewer', 'storyId': 'story-1'}])

	def test_message_edit_and_delete_permissions(self):
		sender = User.objects.create_user(username='sender', password='password123')
		receiver = User.objects.create_user(username='receiver', password='password123')
		SocialState.objects.create(payload={'messages': [
			{'id': 'message-1', 'from': 'sender', 'to': 'receiver', 'text': 'old', 'hiddenFor': []},
		], 'deletedMessages': []})

		self.client.force_login(sender)
		response = self.client.put('/plat/social/', {
			'messages': [{'id': 'message-1', 'from': 'sender', 'to': 'receiver', 'text': 'edited', 'edited': True}],
		}, format='json')
		self.assertEqual(response.status_code, 200)

		self.client.force_login(receiver)
		response = self.client.get('/plat/social/')
		self.assertEqual(response.data['messages'][0]['text'], 'edited')
		response = self.client.put('/plat/social/', {
			'messages': [{'id': 'message-1', 'from': 'sender', 'to': 'receiver', 'text': 'edited', 'edited': True, 'hiddenFor': ['receiver']}],
		}, format='json')
		self.assertEqual(response.status_code, 200)

		response = self.client.put('/plat/social/', {
			'deletedMessages': [{'id': 'message-1', 'from': 'sender', 'to': 'receiver'}],
		}, format='json')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['saved'], True)
		self.assertFalse(SocialState.objects.get(pk=1).payload.get('deletedMessages'))

		self.client.force_login(sender)
		self.client.put('/plat/social/', {
			'deletedMessages': [{'id': 'message-1', 'from': 'sender', 'to': 'receiver'}],
		}, format='json')
		self.client.force_login(receiver)
		response = self.client.get('/plat/social/')
		self.assertEqual(response.data['messages'], [])
