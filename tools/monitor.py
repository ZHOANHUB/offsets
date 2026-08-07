import json
import os
import sys
import time
import hashlib
import subprocess
import urllib.request
import urllib.error

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = "ZHOANHUB/offsets"
BRANCH = "main"
VERSION_URL = "https://clientsettings.roblox.com/v2/client-version/WindowsPlayer"
CURRENT_VERSION_FILE = os.path.join(os.path.dirname(__file__), "current_version.json")


def get_roblox_version():
    try:
        req = urllib.request.Request(VERSION_URL, headers={'User-Agent': 'ZHOAN'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get('clientVersionUpload', None)
    except Exception as e:
        print(f"Error checking Roblox version: {e}")
        return None


def download_roblox(version):
    download_url = f"https://setup.rbxcdn.com/{version}-WindowsPlayer.zip"
    zip_path = os.path.join(os.path.dirname(__file__), "roblox_update.zip")
    exe_path = os.path.join(os.path.dirname(__file__), "RobloxPlayerBeta.exe")
    try:
        print(f"Downloading Roblox {version}...")
        urllib.request.urlretrieve(download_url, zip_path)
        import zipfile
        with zipfile.ZipFile(zip_path, 'r') as z:
            for name in z.namelist():
                if name.endswith('RobloxPlayerBeta.exe'):
                    with z.open(name) as src, open(exe_path, 'wb') as dst:
                        dst.write(src.read())
                    break
        os.remove(zip_path)
        if os.path.exists(exe_path):
            print(f"Downloaded: {exe_path}")
            return exe_path
    except Exception as e:
        print(f"Download error: {e}")
    return None


def load_current_version():
    if os.path.exists(CURRENT_VERSION_FILE):
        with open(CURRENT_VERSION_FILE) as f:
            return json.load(f)
    return {}


def save_current_version(version, offsets):
    with open(CURRENT_VERSION_FILE, 'w') as f:
        json.dump({'version': version, 'offsets': offsets}, f, indent=2)


def github_api(endpoint, method='GET', data=None, token=None):
    url = f"https://api.github.com/{endpoint}"
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'ZHOAN-Updater'
    }
    if token:
        headers['Authorization'] = f"token {token}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"GitHub API error {e.code}: {error_body}")
        return None


def get_file_sha(filepath):
    with open(filepath, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


def update_github_file(filepath, repo_path, commit_msg, token):
    with open(filepath, 'r') as f:
        content = f.read()
    import base64
    b64_content = base64.b64encode(content.encode()).decode()

    existing = github_api(f"repos/{repo}/contents/{repo_path}", token=token)
    payload = {
        'message': commit_msg,
        'content': b64_content,
        'branch': BRANCH
    }
    if existing and 'sha' in existing:
        payload['sha'] = existing['sha']

    result = github_api(f"repos/{repo}/contents/{repo_path}", method='PUT', data=payload, token=token)
    if result:
        print(f"Updated {repo_path} on GitHub")
        return True
    return False


def update_version_json(new_version, token):
    version_data = {
        "version": new_version,
        "url": f"https://github.com/{REPO}/releases/download/v1.0.0/ZHOAN.exe"
    }
    tmp = os.path.join(os.path.dirname(__file__), "version.json")
    with open(tmp, 'w') as f:
        json.dump(version_data, f, indent=2)
    return update_github_file(tmp, "version.json", f"update version to {new_version}", token)


def update_offsets_json(offsets, roblox_version, token):
    current = load_offsets_from_github(token)
    current.update(offsets)
    current['roblox_version'] = roblox_version
    tmp = os.path.join(os.path.dirname(__file__), "offsets.json")
    with open(tmp, 'w') as f:
        json.dump(current, f, indent=2)
    return update_github_file(tmp, "offsets.json", f"update offsets for Roblox {roblox_version}", token)


def load_offsets_from_github(token):
    try:
        result = github_api(f"repos/{REPO}/contents/offsets.json", token=token)
        if result and 'content' in result:
            import base64
            content = base64.b64decode(result['content']).decode()
            return json.loads(content)
    except:
        pass
    return {}


def load_local_offsets():
    offsets_path = os.path.join(os.path.dirname(__file__), '..', 'offsets.json')
    if os.path.exists(offsets_path):
        with open(offsets_path) as f:
            return json.load(f)
    return {}


def save_local_offsets(offsets):
    offsets_path = os.path.join(os.path.dirname(__file__), '..', 'offsets.json')
    with open(offsets_path, 'w') as f:
        json.dump(offsets, f, indent=2)


def run_offset_finder(exe_path):
    finder = os.path.join(os.path.dirname(__file__), 'offset_finder.py')
    try:
        result = subprocess.run(
            [sys.executable, finder, exe_path],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('{'):
                    return json.loads(line)
    except Exception as e:
        print(f"Finder error: {e}")
    return None


def run_monitor():
    print("=== ZHOAN Auto-Updater Monitor ===")

    current = load_current_version()
    current_version = current.get('version', '')
    current_offsets = current.get('offsets', {})

    print(f"Current tracked version: {current_version or 'none'}")

    roblox_version = get_roblox_version()
    if not roblox_version:
        print("Cannot check Roblox version, aborting")
        return False
    print(f"Latest Roblox version: {roblox_version}")

    if roblox_version == current_version:
        print("Already up to date")
        return True

    print(f"New version detected: {roblox_version}")
    exe_path = download_roblox(roblox_version)
    if not exe_path:
        print("Failed to download Roblox")
        return False

    print("Running offset finder...")
    found = run_offset_finder(exe_path)
    if not found:
        print("Offset finder failed")
        return False

    module = found.get('module', {})
    print(f"Found offsets: {json.dumps(module, indent=2)}")

    new_offsets = {}
    for key, value in module.items():
        if value is not None:
            new_offsets[key] = value

    if not new_offsets:
        print("No valid offsets found")
        return False

    token = GITHUB_TOKEN
    if not token:
        print("No GITHUB_TOKEN set, saving locally only")
        save_current_version(roblox_version, new_offsets)
        merged = load_local_offsets()
        merged.update(new_offsets)
        save_local_offsets(merged)
        print("Offsets saved locally")
        return True

    print("Updating GitHub...")
    success = True
    if not update_offsets_json(new_offsets, roblox_version, token):
        print("Failed to update offsets.json")
        success = False
    if not update_version_json(roblox_version, token):
        print("Failed to update version.json")
        success = False

    if success:
        save_current_version(roblox_version, new_offsets)
        print(f"SUCCESS: Offsets updated for Roblox {roblox_version}")
    else:
        print("Some updates failed")

    try:
        os.remove(exe_path)
    except:
        pass

    return success


if __name__ == '__main__':
    success = run_monitor()
    sys.exit(0 if success else 1)
