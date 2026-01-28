REST API
========

Asimov provides a RESTful API for programmatic access to project management, event handling, and production operations. The API enables integration with web interfaces, external tools, and automation scripts.

Quick Start
-----------

Starting the API Server
~~~~~~~~~~~~~~~~~~~~~~~

Start the API server using the ``serve`` command:

.. code-block:: bash

   asimov serve --host 127.0.0.1 --port 5000

Options:

* ``--host``: Host to bind to (default: 127.0.0.1)
* ``--port``: Port to bind to (default: 5000)
* ``--debug``: Enable debug mode

For production deployment, see :ref:`api-production-deployment`.

Authentication Setup
~~~~~~~~~~~~~~~~~~~~

The API uses bearer token authentication for write operations. There are three ways to configure API keys:

**Option 1: Environment Variable (Recommended for Production)**

Set a single API key:

.. code-block:: bash

   export ASIMOV_API_KEY="your-secret-token:your-username"
   asimov serve

Or point to a keys file:

.. code-block:: bash

   export ASIMOV_API_KEYS_FILE="/path/to/api_keys.yaml"
   asimov serve

**Option 2: Configuration File**

Create an API keys file:

.. code-block:: bash

   mkdir -p .asimov
   cat > .asimov/api_keys.yaml << EOF
   api_keys:
     your-secret-token-here: your-username
   EOF

Configure the API in ``.asimov/asimov.conf``:

.. code-block:: ini

   [api]
   secret_key = your-secret-key-change-in-production
   api_keys_file = .asimov/api_keys.yaml

**Option 3: Both (Environment Variable Takes Priority)**

You can use both methods. The environment variable will be checked first, then the config file.

**Important Security Notes:**

* Always use environment variables in production to avoid committing secrets
* Never commit API keys to version control
* Rotate API keys regularly
* Use strong, randomly generated tokens

Making Requests
~~~~~~~~~~~~~~~

Read-only requests (no authentication required):

.. code-block:: bash

   curl http://127.0.0.1:5000/api/v1/events/

Write requests (authentication required):

.. code-block:: bash

   curl -X POST http://127.0.0.1:5000/api/v1/events/ \
     -H "Authorization: Bearer your-secret-token-here" \
     -H "Content-Type: application/json" \
     -d '{"name":"GW150914","meta":{"test":true}}'

API Endpoints
-------------

Health Check
~~~~~~~~~~~~

.. http:get:: /api/v1/health

   Check API server health.

   **Example request**:

   .. code-block:: bash

      curl http://127.0.0.1:5000/api/v1/health

   **Example response**:

   .. code-block:: json

      {
        "status": "ok",
        "version": "v1"
      }

   :statuscode 200: API is healthy

Events
~~~~~~

List Events
^^^^^^^^^^^

.. http:get:: /api/v1/events/

   List all events in the project.

   **Example request**:

   .. code-block:: bash

      curl http://127.0.0.1:5000/api/v1/events/

   **Example response**:

   .. code-block:: json

      {
        "events": [
          {
            "name": "GW150914",
            "working directory": "/path/to/working/GW150914",
            "productions": [],
            "meta": {}
          }
        ]
      }

   :statuscode 200: Success

Get Event
^^^^^^^^^

.. http:get:: /api/v1/events/(name)

   Get details of a specific event.

   :param name: Event name

   **Example request**:

   .. code-block:: bash

      curl http://127.0.0.1:5000/api/v1/events/GW150914

   **Example response**:

   .. code-block:: json

      {
        "event": {
          "name": "GW150914",
          "working directory": "/path/to/working/GW150914",
          "productions": [],
          "meta": {}
        }
      }

   :statuscode 200: Success
   :statuscode 404: Event not found

Create Event
^^^^^^^^^^^^

.. http:post:: /api/v1/events/

   Create a new event.

   :reqheader Authorization: Bearer token required

   **Request JSON Object**:

   * **name** (*string*) -- Event name (required)
   * **repository** (*string*) -- Git repository URL (optional)
   * **working_directory** (*string*) -- Working directory path (optional)
   * **meta** (*object*) -- Event metadata (optional)

   **Example request**:

   .. code-block:: bash

      curl -X POST http://127.0.0.1:5000/api/v1/events/ \
        -H "Authorization: Bearer your-token" \
        -H "Content-Type: application/json" \
        -d '{
          "name": "GW150914",
          "meta": {
            "gps_time": 1126259462.4,
            "far": 1e-7
          }
        }'

   **Example response**:

   .. code-block:: json

      {
        "event": {
          "name": "GW150914",
          "working directory": "/path/to/working/GW150914",
          "productions": [],
          "meta": {
            "gps_time": 1126259462.4,
            "far": 1e-7
          }
        }
      }

   :statuscode 201: Event created
   :statuscode 400: Validation error
   :statuscode 401: Unauthorized
   :statuscode 409: Event already exists

Update Event
^^^^^^^^^^^^

