import io


def post(client, url, data=None, **kwargs):
    payload = {"csrf_token": client.csrf}
    if data:
        payload.update(data)
    return client.post(url, data=payload, **kwargs)


def upload(client, filename, raw, content_type="application/zip"):
    handle = raw if hasattr(raw, "read") else io.BytesIO(raw)
    return post(
        client,
        "/upload",
        {"genome": (handle, filename)},
        content_type="multipart/form-data",
    )
