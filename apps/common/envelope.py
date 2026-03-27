"""
API response envelope following the Scout pattern.

Provides consistent response shapes for success and error cases,
with request timing in milliseconds.
"""
import time

_request_start = None


def start_timing():
    global _request_start
    _request_start = time.monotonic()


def success_response(data, warnings=None):
    elapsed = int((time.monotonic() - (_request_start or time.monotonic())) * 1000)
    resp = {"success": True, "data": data, "timing_ms": elapsed}
    if warnings:
        resp["warnings"] = warnings
    return resp


def error_response(code, message, status=400):
    elapsed = int((time.monotonic() - (_request_start or time.monotonic())) * 1000)
    return {"success": False, "error": {"code": code, "message": message}, "timing_ms": elapsed}