.. http:put:: /api/v1/events/(name)

   Update an existing event.

   :param name: Event name
   :reqheader Authorization: Bearer token required

   **Request JSON Object**:

   * **repository** (*string*) -- Git repository URL (optional)
   * **working_directory** (*string*) -- Working directory path (optional)
   * **meta** (*object*) -- Event metadata to update (optional)

   **Example request**:

   .. code-block:: bash

      curl -X PUT http://127.0.0.1:5000/api/v1/events/GW150914 \
        -H "Authorization: Bearer your-token" \
        -H "Content-Type: application/json" \
        -d '{"meta": {"updated": true}}'

   :statuscode 200: Event updated
   :statuscode 400: Validation error
   :statuscode 401: Unauthorized
   :statuscode 404: Event not found

Delete Event
^^^^^^^^^^^^

.. http:delete:: /api/v1/events/(name)

   Delete an event.

   :param name: Event name
   :reqheader Authorization: Bearer token required

   **Example request**:

   .. code-block:: bash

      curl -X DELETE http://127.0.0.1:5000/api/v1/events/GW150914 \
        -H "Authorization: Bearer your-token"

   :statuscode 204: Event deleted
   :statuscode 401: Unauthorized
   :statuscode 404: Event not found

List Productions for Event
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. http:get:: /api/v1/events/(name)/productions

   List all productions for a specific event.

   :param name: Event name

   **Example request**:

   .. code-block:: bash

      curl http://127.0.0.1:5000/api/v1/events/GW150914/productions

   **Example response**:

   .. code-block:: json

      {
        "productions": [
          {
            "name": "Prod_A",
            "pipeline": "bilby",
            "status": "ready",
            "comment": "Test production"
          }
        ]
      }

   :statuscode 200: Success
   :statuscode 404: Event not found

Productions
~~~~~~~~~~~

Get Production
^^^^^^^^^^^^^^

.. http:get:: /api/v1/productions/(event_name)/(production_name)

   Get details of a specific production.

   :param event_name: Event name
   :param production_name: Production name

   **Example request**:

   .. code-block:: bash

      curl http://127.0.0.1:5000/api/v1/productions/GW150914/Prod_A

   **Example response**:

   .. code-block:: json

      {
        "production": {
          "name": "Prod_A",
          "pipeline": "bilby",
          "status": "ready",
          "comment": "Test production",
          "dependencies": [],
          "meta": {}
        }
      }

   :statuscode 200: Success
   :statuscode 404: Event or production not found

Create Production
^^^^^^^^^^^^^^^^^

.. http:post:: /api/v1/productions/(event_name)

   Add a production to an event.

   :param event_name: Event name
   :reqheader Authorization: Bearer token required

   **Request JSON Object**:

   * **name** (*string*) -- Production name (required)
   * **pipeline** (*string*) -- Pipeline type: bilby, rift, bayeswave, lalinference (required)
   * **comment** (*string*) -- Production comment (optional)
   * **dependencies** (*array*) -- List of dependency production names (optional)
   * **meta** (*object*) -- Production metadata (optional)

   **Example request**:

   .. code-block:: bash

      curl -X POST http://127.0.0.1:5000/api/v1/productions/GW150914 \
        -H "Authorization: Bearer your-token" \
        -H "Content-Type: application/json" \
        -d '{
          "name": "Prod_A",
          "pipeline": "bilby",
          "comment": "High-spin prior",
          "meta": {
            "sampler": "dynesty"
          }
        }'

   :statuscode 201: Production created
   :statuscode 400: Validation error
   :statuscode 401: Unauthorized
   :statuscode 404: Event not found
   :statuscode 409: Production already exists

Update Production
^^^^^^^^^^^^^^^^^

.. http:put:: /api/v1/productions/(event_name)/(production_name)

   Update a production.

   :param event_name: Event name
   :param production_name: Production name
   :reqheader Authorization: Bearer token required

   **Request JSON Object**:

   * **status** (*string*) -- Production status (optional)
   * **comment** (*string*) -- Production comment (optional)
   * **meta** (*object*) -- Production metadata to update (optional)

   **Example request**:

   .. code-block:: bash

      curl -X PUT http://127.0.0.1:5000/api/v1/productions/GW150914/Prod_A \
        -H "Authorization: Bearer your-token" \
        -H "Content-Type: application/json" \
        -d '{"status": "finished", "comment": "Completed successfully"}'

   :statuscode 200: Production updated
   :statuscode 400: Validation error
   :statuscode 401: Unauthorized
   :statuscode 404: Event or production not found

Delete Production
^^^^^^^^^^^^^^^^^

.. http:delete:: /api/v1/productions/(event_name)/(production_name)

   Delete a production from an event.

   :param event_name: Event name
   :param production_name: Production name
   :reqheader Authorization: Bearer token required

   **Example request**:

   .. code-block:: bash

      curl -X DELETE http://127.0.0.1:5000/api/v1/productions/GW150914/Prod_A \
        -H "Authorization: Bearer your-token"

   :statuscode 204: Production deleted
   :statuscode 401: Unauthorized
   :statuscode 404: Event or production not found

Error Responses
---------------

