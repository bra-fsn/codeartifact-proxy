# CodeArtifact PyPI Proxy Service

A Flask-based proxy service that provides seamless access to AWS CodeArtifact PyPI repositories with intelligent caching and fallback to public PyPI.

## Overview

This service acts as a smart proxy between pip clients and AWS CodeArtifact repositories. It automatically handles authentication tokens, caches them efficiently, and provides intelligent fallback to public PyPI when packages are available there (for better performance).

## Key Features

- **Automatic Token Management**: Handles AWS CodeArtifact authentication tokens with TTL-based caching
- **Intelligent Fallback**: Redirects to public PyPI when packages are available there for faster downloads
- **Streaming Proxy**: Efficiently streams large package downloads without buffering
- **Health Monitoring**: Provides health check endpoint with error reporting
- **Error Tracking**: Tracks and reports authentication errors for debugging

## How It Works

1. **Token Caching**: Uses TTL cache (12 hours) to store and reuse CodeArtifact authentication tokens
2. **Smart Routing**: For GET requests to package pages, checks if the package exists on public PyPI and redirects there if available
3. **Streaming**: Proxies both GET and POST requests with streaming to handle large package uploads/downloads efficiently
4. **Error Handling**: Tracks authentication errors and reports them via the health endpoint

## API Endpoints

### Proxy Endpoint
```
GET/POST /{account_id}/{region}/{domain}/{repo}/{path}
```

**Parameters:**
- `account_id`: AWS account ID that owns the CodeArtifact domain
- `region`: AWS region where the CodeArtifact repository is located
- `domain`: CodeArtifact domain name
- `repo`: CodeArtifact repository name
- `path`: Package path (e.g., `numpy/`, `requests/`, etc.)

**Example:**
```
GET /123456789012/us-east-1/my-domain/my-repo/numpy/
```

### Health Check
```
GET /healthz
```

Returns service health status and cache information. Returns HTTP 500 if there are authentication errors.

## Usage

### Running Locally

```bash
# Install dependencies
pip install boto3 requests flask cachetools click

# Run the service with default settings (0.0.0.0:80)
python proxy.py

# Run with custom host and port
python proxy.py --host 127.0.0.1 --port 8080

# Run with environment variables
LISTEN_ADDRESS=127.0.0.1 PORT=8080 python proxy.py

# Run in debug mode
python proxy.py --debug
```

**Command-line Options:**
- `--host`, `--listen-address`: Address to listen on (default: 0.0.0.0, env: `LISTEN_ADDRESS`)
- `--port`: Port to listen on (default: 80, env: `PORT`)
- `--debug`: Enable debug mode (default: false, env: `DEBUG`)

The service will start on the specified address and port.

### Using with pip

Configure pip to use the proxy service:

```bash
# For a specific package index
pip install --index-url http://your-proxy-host/123456789012/us-east-1/my-domain/my-repo/simple/ numpy

# Using multiple extra-index-urls for different repositories
pip install \
  --extra-index-url http://your-proxy-host/123456789012/us-west-2/internal-packages/simple/ \
  --extra-index-url http://your-proxy-host/987654321098/us-west-2/company-packages/simple/ \
  your-package-name

# Or configure in pip.conf
[global]
index-url = http://your-proxy-host/123456789012/us-east-1/my-domain/my-repo/simple/
extra-index-url = 
    http://your-proxy-host/123456789012/us-west-2/internal-packages/simple/
    http://your-proxy-host/987654321098/us-west-2/company-packages/simple/
```

### Docker Deployment

The service includes a Dockerfile for containerized deployment:

```bash
# Build the image locally
docker build -t codeartifact-proxy .

# Run the container with default settings
docker run -p 80:80 codeartifact-proxy

# Run with custom host and port
docker run -p 8080:8080 -e PORT=8080 codeartifact-proxy

# Run with environment variables
docker run -p 8080:8080 \
  -e LISTEN_ADDRESS=0.0.0.0 \
  -e PORT=8080 \
  -e DEBUG=true \
  codeartifact-proxy
```

### Pre-built Images

Pre-built Docker images are automatically available on GitHub Container Registry:

```bash
# Pull the latest image
docker pull ghcr.io/bra-fsn/codeartifact-proxy:latest

# Run the pre-built image
docker run -p 80:80 ghcr.io/bra-fsn/codeartifact-proxy:latest
```

## Configuration

### Environment Variables

**Service Configuration:**
- `LISTEN_ADDRESS`: Address to listen on (default: 0.0.0.0)
- `PORT`: Port to listen on (default: 80)
- `DEBUG`: Enable debug mode (default: false)

**AWS Credentials:**
The service uses AWS credentials from the standard AWS credential chain:
- AWS credentials file (`~/.aws/credentials`)
- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- IAM roles (when running on EC2/ECS)

### Constants

Key configuration constants in the code:
- `TOKEN_VALIDITY`: Token cache TTL (43200 seconds = 12 hours)
- `CHUNK_SIZE`: Streaming chunk size (64KB)
- `PYPI_BASE`: Public PyPI base URL
- `PIP_PASS_HEADERS`: Headers to pass through to upstream

## Deployment

### AWS ECS/Fargate

1. Build and push the Docker image to ECR
2. Create an ECS task definition with the image
3. Deploy as a service with appropriate IAM permissions

### Kubernetes

1. Create a deployment manifest
2. Ensure the service account has CodeArtifact permissions
3. Expose via service and ingress

### IAM Permissions

The service requires the following IAM permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "codeartifact:GetAuthorizationToken"
            ],
            "Resource": "*"
        }
    ]
}
```

## Monitoring

### Health Checks

Monitor the `/healthz` endpoint for:
- Service availability
- Authentication token errors
- Cache performance metrics

### Logs

The service logs:
- Token fetch operations
- Authentication errors
- Request processing errors

## Troubleshooting

### Common Issues

1. **Authentication Errors**: Check IAM permissions and AWS credentials
2. **Token Expiration**: Tokens are cached for 12 hours; errors will be reported in health endpoint
3. **Network Issues**: Ensure the service can reach both CodeArtifact and public PyPI

### Debug Mode

Enable debug mode using command-line option or environment variable:

```bash
# Command-line option
python proxy.py --debug

# Environment variable
DEBUG=true python proxy.py
```

This will enable Flask debug mode and set the log level to DEBUG.

## Security Considerations

- The service handles sensitive authentication tokens - ensure proper network security
- Use HTTPS in production environments
- Consider network policies to restrict access to authorized clients
- Regularly rotate AWS credentials used by the service

## Performance

- Token caching reduces API calls to CodeArtifact
- Streaming prevents memory issues with large packages
- Intelligent PyPI fallback improves download speeds for public packages
- TTL cache automatically manages token lifecycle
