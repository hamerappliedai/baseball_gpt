"""Read SABR's public Box shared folder without an API token.

SABR publishes each Lahman release as a public Box folder. Box offers no
unauthenticated API for shared folders, so:
  - the file listing comes from the JSON Box embeds in the folder page
    (`Box.postStreamData`), one request per page of the listing;
  - each file downloads from Box's shared-file download endpoint by file id.

Only `discover` uses the listing. Normal builds download by the file ids pinned
in the manifest, so a change to Box's page layout cannot break a routine build.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

BOX_HOST = "https://sabr.app.box.com"
USER_AGENT = "baseball-gpt-pipeline/0.1"
TIMEOUT = 60

_STREAM_DATA = re.compile(r"Box\.postStreamData\s*=\s*(\{.*?\});\s*</script>", re.S)


@dataclass
class BoxFile:
    name: str
    typed_id: str  # "f_<id>"
    size: int


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _folder_page(shared_name: str, page: int) -> dict:
    url = f"{BOX_HOST}/s/{urllib.parse.quote(shared_name)}?page={page}"
    html = _get(url).decode("utf-8", "replace")
    m = _STREAM_DATA.search(html)
    if not m:
        raise RuntimeError(f"No folder listing found in {url}; Box's page layout may have changed")
    data = json.loads(m.group(1))
    try:
        return data["/app-api/enduserapp/shared-folder"]
    except KeyError:
        raise RuntimeError(f"{url} is not a shared folder") from None


def list_shared_folder(shared_name: str) -> list[BoxFile]:
    """Every file in a public shared folder, across all pages of the listing."""
    files: list[BoxFile] = []
    page, page_count = 1, 1
    while page <= page_count:
        folder = _folder_page(shared_name, page)
        page_count = int(folder.get("pageCount", 1))
        for item in folder["items"]:
            if item.get("type") == "file":
                files.append(BoxFile(item["name"], item["typedID"], int(item["itemSize"])))
        page += 1
    names = [f.name for f in files]
    if len(names) != len(set(names)):
        raise RuntimeError(f"Duplicate file names in Box folder {shared_name}")
    return files


def download_url(shared_name: str, typed_id: str) -> str:
    query = urllib.parse.urlencode(
        {"rm": "box_download_shared_file", "shared_name": shared_name, "file_id": typed_id}
    )
    return f"{BOX_HOST}/index.php?{query}"


def download(shared_name: str, typed_id: str) -> bytes:
    return _get(download_url(shared_name, typed_id))
