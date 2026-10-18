"""
ngrok Tunnel Runner for Email Agent & MCP Server.

Creates a public HTTPS URL forwarding to your local MCP server (port 8001)
or FastAPI backend (port 8000) for connecting with ChatGPT or external clients.
"""

import os
import sys
import argparse
import logging
from dotenv import load_dotenv
from pyngrok import ngrok, conf

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("ngrok_tunnel")


def start_tunnel(port: int = 8001):
    """Starts an ngrok tunnel to the specified local port."""
    # Check for auth token in environment
    auth_token = os.environ.get("NGROK_AUTHTOKEN") or os.environ.get("NGROK_AUTH_TOKEN")
    if auth_token:
        logger.info("Configuring ngrok with provided auth token...")
        ngrok.set_auth_token(auth_token)
    else:
        logger.warning(
            "\n[TIP] If you see an authentication error from ngrok, add your free auth token to .env:\n"
            "      NGROK_AUTHTOKEN=your_token_from_dashboard.ngrok.com\n"
            "      Or run: uv run ngrok config add-authtoken <your-token>\n"
        )

    try:
        logger.info("Opening ngrok tunnel to local port %d...", port)
        public_tunnel = ngrok.connect(port, "http")
        public_url = public_tunnel.public_url

        # Ensure HTTPS scheme
        if public_url.startswith("http://"):
            public_url = public_url.replace("http://", "https://", 1)

        print("\n" + "=" * 65)
        print("          NGROK PUBLIC TUNNEL ESTABLISHED!          ")
        print("=" * 65)
        print(f"  Local Port:         {port}")
        print(f"  Public HTTPS URL:   {public_url}")
        if port == 8001:
            print(f"  ChatGPT MCP URL:    {public_url}/mcp")
        elif port == 8000:
            print(f"  FastAPI Docs URL:   {public_url}/docs")
            print(f"  Health Check URL:   {public_url}/health")
        print("=" * 65)
        print("\nPress Ctrl+C to stop the tunnel.\n")

        # Keep alive
        ngrok_process = ngrok.get_ngrok_process()
        ngrok_process.proc.wait()

    except KeyboardInterrupt:
        print("\nStopping ngrok tunnel...")
        ngrok.kill()
        print("Tunnel closed.")
    except Exception as exc:
        logger.error("Failed to start ngrok tunnel: %s", str(exc))
        print(
            "\nTroubleshooting:\n"
            "1. If ngrok requires an account, get your free auth token at https://dashboard.ngrok.com/signup\n"
            "2. Add to your .env: NGROK_AUTHTOKEN=your_token_here\n"
            "3. Or run in terminal: uv run ngrok config add-authtoken <your_token>\n"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start an ngrok tunnel for Email Agent services.")
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Local port to forward (default: 8001 for MCP server, 8000 for FastAPI API)"
    )
    args = parser.parse_args()
    start_tunnel(port=args.port)
