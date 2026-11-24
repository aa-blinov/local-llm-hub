"""Child process that downloads one Hugging Face repository.

Run as a separate process so the panel can stop it at any moment (cancel).
Arguments: repository, cache directory. The token, if any, comes from HF_TOKEN.
"""
import os
import sys


def main() -> int:
    repo, cache_dir = sys.argv[1], sys.argv[2]
    from huggingface_hub import snapshot_download
    try:
        snapshot_download(repo, cache_dir=cache_dir, token=os.environ.get("HF_TOKEN") or None)
    except Exception as e:  # the parent turns this into a readable message
        print(f"{type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
