import threading
import time
import requests

from apps.produtos.services.bling.auth_bridge import get_access_token

BASE_URL = "https://api.bling.com.br/Api/v3"
MIN_SECONDS_BETWEEN_REQUESTS = 0.45
RETRY_STATUS = {429, 500, 502, 503, 504}
_last_request_monotonic = 0.0
_rate_limit_lock = threading.Lock()


def _headers():
    return {"Authorization": f"Bearer {get_access_token()}", "Content-Type": "application/json"}


def _raise_for_status_with_body(resp: requests.Response) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        body = ""
        try:
            body = resp.text or ""
        except Exception:
            body = ""
        if body:
            raise requests.HTTPError(f"{e} | response={body}", response=resp) from e
        raise


def _respect_rate_limit() -> None:
    global _last_request_monotonic
    with _rate_limit_lock:
        now = time.monotonic()
        wait = MIN_SECONDS_BETWEEN_REQUESTS - (now - _last_request_monotonic)
        if wait > 0:
            time.sleep(wait)
        _last_request_monotonic = time.monotonic()


def _retry_sleep_seconds(resp: requests.Response | None, attempt: int) -> float:
    if resp is not None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), MIN_SECONDS_BETWEEN_REQUESTS)
            except (TypeError, ValueError):
                pass
    return max(MIN_SECONDS_BETWEEN_REQUESTS, 0.8 * (attempt + 1))


def _request_with_retry(method: str, path: str, *, params=None, json=None, timeout=30, retries: int = 3):
    url = f"{BASE_URL}{path}"
    last_exc = None
    for attempt in range(retries + 1):
        try:
            _respect_rate_limit()
            resp = requests.request(
                method,
                url,
                headers=_headers(),
                params=params,
                json=json,
                timeout=timeout,
            )
            if resp.status_code in RETRY_STATUS and attempt < retries:
                time.sleep(_retry_sleep_seconds(resp, attempt))
                continue
            _raise_for_status_with_body(resp)
            return resp.json()
        except requests.RequestException as e:
            last_exc = e
            if attempt >= retries:
                raise
            response = getattr(e, "response", None)
            time.sleep(_retry_sleep_seconds(response, attempt))
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Falha inesperada na requisicao Bling: {method} {path}")


def bling_get(path: str, params=None, timeout=30, retries: int = 3):
    return _request_with_retry("GET", path, params=params, timeout=timeout, retries=retries)


def bling_post(path: str, json=None, timeout=30, retries: int = 5):
    return _request_with_retry("POST", path, json=json, timeout=timeout, retries=retries)


def bling_patch(path: str, json=None, timeout=30, retries: int = 5):
    return _request_with_retry("PATCH", path, json=json, timeout=timeout, retries=retries)


def bling_put(path: str, json=None, timeout=30, retries: int = 3):
    return _request_with_retry("PUT", path, json=json, timeout=timeout, retries=retries)


def bling_request_raw(method: str, path: str, *, json=None, params=None, timeout=30) -> "requests.Response":
    """Retorna Response bruto (sem raise) para checar status code manualmente."""
    url = f"{BASE_URL}{path}"
    _respect_rate_limit()
    return requests.request(method, url, headers=_headers(), json=json, params=params, timeout=timeout)
