FROM python:3.13-slim
RUN --mount=type=tmpfs,target=/tmp,rw\
    --mount=id=root,type=cache,target=/root,sharing=shared \
    pip install boto3 requests flask cachetools click
ADD proxy.py /usr/local/bin/proxy.py
CMD ["python", "/usr/local/bin/proxy.py"]
