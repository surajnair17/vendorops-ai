import os

import httpx
import streamlit as st


def api(method: str, path: str, **kwargs):
    url = os.getenv("VENDOROPS_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    try:
        response = httpx.request(
            method,
            f"{url}/api/v1{path}",
            timeout=float(os.getenv("VENDOROPS_REQUEST_TIMEOUT_SECONDS", "60")),
            **kwargs,
        )
        if response.is_error:
            try:
                message = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = f"Backend error: HTTP {response.status_code}"
            st.error(message)
            return None
        return response.json()
    except httpx.TimeoutException:
        st.error("The request timed out. Refresh job status before retrying an action.")
    except (httpx.RequestError, ValueError):
        st.error("Cannot read a response from the backend. Check its address and status.")
    return None
