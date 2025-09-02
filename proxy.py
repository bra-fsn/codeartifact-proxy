from cachetools import cached, TTLCache
from flask import Flask, request, Response, stream_with_context, jsonify, redirect
from typing import Dict, Optional
import boto3
import logging
import requests
import threading
import click
import os

TOKEN_VALIDITY = 43200
CHUNK_SIZE = 64 * 1024
PYPI_BASE = "https://pypi.org/simple"
# PASS these client headers to pypi/code artifact
PIP_PASS_HEADERS = {"user-agent", "cache-control"}

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# Error tracking
TOKEN_ERRORS: Dict[str, Exception] = {}
ERROR_LOCK = threading.Lock()


def get_cache_key(account_id: str, region: str, domain: str, repo: str) -> str:
    """Generate a cache key for the given parameters."""
    return f"{str(account_id)}-{region}-{domain}-{repo}"


@cached(TTLCache(maxsize=100, ttl=TOKEN_VALIDITY))
def get_token(account_id: str, region: str, domain: str, repo: str) -> Optional[str]:
    """
    Get a token for the specified CodeArtifact repository.
    Uses TTLCache decorator for automatic memoization and expiration.
    """
    cache_key = get_cache_key(account_id, region, domain, repo)
    
    # Clear any previous errors for this key
    with ERROR_LOCK:
        if cache_key in TOKEN_ERRORS:
            del TOKEN_ERRORS[cache_key]
    
    # Fetch new token
    try:
        app.logger.info(f"Fetching token for {cache_key}")
        client = boto3.client("codeartifact", region_name=region)
        token = client.get_authorization_token(
            domain=domain,
            domainOwner=str(account_id),
            durationSeconds=TOKEN_VALIDITY,
        )["authorizationToken"]
        
        app.logger.info(f"Got a new token for {cache_key}")
        return token
        
    except Exception as e:
        app.logger.exception(f"Couldn't get token for {cache_key}. Error: {str(e)}")
        with ERROR_LOCK:
            TOKEN_ERRORS[cache_key] = e
        return None


def generate_url(account_id: str, region: str, domain: str, repo: str, path: str) -> str:
    """Generate a CodeArtifact URL with authentication token."""
    if path.startswith("/"):
        path = path[1:]
    
    token = get_token(account_id, region, domain, repo)
    if not token:
        raise Exception(f"Failed to get token for {get_cache_key(account_id, region, domain, repo)}")
    
    return f"https://aws:{token}@{domain}-{account_id}.d.codeartifact.{region}.amazonaws.com/pypi/{repo}/simple/{path}"


def proxy_get(url):
    # Stream the GET request to the remote server
    headers = dict(request.headers)
    if "Host" in headers:
        del headers["Host"]
    upstream_response = requests.get(url, stream=True, headers=headers)

    def generate():
        for chunk in upstream_response.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                yield chunk

    return Response(
        stream_with_context(generate()),
        content_type=upstream_response.headers.get("Content-Type"),
        status=upstream_response.status_code
    )


def proxy_post(url):
    # Stream the POST request to the remote server
    headers = dict(request.headers)
    if "Host" in headers:
        del headers["Host"]
    upstream_response = requests.post(
        url,
        data=request.stream,
        headers=request.headers,
        stream=True
    )

    def generate():
        for chunk in upstream_response.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                yield chunk

    return Response(
        stream_with_context(generate()),
        content_type=upstream_response.headers.get("Content-Type"),
        status=upstream_response.status_code
    )


@app.route("/healthz")
def healthz():
    """Health check endpoint that reports token errors."""
    with ERROR_LOCK:
        if TOKEN_ERRORS:
            errors = {}
            for cache_key, error in TOKEN_ERRORS.items():
                errors[cache_key] = {
                    "error": str(error),
                    "type": type(error).__name__
                }
            
            response = jsonify({
                "errors": errors,
                "status": 500
            })
            response.status_code = 500
            return response
    
    # Return cache status safely
    try:
        cache_size = len(get_token.cache) if hasattr(get_token, 'cache') else 0
        cache_info = get_token.cache_info() if hasattr(get_token, 'cache_info') else {}
    except Exception:
        cache_size = 0
        cache_info = {}
    
    return jsonify({
        "status": "healthy",
        "cache_info": {
            "cache_size": cache_size,
            "cache_info": cache_info
        }
    })


@app.route("/<int:account_id>/<string:region>/<string:domain>/<string:repo>/<path:path>", methods=["GET", "POST"])
def proxy(account_id, region, domain, repo, path):
    """Proxy requests to CodeArtifact repositories."""
    try:
        if request.method == "GET":
            if path.endswith("/"):
                # if this is a request to the package page and it exists in pypi, redirect pip to it, so
                # it will use pypi instead of Code Artifact, which is often an order of magnitude slower
                pypi_url = f"{PYPI_BASE}/{path}"
                pip_headers = {k: v for k, v in request.headers.items() if k.lower() in PIP_PASS_HEADERS}
                try:
                    res = requests.head(pypi_url, headers=pip_headers)
                    if 200 <= res.status_code < 300:
                        return redirect(pypi_url)
                except Exception:
                    logging.exception("Failed to get url %s", pypi_url)
            # as pip follows redirects, give a 302, so the traffic won't flow through us
            return redirect(generate_url(account_id, region, domain, repo, path))
        elif request.method == "POST":
            return proxy_post(generate_url(account_id, region, domain, repo, path))
    except Exception as e:
        app.logger.exception(f"Error processing request for {account_id}/{region}/{domain}/{repo}/{path}")
        return jsonify({"error": str(e)}), 500


@click.command()
@click.option('--host', '--listen-address', 
              default=lambda: os.environ.get('LISTEN_ADDRESS', '0.0.0.0'),
              help='Address to listen on (default: 0.0.0.0, env: LISTEN_ADDRESS)')
@click.option('--port', 
              default=lambda: int(os.environ.get('PORT', '80')),
              help='Port to listen on (default: 80, env: PORT)')
@click.option('--debug', 
              is_flag=True,
              default=lambda: os.environ.get('DEBUG', 'false').lower() == 'true',
              help='Enable debug mode (default: false, env: DEBUG)')
def main(host, port, debug):
    """CodeArtifact PyPI Proxy Service"""
    if debug:
        app.logger.setLevel(logging.DEBUG)
        app.run(host=host, port=port, debug=True, threaded=True)
    else:
        app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
