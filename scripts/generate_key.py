import base64
import os


def main() -> None:
    key = os.urandom(32)
    print(base64.urlsafe_b64encode(key).decode("utf-8"))


if __name__ == "__main__":
    main()

