import getpass
import os
import sys

import keyring

from .config import KEYRING_SERVICE, KEYRING_USERNAME


def get_api_key() -> str:
    env_key = os.environ.get("OPENAI_API_KEY")
    if env_key:
        return env_key

    key = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if key:
        return key

    print("Missing OpenAI API key.")
    print("Run: python -m voice_transcription.set_api_key")
    sys.exit(1)


def set_api_key_interactive() -> None:
    print("")
    print("Paste your OpenAI API key.")
    print("It will be hidden as you type.")
    api_key = getpass.getpass("OpenAI API key: ").strip()

    if not api_key:
        print("No API key entered.")
        sys.exit(1)

    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, api_key)

    print("")
    print("Saved API key to your OS credential store.")
    print(f"Service: {KEYRING_SERVICE}")
    print(f"Username: {KEYRING_USERNAME}")


def delete_api_key() -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        print("Deleted API key from OS credential store.")
    except keyring.errors.PasswordDeleteError:
        print("No saved API key found.")
