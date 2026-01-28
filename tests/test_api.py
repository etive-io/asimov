"""
Unit tests for the REST API.
"""

import unittest
import json
import os
from asimov.api.app import create_app
from asimov.testing import AsimovTestCase
from asimov.event import Event

# Set testing flag to avoid RuntimeError when no API keys configured
os.environ['ASIMOV_TESTING'] = '1'


class APIHealthTestCase(unittest.TestCase):
    """Tests for API health check endpoint."""

    def setUp(self):
        """Set up test client."""
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_health_check(self):
        """Test health check endpoint."""
        response = self.client.get('/api/v1/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['version'], 'v1')


class APIEventsTestCase(AsimovTestCase):
    """Tests for Events API endpoints."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()

        # Inject test API keys before creating app
        import asimov.api.auth as auth_module
        auth_module._api_keys_cache = {'test-token-12345': 'test-user'}

        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.auth_headers = {'Authorization': 'Bearer test-token-12345'}

    def tearDown(self):
        """Clean up test environment."""
        # Reset API keys cache
        import asimov.api.auth as auth_module
        auth_module._api_keys_cache = None
        super().tearDown()

    def test_list_events_empty(self):
        """Test listing events when none exist."""
        response = self.client.get('/api/v1/events/')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('events', data)
        self.assertEqual(len(data['events']), 0)

    def test_create_event_no_auth(self):
        """Test creating event without authentication fails."""
        response = self.client.post(
            '/api/v1/events/',
            data=json.dumps({'name': 'GW150914'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertIn('error', data)

    def test_create_event_invalid_auth(self):
        """Test creating event with invalid token fails."""
        response = self.client.post(
            '/api/v1/events/',
            data=json.dumps({'name': 'GW150914'}),
            headers={'Authorization': 'Bearer invalid-token'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)

    def test_create_event_missing_name(self):
        """Test creating event without name fails validation."""
        response = self.client.post(
            '/api/v1/events/',
            data=json.dumps({'meta': {'test': True}}),
            headers=self.auth_headers,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('error', data)

    def test_get_nonexistent_event(self):
        """Test getting non-existent event returns 404."""
        response = self.client.get('/api/v1/events/NonExistent')
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Event not found')

    def test_update_nonexistent_event(self):
        """Test updating non-existent event returns 404."""
        response = self.client.put(
            '/api/v1/events/NonExistent',
            data=json.dumps({'meta': {'test': True}}),
            headers=self.auth_headers,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_nonexistent_event(self):
        """Test deleting non-existent event returns 404."""
        response = self.client.delete(
            '/api/v1/events/NonExistent',
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 404)

    def test_list_productions_nonexistent_event(self):
        """Test listing productions for non-existent event returns 404."""
        response = self.client.get('/api/v1/events/NonExistent/productions')
        self.assertEqual(response.status_code, 404)

    def test_create_event_success(self):
        """Test creating event successfully."""
        response = self.client.post(
            '/api/v1/events/',
            data=json.dumps({
                'name': 'GW150914',
                'repository': 'https://git.ligo.org/test/repo.git',
                'working_directory': '/tmp/test',
                'meta': {'test': True}
            }),
            headers=self.auth_headers,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertIn('event', data)
        self.assertEqual(data['event']['name'], 'GW150914')

    def test_update_event_success(self):
        """Test updating event successfully."""
        # Create event first
        self.client.post(
            '/api/v1/events/',
            data=json.dumps({'name': 'GW150914'}),
            headers=self.auth_headers,
            content_type='application/json'
        )

        # Update event
        response = self.client.put(
            '/api/v1/events/GW150914',
            data=json.dumps({
                'repository': 'https://git.ligo.org/updated/repo.git',
                'meta': {'updated': True}
            }),
            headers=self.auth_headers,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('event', data)
        self.assertEqual(data['event']['name'], 'GW150914')

    def test_delete_event_success(self):
        """Test deleting event successfully."""
        # Create event first
        self.client.post(
            '/api/v1/events/',
            data=json.dumps({'name': 'GW150914'}),
            headers=self.auth_headers,
            content_type='application/json'
        )

        # Delete event
        response = self.client.delete(
            '/api/v1/events/GW150914',
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 204)

        # Verify it's deleted
        response = self.client.get('/api/v1/events/GW150914')
        self.assertEqual(response.status_code, 404)

    def test_get_event_success(self):
        """Test getting event successfully."""
        # Create event first
        self.client.post(
            '/api/v1/events/',
            data=json.dumps({'name': 'GW150914'}),
            headers=self.auth_headers,
            content_type='application/json'
        )

        # Get event
        response = self.client.get('/api/v1/events/GW150914')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('event', data)
        self.assertEqual(data['event']['name'], 'GW150914')

    def test_list_events_with_data(self):
        """Test listing events when events exist."""
        # Create event
        self.client.post(
            '/api/v1/events/',
            data=json.dumps({'name': 'GW150914'}),
            headers=self.auth_headers,
            content_type='application/json'
        )

        # List events
        response = self.client.get('/api/v1/events/')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('events', data)
        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['events'][0]['name'], 'GW150914')


class APIProductionsTestCase(AsimovTestCase):
    """Tests for Productions API endpoints."""

    def setUp(self):
        """Set up test environment with an event."""
        super().setUp()

        # Inject test API keys before creating app
        import asimov.api.auth as auth_module
        auth_module._api_keys_cache = {'test-token-12345': 'test-user'}

        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.auth_headers = {'Authorization': 'Bearer test-token-12345'}

        # Create a test event with a git repo
        self.test_repo_path = os.path.join(self.cwd, "tests/tmp/test-repo")
        os.makedirs(self.test_repo_path, exist_ok=True)
        os.system(f'cd {self.test_repo_path} && git init --quiet 2>/dev/null')

        # Manually add event to ledger to avoid git version issues
        event = Event(
            name='GW150914',
            ledger=self.ledger,
            repository=self.test_repo_path
        )
        self.ledger.add_event(event)

    def tearDown(self):
        """Clean up test environment."""
        # Reset API keys cache
        import asimov.api.auth as auth_module
        auth_module._api_keys_cache = None
        super().tearDown()

    def test_create_production_no_auth(self):
        """Test creating production without authentication fails."""
        response = self.client.post(
            '/api/v1/productions/GW150914',
            data=json.dumps({
                'name': 'Prod_A',
                'pipeline': 'bilby'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)

    def test_create_production_invalid_data(self):
        """Test creating production with invalid data fails."""
        response = self.client.post(
            '/api/v1/productions/GW150914',
            data=json.dumps({'name': 'Prod_A'}),  # Missing required 'pipeline'
            headers=self.auth_headers,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_create_production_nonexistent_event(self):
        """Test creating production for non-existent event fails."""
        response = self.client.post(
            '/api/v1/productions/NonExistent',
            data=json.dumps({
                'name': 'Prod_A',
                'pipeline': 'bilby'
            }),
            headers=self.auth_headers,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_create_production_success(self):
        """Test creating production successfully."""
        response = self.client.post(
            '/api/v1/productions/GW150914',
            data=json.dumps({
                'name': 'Prod_A',
                'pipeline': 'bilby',
                'comment': 'Test production',
                'meta': {'test': True}
            }),
            headers=self.auth_headers,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertIn('production', data)
        self.assertEqual(data['production']['name'], 'Prod_A')
        self.assertEqual(data['production']['pipeline'], 'bilby')

    def test_create_duplicate_production(self):
        """Test creating duplicate production fails."""
        # Create first production
        self.client.post(
            '/api/v1/productions/GW150914',
            data=json.dumps({
                'name': 'Prod_A',
                'pipeline': 'bilby'
            }),
            headers=self.auth_headers,
            content_type='application/json'
        )

        # Try to create duplicate
        response = self.client.post(
            '/api/v1/productions/GW150914',
            data=json.dumps({
                'name': 'Prod_A',
                'pipeline': 'bilby'
            }),
            headers=self.auth_headers,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 409)

    def test_get_production(self):
        """Test getting a production."""
        # Create production first
        self.client.post(
            '/api/v1/productions/GW150914',
            data=json.dumps({
                'name': 'Prod_A',
                'pipeline': 'bilby'
            }),
            headers=self.auth_headers,
            content_type='application/json'
        )

        # Get production
        response = self.client.get('/api/v1/productions/GW150914/Prod_A')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['production']['name'], 'Prod_A')

    def test_get_nonexistent_production(self):
        """Test getting non-existent production returns 404."""
        response = self.client.get('/api/v1/productions/GW150914/NonExistent')
        self.assertEqual(response.status_code, 404)

    def test_update_production(self):
        """Test updating a production."""
        # Create production first
        self.client.post(
            '/api/v1/productions/GW150914',
            data=json.dumps({
                'name': 'Prod_A',
                'pipeline': 'bilby'
            }),
            headers=self.auth_headers,
            content_type='application/json'
        )

        # Update production
        response = self.client.put(
            '/api/v1/productions/GW150914/Prod_A',
            data=json.dumps({
                'status': 'ready',
                'comment': 'Updated comment'
            }),
            headers=self.auth_headers,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['production']['status'], 'ready')

    def test_update_nonexistent_production(self):
        """Test updating non-existent production returns 404."""
        response = self.client.put(
            '/api/v1/productions/GW150914/NonExistent',
            data=json.dumps({'status': 'ready'}),
            headers=self.auth_headers,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_production(self):
        """Test deleting a production."""
        # Create production first
        self.client.post(
            '/api/v1/productions/GW150914',
            data=json.dumps({
                'name': 'Prod_A',
                'pipeline': 'bilby'
            }),
            headers=self.auth_headers,
            content_type='application/json'
        )

        # Delete production
        response = self.client.delete(
            '/api/v1/productions/GW150914/Prod_A',
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 204)

        # Verify deletion
        response = self.client.get('/api/v1/productions/GW150914/Prod_A')
        self.assertEqual(response.status_code, 404)

    def test_delete_nonexistent_production(self):
        """Test deleting non-existent production returns 404."""
        response = self.client.delete(
            '/api/v1/productions/GW150914/NonExistent',
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 404)

    def test_list_productions_empty(self):
        """Test listing productions when none exist."""
        response = self.client.get('/api/v1/events/GW150914/productions')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data['productions']), 0)

    def test_list_productions(self):
        """Test listing productions."""
        # Create multiple productions
        for i in range(3):
            self.client.post(
                '/api/v1/productions/GW150914',
                data=json.dumps({
                    'name': f'Prod_{i}',
                    'pipeline': 'bilby'
                }),
                headers=self.auth_headers,
                content_type='application/json'
            )

        # List productions
        response = self.client.get('/api/v1/events/GW150914/productions')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data['productions']), 3)


class APIAuthenticationTestCase(unittest.TestCase):
    """Tests for API authentication."""

    def setUp(self):
        """Set up test client."""
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_missing_authorization_header(self):
        """Test request without Authorization header is rejected."""
        response = self.client.post(
            '/api/v1/events/',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Authorization header missing')

    def test_invalid_authorization_scheme(self):
        """Test request with invalid scheme is rejected."""
        response = self.client.post(
            '/api/v1/events/',
            data=json.dumps({'name': 'Test'}),
            headers={'Authorization': 'Basic invalid'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Invalid authorization scheme')

    def test_malformed_authorization_header(self):
        """Test request with malformed header is rejected."""
        response = self.client.post(
            '/api/v1/events/',
            data=json.dumps({'name': 'Test'}),
            headers={'Authorization': 'InvalidFormat'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)

    def test_invalid_token(self):
        """Test request with invalid token is rejected."""
        response = self.client.post(
            '/api/v1/events/',
            data=json.dumps({'name': 'Test'}),
            headers={'Authorization': 'Bearer invalid-token'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Invalid token')


class APICORSTestCase(unittest.TestCase):
    """Tests for CORS headers."""

    def setUp(self):
        """Set up test client with CORS enabled."""
        # Need to configure CORS origins for the test
        from asimov import config
        if not config.has_section('api'):
            config.add_section('api')
        config.set('api', 'cors_origins', '*')
        
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_cors_headers_present(self):
        """Test CORS headers are present in responses when configured."""
        response = self.client.get('/api/v1/health')
        self.assertEqual(response.status_code, 200)
        # Flask-CORS should add CORS headers when configured
        self.assertIn('Access-Control-Allow-Origin', response.headers)


class APIErrorHandlingTestCase(unittest.TestCase):
    """Tests for API error handling."""

    def setUp(self):
        """Set up test client."""
        # Set up API keys for authentication
        import asimov.api.auth as auth_module
        auth_module._api_keys_cache = {'test-token': 'test-user'}
        
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def tearDown(self):
        """Clean up after tests."""
        import asimov.api.auth as auth_module
        auth_module._api_keys_cache = None

    def test_404_not_found(self):
        """Test 404 error handling."""
        response = self.client.get('/api/v1/nonexistent')
        self.assertEqual(response.status_code, 404)

    def test_invalid_json(self):
        """Test invalid JSON is handled."""
        response = self.client.post(
            '/api/v1/events/',
            data='invalid json',
            headers={'Authorization': 'Bearer test-token', 'Content-Type': 'application/json'}
        )
        # Should return an error (400 or 500)
        self.assertIn(response.status_code, [400, 500])


if __name__ == '__main__':
    unittest.main()
