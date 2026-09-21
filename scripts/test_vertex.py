import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    parser = argparse.ArgumentParser(description="Test a Gemini tuned endpoint with synthetic surf data.")
    parser.add_argument("--project", default=os.environ.get("VERTEX_PROJECT_ID"), help="Project ID or number owning the endpoint")
    parser.add_argument("--check-permissions", action="store_true", help="Check project permissions without model inference")
    args = parser.parse_args()
    if not args.project:
        parser.error("Set VERTEX_PROJECT_ID in .env or pass --project")

    credentials_json = os.environ.get("GOOGLE_CREDENTIALS")
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    if credentials_json:
        credential_source = "GOOGLE_CREDENTIALS"
        credentials = Credentials.from_service_account_info(json.loads(credentials_json), scopes=scopes)
    else:
        credential_source = os.environ.get(
            "GOOGLE_CREDENTIALS_FILE",
            r"D:\antigravity\surf-data-automation\secrets\google-key.json",
        )
        credentials = Credentials.from_service_account_file(
            os.environ.get(
                "GOOGLE_CREDENTIALS_FILE",
                r"D:\antigravity\surf-data-automation\secrets\google-key.json",
            ),
            scopes=scopes,
        )

    location = os.environ.get("VERTEX_LOCATION", "us")
    endpoint_id = os.environ.get("VERTEX_ENDPOINT_ID", "3548132818926174208")
    endpoint = f"projects/{args.project}/locations/{location}/endpoints/{endpoint_id}"
    host = f"aiplatform.{location}.rep.googleapis.com" if location in ("us", "eu") else f"{location}-aiplatform.googleapis.com"
    url = f"https://{host}/v1beta1/{endpoint}:generateContent"
    prompt = (
        "請根據以下海況生成一段簡短評語：\n"
        "Wave Height (m): 1.2\n"
        "Wave Period (s): 8\n"
        "Wave Direction: 90\n"
        "Wind Speed (m/s): 3\n"
        "Wind Direction: 270\n"
        "Sea Level (m): 0.2\n"
        "Time: 09:00\n"
        "Spot: Doublelion"
    )
    print(f"Endpoint: {endpoint}")
    print(f"Credentials source: {credential_source}")
    print(f"Service account: {credentials.service_account_email}")
    with AuthorizedSession(credentials) as session:
        if args.check_permissions:
            response = session.post(
                f"https://cloudresourcemanager.googleapis.com/v1/projects/{args.project}:testIamPermissions",
                json={"permissions": ["aiplatform.endpoints.predict", "aiplatform.endpoints.get", "resourcemanager.projects.get"]},
                timeout=30,
            )
            print(f"Project permission check HTTP status: {response.status_code}")
            print(response.text)
            if not response.ok:
                return 1
            granted = response.json().get("permissions", [])
            print("Project-level predict permission: " + ("GRANTED" if "aiplatform.endpoints.predict" in granted else "NOT GRANTED"))
            print("This project-level check does not evaluate endpoint-specific grants or conditions.")
            return 0
        response = session.post(
            url,
            json={
                "systemInstruction": {"parts": [{"text": "你是一個衝浪海況分析助手，根據海況數值生成簡短、自然的浪人回饋。"}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            },
            timeout=120,
        )
    print(f"HTTP status: {response.status_code}")
    if not response.ok:
        print(response.text)
        return 1

    data = response.json()
    parts = [
        part["text"]
        for candidate in data.get("candidates", [])
        for part in candidate.get("content", {}).get("parts", [])
        if part.get("text") and not part.get("thought")
    ]
    if not parts:
        print("No answer text returned:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 1
    print("\n".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
