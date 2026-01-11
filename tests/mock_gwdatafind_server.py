"""
Mock gwdatafind server for testing.

This module provides a simple HTTP server that implements the gwdatafind API
for testing purposes, without requiring the full gwdatafind-server package.
"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import threading
import time


class MockGWDataFindHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler that implements a minimal gwdatafind API.
    
    This handler responds to gwdatafind queries with pre-configured
    frame file URLs.
    """
    
    # Class variable to store frame configurations
    frame_configs = {}
    
    def log_message(self, format, *args):
        """Suppress HTTP server logging."""
        pass
    
    def do_GET(self):
        """Handle GET requests for gwdatafind API."""
        parsed_path = urlparse(self.path)
        path_parts = parsed_path.path.strip('/').split('/')
        
        # gwdatafind API format: /api/v1/gwf/{site}/{frametype}/{gpsstart},{gpsend}/{urltype}.json
        if len(path_parts) >= 6 and path_parts[0] == 'api' and path_parts[2] == 'gwf':
            site = path_parts[3]
            frametype = path_parts[4]
            
            # Get frame URLs for this site/frametype combination
            key = (site, frametype)
            if key in self.frame_configs:
                urls = self.frame_configs[key]
                
                # Return JSON response
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(urls).encode('utf-8'))
            else:
                # No frames configured
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps([]).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()


class MockGWDataFindServer:
    """
    A mock gwdatafind server for testing.
    
    This server implements the basic gwdatafind API to return frame file URLs
    without requiring network access to real gwdatafind servers.
    
    Parameters
    ----------
    host : str, optional
        The host to bind to. Default is 'localhost'.
    port : int, optional
        The port to bind to. Default is 8765.
    frame_configs : dict, optional
        Dictionary mapping (site, frametype) tuples to lists of frame URLs.
        
    Examples
    --------
    >>> server = MockGWDataFindServer(frame_configs={
    ...     ('H', 'H1_HOFT_C02'): [
    ...         'file:///data/H-H1_HOFT_C02-1126256640-4096.gwf'
    ...     ]
    ... })
    >>> server.start()
    >>> # Use gwdatafind with host='localhost:8765'
    >>> server.stop()
    """
    
    def __init__(self, host='localhost', port=8765, frame_configs=None):
        self.host = host
        self.port = port
        self.frame_configs = frame_configs or {}
        self.server = None
        self.server_thread = None
        
    def start(self):
        """Start the mock gwdatafind server in a background thread."""
        # Set the frame configurations on the handler class
        MockGWDataFindHandler.frame_configs = self.frame_configs
        
        # Create and start the server
        self.server = HTTPServer((self.host, self.port), MockGWDataFindHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        
        # Give the server a moment to start
        time.sleep(0.1)
        
    def stop(self):
        """Stop the mock gwdatafind server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            if self.server_thread:
                self.server_thread.join(timeout=1)
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
    
    def add_frames(self, site, frametype, urls):
        """
        Add frame URLs for a site/frametype combination.
        
        Parameters
        ----------
        site : str
            Single-character site identifier (e.g., 'H', 'L', 'V')
        frametype : str
            Frame type name (e.g., 'H1_HOFT_C02')
        urls : list of str
            List of frame file URLs
        """
        self.frame_configs[(site, frametype)] = urls
        MockGWDataFindHandler.frame_configs = self.frame_configs
