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

def fetch_scenario_ini(url, retries=3, delay=2):
    """
    Fetch the first .ini file found in the given external repository URL.
    Tries to list files in the repo and fetch the first .ini file found.
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
        logging.warning(f"URL does not contain raw.githubusercontent.com: {url}")
    return None

def get_latest_commit_date(url, retries=3, delay=2):
    logging.info(f"Fetching latest commit date for: {url}")
    parsed = urlparse(url)
    if "raw.githubusercontent.com" in parsed.netloc:
        parts = parsed.path.strip('/').split('/')
        if "raw.githubusercontent.com" in parsed.netloc and len(parts) >= 4:
            user, repo, branch = parts[:3]
            repo_api = f"https://api.github.com/repos/{user}/{repo}/commits?sha={branch}&path={'/'.join(parts[3:])}"
        elif "raw.githubusercontent.com" in parsed.netloc and len(parts) >= 2:
            user, repo = parts[:2]
            repo_api = f"https://api.github.com/repos/{user}/{repo}/commits"
        else:
            logging.warning(f"Could not parse repo info from url: {url}")
            return ""
        headers = {}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"
        for attempt in range(1, retries + 1):
            try:
                resp = requests.get(repo_api, headers=headers, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and data:
                        date = data[0]["commit"]["committer"]["date"]
                        logging.info(f"Latest commit date for {url}: {date}")
                        return date
                    else:
                        logging.warning(f"No commits found for {url}, attempt {attempt}/{retries}")
                else:
                    logging.warning(f"Failed to fetch commits from {repo_api} (status {resp.status_code}), attempt {attempt}/{retries}")
            except Exception as e:
                logging.error(f"Exception while fetching commits from {repo_api} (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(delay)
    else:
        logging.info(f"Non-GitHub URL, skipping commit date fetch: {url}")
    return ""

def parse_manifest_ini(manifest_path):
    logging.info(f"Parsing manifest.ini from: {manifest_path}")
    config = configparser.ConfigParser()
    config.optionxform = str  # preserve case
    config.read(manifest_path, encoding="utf-8")
    return config

def write_manifest_download_ini(scenarios, out_path):
    logging.info(f"Writing manifestDownload.ini to: {out_path}")
    with open(out_path, "w", encoding="utf-8") as f:
        # Write header line with timestamp and scenario count
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S'UTC'")
        f.write(f"# Generated the {now} with {len(scenarios)} scenarios\n")
        for scenario in scenarios:
            f.write(f'[{scenario["name"]}]\n')
            for k, v in scenario["data"].items():
                f.write(f"{k}={v}\n")
            f.write("\n")
    logging.info(f"Finished writing manifestDownload.ini with {len(scenarios)} scenarios.")
    # Log the full content of the generated file
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            content = f.read()
            logging.info(f"Content of {out_path}:\n{content}")
    except Exception as e:
        logging.error(f"Could not read {out_path} for logging: {e}")

def process_scenario_section(section, config):
    if "external" not in config[section]:
        logging.warning(f"Section [{section}] missing 'external' entry, skipping.")
        return None
    external_url = config[section]["external"]
    scenario_ini_content = fetch_scenario_ini(external_url)
    if not scenario_ini_content:
        logging.warning(f"Could not fetch scenario.ini for [{section}], skipping.")
        return None

    # Parse scenario.ini
    scenario_config = configparser.ConfigParser()
    scenario_config.optionxform = str
    scenario_config.read_string(scenario_ini_content)

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
    scenario_data["latest_update"] = get_latest_commit_date(external_url)

    logging.info(f"Parsed scenario: [{section}] with url: {external_url}")

    return {
        "name": section,
        "data": scenario_data
    }

def main():
    logging.info("Starting manifest_sync.py script")
    if len(sys.argv) < 2:
        logging.error("Usage: manifest_sync.py <GameType>")
        sys.exit(1)
    game_type = sys.argv[1]
    manifest_path = "manifest.ini"
    output_path = get_manifest_path(game_type)
    logging.info("Manifest path to update: " + output_path)

    config = parse_manifest_ini(manifest_path)
    scenarios = []

    for section in config.sections():
        try:
            scenario = process_scenario_section(section, config)
            if scenario:
                scenarios.append(scenario)
        except Exception as e:
            logging.error(f"Exception while processing section [{section}]: {e}", exc_info=True)

    write_manifest_download_ini(scenarios, output_path)
    logging.info("manifest_sync.py script finished successfully.")

if __name__ == "__main__":
    main()