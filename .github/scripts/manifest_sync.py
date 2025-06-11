import sys
import os
import configparser
import requests
from urllib.parse import urlparse
from datetime import datetime, UTC
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def get_manifest_path(game_type):
    logging.info(f"Getting manifest path for GameType: {game_type}")
    if game_type == "D2E":
        return "D2E/manifestDownload.ini"
    else:
        return "MoM/manifestDownload.ini"

def get_contentpackmanifest_path(game_type):
    logging.info(f"Getting content pack manifest path for GameType: {game_type}")
    if game_type == "D2E":
        return "D2E/contentPacksManifestDownload.ini"
    else:
        return "MoM/contentPacksManifestDownload.ini"

def fetch_scenario_ini(url, scenario_name=None, retries=3, delay=2):
    """
    Fetch the first .ini file found in the given external repository URL.
    Tries to list files in the repo and fetch the first .ini file found.
    If not a GitHub raw URL, tries to fetch {url}/{scenario_name}.ini directly.
    """
    if url.endswith('/'):
        url = url[:-1]

    parsed = urlparse(url)
    if "raw.githubusercontent.com" in parsed.netloc:
        parts = parsed.path.strip('/').split('/')
        logging.debug(f"Parsed URL parts: {parts}")
        if len(parts) >= 3:
            user, repo, branch = parts[:3]
            repo_path = '/'.join(parts[3:]) if len(parts) > 3 else ''
            if repo_path:
                api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{repo_path}?ref={branch}"
            else:
                api_url = f"https://api.github.com/repos/{user}/{repo}/contents?ref={branch}"
            headers = {}
            token = os.environ.get("GITHUB_TOKEN")
            if token:
                headers["Authorization"] = f"token {token}"
            for attempt in range(1, retries + 1):
                try:
                    resp = requests.get(api_url, headers=headers, timeout=20)
                    if resp.status_code == 200:
                        files = resp.json()
                        if not isinstance(files, list):
                            logging.warning(f"API response is not a list at {api_url}: {files}")
                            return None
                        ini_file = None
                        for file in files:
                            if file["name"].lower().endswith(".ini"):
                                ini_file = file["download_url"]
                                break
                        if ini_file:
                            ini_resp = requests.get(ini_file, timeout=20)
                            if ini_resp.status_code == 200:
                                logging.info(f"Successfully fetched ini file from: {ini_file}")
                                return ini_resp.text
                            else:
                                logging.warning(f"Failed to fetch ini file from: {ini_file} (status {ini_resp.status_code}), attempt {attempt}/{retries}")
                        else:
                            logging.warning(f"No .ini file found in repo listing at {api_url}")
                            return None
                    else:
                        logging.warning(f"Failed to list files from {api_url} (status {resp.status_code}), attempt {attempt}/{retries}")
                except Exception as e:
                    logging.error(f"Exception while listing/fetching ini file from {api_url} (attempt {attempt}/{retries}): {e}")
                if attempt < retries:
                    time.sleep(delay)
            logging.error(f"All attempts failed to fetch .ini file from repo at {api_url}")
            return None
        else:
            logging.warning(f"URL path does not have enough parts to extract user/repo/branch: {url} (parts: {parts})")
    else:
        # Try fetching {url}/{scenario_name}.ini directly for non-GitHub URLs
        if scenario_name:
            ini_url = f"{url}/{scenario_name}.ini"
            for attempt in range(1, retries + 1):
                try:
                    resp = requests.get(ini_url, timeout=20)
                    if resp.status_code == 200:
                        logging.info(f"Successfully fetched ini file from: {ini_url}")
                        return resp.text
                    else:
                        logging.warning(f"Failed to fetch ini file from: {ini_url} (status {resp.status_code}), attempt {attempt}/{retries}")
                except Exception as e:
                    logging.error(f"Exception while fetching ini file from {ini_url} (attempt {attempt}/{retries}): {e}")
                if attempt < retries:
                    time.sleep(delay)
            logging.error(f"All attempts failed to fetch .ini file from {ini_url}")
        else:
            logging.warning(f"No scenario_name provided for non-GitHub URL: {url}")
    return None