The API uses standard HTTP status codes and returns error details in JSON format:

.. code-block:: json

   {
     "error": "Event not found"
   }

Validation errors include field-level details:

.. code-block:: json

   {
     "error": "Validation error",
     "details": [
       {
         "loc": ["name"],
         "msg": "field required",
         "type": "value_error.missing"
       }
     ]
   }

Common Status Codes
~~~~~~~~~~~~~~~~~~~

* **200 OK**: Request succeeded
* **201 Created**: Resource created successfully
* **204 No Content**: Resource deleted successfully
* **400 Bad Request**: Invalid request data
* **401 Unauthorized**: Authentication required
* **404 Not Found**: Resource not found
* **409 Conflict**: Resource already exists
* **500 Internal Server Error**: Server error

.. _api-production-deployment:

Production Deployment
---------------------

For production use, deploy the API behind a WSGI server and reverse proxy.

Using Gunicorn
~~~~~~~~~~~~~~

.. code-block:: bash

   # Install gunicorn
   pip install gunicorn

   # Run with 4 workers
   cd /path/to/project
   gunicorn -w 4 -b 0.0.0.0:5000 "asimov.api.app:create_app()"

Nginx Configuration
~~~~~~~~~~~~~~~~~~~

.. code-block:: nginx

   server {
       listen 80;
       server_name api.example.com;

       location /api/ {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       }
   }

Docker Deployment
~~~~~~~~~~~~~~~~~

Create a ``Dockerfile``:

.. code-block:: dockerfile

   FROM python:3.9

   WORKDIR /app
   COPY . /app

   RUN pip install -e .
   RUN pip install gunicorn

   CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "asimov.api.app:create_app()"]

Build and run:

.. code-block:: bash

   docker build -t asimov-api .
   docker run -p 5000:5000 -v /path/to/project:/app/project asimov-api

Security Best Practices
------------------------

1. **Use HTTPS**: Always use SSL/TLS in production
2. **Secure API Keys**:

   * Always use environment variables in production (never hardcode)
   * Use strong, randomly generated tokens (at least 32 characters)
   * Rotate keys regularly
   * Never commit keys to version control
   * Use different keys for different environments (dev/staging/prod)

3. **Rate Limiting**: Implement rate limiting (coming in PR #2)
4. **CORS**: Configure CORS appropriately for your use case
5. **Input Validation**: API validates all inputs with Pydantic
6. **Audit Logging**: Enable audit logging (coming in PR #2)
7. **Fail Securely**: The API will refuse to start in production if no authentication is configured

Example secure production deployment:

.. code-block:: bash

   # Generate a strong API key
   export ASIMOV_API_KEY="$(openssl rand -hex 32):admin-user"

   # Start with gunicorn (production WSGI server)
   gunicorn -w 4 -b 0.0.0.0:5000 "asimov.api.app:create_app()"

Client Libraries
----------------

Python Client Example
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import requests

   API_URL = "http://127.0.0.1:5000/api/v1"
   TOKEN = "your-secret-token"

   headers = {
       "Authorization": f"Bearer {TOKEN}",
       "Content-Type": "application/json"
   }

   # Create event
   response = requests.post(
       f"{API_URL}/events/",
       headers=headers,
       json={"name": "GW150914", "meta": {"test": True}}
   )
   print(response.json())

   # Get event
   response = requests.get(f"{API_URL}/events/GW150914")
   print(response.json())

   # Create production
   response = requests.post(
       f"{API_URL}/productions/GW150914",
       headers=headers,
       json={
           "name": "Prod_A",
           "pipeline": "bilby",
           "comment": "Test production"
       }
   )
   print(response.json())

JavaScript Client Example
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: javascript

   const API_URL = 'http://127.0.0.1:5000/api/v1';
   const TOKEN = 'your-secret-token';

   // Create event
   fetch(`${API_URL}/events/`, {
     method: 'POST',
     headers: {
       'Authorization': `Bearer ${TOKEN}`,
       'Content-Type': 'application/json'
     },
     body: JSON.stringify({
       name: 'GW150914',
       meta: { test: true }
     })
   })
   .then(response => response.json())
   .then(data => console.log(data));

   // Get event
   fetch(`${API_URL}/events/GW150914`)
     .then(response => response.json())
     .then(data => console.log(data));

Roadmap
-------

Future enhancements planned:

* **PR #2**: SciTokens authentication, RBAC, rate limiting
* **PR #3**: Async operations with Celery for job management
* **PR #4**: Real-time updates via Server-Sent Events, OpenAPI docs

See the `API_ROADMAP.md <https://github.com/ligo-asimov/asimov/blob/main/API_ROADMAP.md>`_ for detailed plans.

Python API Reference
--------------------

.. automodule:: asimov.api.app
   :members:
   :undoc-members:

.. automodule:: asimov.api.auth
   :members:
   :undoc-members:

.. automodule:: asimov.api.models
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: asimov.api.utils
   :members:
   :undoc-members:

.. automodule:: asimov.api.errors
   :members:
   :undoc-members:
