"""API server launcher."""

import uvicorn

from api_view.config import API_HOST, API_PORT

if __name__ == "__main__":
    uvicorn.run(
        "api_view.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level="info",
    )