def get_latest_commit_date(url, retries=3, delay=2, file_extension=".valkyrie"):
    logging.info(f"Fetching latest commit date for: {url} (extension: {file_extension})")
    parsed = urlparse(url)
    if "raw.githubusercontent.com" in parsed.netloc:
        parts = parsed.path.strip('/').split('/')
        if len(parts) >= 3:
            user, repo, branch = parts[:3]
            repo_path = '/'.join(parts[3:]) if len(parts) > 3 else ''
            if repo_path:
                api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{repo_path}?ref={branch}"
            else:
                api_url = f"https://api.github.com/repos/{user}/{repo}/contents?ref={branch}"
            headers = {}
            token = os.environ.get("GITHUB_TOKEN")
            if token:
                headers["Authorization"] = f"token {token}"
            target_file_path = None
            for attempt in range(1, retries + 1):
                try:
                    resp = requests.get(api_url, headers=headers, timeout=20)
                    if resp.status_code == 200:
                        files = resp.json()
                        if not isinstance(files, list):
                            logging.warning(f"API response is not a list at {api_url}: {files}")
                            return "1970-01-01T12:28:29Z"
                        for file in files:
                            if file["name"].lower().endswith(file_extension.lower()):
                                target_file_path = file["path"]
                                break
                        if target_file_path:
                            break
                        else:
                            logging.warning(f"No {file_extension} file found in repo listing at {api_url}")
                            return "1970-01-01T12:28:29Z"
                    else:
                        logging.warning(f"Failed to list files from {api_url} (status {resp.status_code}), attempt {attempt}/{retries}")
                except Exception as e:
                    logging.error(f"Exception while listing files from {api_url} (attempt {attempt}/{retries}): {e}")
                if attempt < retries:
                    time.sleep(delay)
            if not target_file_path:
                logging.warning(f"No {file_extension} file found after all attempts in {api_url}")
                return "1970-01-01T12:28:29Z"
            repo_api = f"https://api.github.com/repos/{user}/{repo}/commits?sha={branch}&path={target_file_path}"
            for attempt in range(1, retries + 1):
                try:
                    resp = requests.get(repo_api, headers=headers, timeout=20)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list) and data:
                            date = data[0]["commit"]["committer"]["date"]
                            logging.info(f"Latest commit date for {target_file_path} in {url}: {date}")
                            return date
                        else:
                            logging.warning(f"No commits found for {target_file_path} in {url}, attempt {attempt}/{retries}")
                    else:
                        logging.warning(f"Failed to fetch commits from {repo_api} (status {resp.status_code}), attempt {attempt}/{retries}")
                except Exception as e:
                    logging.error(f"Exception while fetching commits from {repo_api} (attempt {attempt}/{retries}): {e}")
                if attempt < retries:
                    time.sleep(delay)
            logging.error(f"All attempts failed to fetch commit date for {target_file_path} in {repo_api}")
            return "1970-01-01T12:28:29Z"
        else:
            logging.warning(f"Could not parse repo info from url: {url}")
            return "1970-01-01T12:28:29Z"
    else:
        logging.info(f"Non-GitHub URL, returning date placeholder instead of getting commit date fetch: {url}")
        return "1970-01-01T12:28:29Z"

def parse_manifest_ini(manifest_path):
    logging.info(f"Parsing manifest.ini from: {manifest_path}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_content = f.read()
    logging.debug(f"Manifest file content:\n{manifest_content}")
    config = configparser.ConfigParser()
    config.optionxform = str  # preserve case
    config.read_string(manifest_content)
    return config

def write_manifest_download_ini(scenarios, out_path, is_content_pack=False):
    logging.info(f"Writing manifestDownload.ini to: {out_path}")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            # Write header line with scenario or content pack count
            if is_content_pack:
                f.write(f"# Generated with {len(scenarios)} content packs\n")
            else:
                f.write(f"# Generated with {len(scenarios)} scenarios\n")
            for scenario in scenarios:
                f.write(f'[{scenario["name"]}]\n')
                for k, v in scenario["data"].items():
                    f.write(f"{k}={v}\n")
                f.write("\n")
        if is_content_pack:
            logging.info(f"Finished writing manifestDownload.ini with {len(scenarios)} content packs.")
        else:
            logging.info(f"Finished writing manifestDownload.ini with {len(scenarios)} scenarios.")
    except Exception as e:
        logging.error(f"Failed to write manifestDownload.ini to {out_path}: {e}", exc_info=True)

def process_scenario_section(section, config, file_extension=".valkyrie"):
    if "external" not in config[section]:
        logging.warning(f"Section [{section}] missing 'external' entry, skipping.")
        return None
    external_url = config[section]["external"]
    scenario_ini_content = fetch_scenario_ini(external_url, scenario_name=section)
    if not scenario_ini_content:
        logging.warning(f"Could not fetch scenario.ini for [{section}], skipping.")
        return None

    # Parse scenario.ini with interpolation disabled to handle '%' characters
    scenario_config = configparser.ConfigParser(interpolation=None)
    scenario_config.optionxform = str

    # Try parsing, and if a BOM is present or a section header error occurs, try to recover
    try:
        scenario_config.read_string(scenario_ini_content)
    except configparser.MissingSectionHeaderError as e:
        logging.warning(f"Missing section header or BOM in scenario.ini for [{section}]: {e}. Trying to recover by stripping BOM and retrying.")
        # Remove BOM if present and try again
        cleaned_content = scenario_ini_content.lstrip('\ufeff')
        try:
            scenario_config.read_string(cleaned_content)
        except Exception as e2:
            logging.error(f"Failed to parse scenario.ini for [{section}] after BOM removal: {e2}")
            return None
    except configparser.InterpolationSyntaxError as e:
        logging.error(f"Interpolation error while parsing scenario.ini for [{section}]: {e}")
        return None
    except Exception as e:
        logging.error(f"General error while parsing scenario.ini for [{section}]: {e}")
        return None

    # Rename [Quest] to [ScenarioName]
    scenario_data = {}
    if "Quest" in scenario_config:
        for k, v in scenario_config["Quest"].items():
            scenario_data[k] = v
    else:
        # fallback: use first section if not [Quest]
        first_section = scenario_config.sections()[0]
        for k, v in scenario_config[first_section].items():
            scenario_data[k] = v

    # Add url and latest_update
    scenario_data["url"] = external_url
    scenario_data["latest_update"] = get_latest_commit_date(external_url, file_extension=file_extension)

    logging.info(f"Parsed scenario: [{section}] with url: {external_url}")

    return {
        "name": section,
        "data": scenario_data
    }

def process_manifest(manifest_path, output_path):
    logging.info("Manifest path to update: " + output_path)
    config = parse_manifest_ini(manifest_path)
    scenarios = []

    logging.info(f"Found {len(config.sections())} scenarios in manifest.")

    for section in config.sections():
        try:
            scenario = process_scenario_section(section, config)  # uses default .valkyrie
            if scenario:
                scenarios.append(scenario)
        except Exception as e:
            logging.error(f"Exception while processing section [{section}]: {e}", exc_info=True)

    write_manifest_download_ini(scenarios, output_path, is_content_pack=False)
    logging.info(f"Finished processing manifest: {manifest_path}")

def process_contentpacks_manifest(cp_manifest_path, cp_output_path):
    logging.info(f"Processing ContentPacks manifest: {cp_manifest_path}")
    cp_config = parse_manifest_ini(cp_manifest_path)
    cp_packs = []

    logging.info(f"Found {len(cp_config.sections())} content packs in ContentPacks manifest.")

    for section in cp_config.sections():
        try:
            contentPack = process_scenario_section(section, cp_config, file_extension=".valkyrieContentPack")
            if contentPack:
                cp_packs.append(contentPack)
        except Exception as e:
            logging.error(f"Exception while processing ContentPacks section [{section}]: {e}", exc_info=True)

    write_manifest_download_ini(cp_packs, cp_output_path, is_content_pack=True)
    logging.info("ContentPacks manifest_sync finished successfully.")

def main():
    logging.info("Starting manifest_sync.py script")
    if len(sys.argv) < 2:
        logging.error("Usage: manifest_sync.py <GameType>")
        sys.exit(1)
    game_type = sys.argv[1]

    # manifest_path = "manifest.ini"
    # output_path = get_manifest_path(game_type)
    # process_manifest(manifest_path, output_path)

    # --- Repeat for ContentPacks ---
    cp_manifest_path = "contentPacksManifest.ini"
    cp_output_path = get_contentpackmanifest_path(game_type)
    process_contentpacks_manifest(cp_manifest_path, cp_output_path)

if __name__ == "__main__":
    main()