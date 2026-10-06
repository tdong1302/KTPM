"""Exercise the main API journeys and write redacted Markdown/JSON evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable


class DemoFailure(RuntimeError):
    """Raised when an observed API result does not match the demo contract."""


@dataclass
class StepResult:
    name: str
    method: str
    path: str
    expected_status: int
    actual_status: int
    passed: bool
    duration_ms: float
    note: str


def _request(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str = "",
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        base_url + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        response = urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read()
        content_type = response.headers.get("Content-Type", "")
        if not body:
            parsed: Any = None
        elif "json" in content_type:
            parsed = json.loads(body)
        else:
            parsed = body.decode("utf-8", errors="replace")
        return response.status, parsed


def _wait_for_health(base_url: str, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, body = _request(base_url, "GET", "/health")
            if status == 200 and body.get("status") == "UP":
                return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.5)
    raise DemoFailure("API did not become healthy within 60 seconds")


def _require(condition: bool, message: str) -> str:
    if not condition:
        raise DemoFailure(message)
    return message


class DemoRun:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.steps: list[StepResult] = []

    def call(
        self,
        name: str,
        method: str,
        path: str,
        expected_status: int,
        *,
        payload: dict[str, Any] | None = None,
        token: str = "",
        validate: Callable[[Any], str] | None = None,
    ) -> Any:
        started = time.perf_counter()
        status = 0
        note = ""
        body: Any = None
        passed = False
        try:
            status, body = _request(self.base_url, method, path, payload, token)
            if status != expected_status:
                error_code = body.get("code") if isinstance(body, dict) else "non-JSON response"
                raise DemoFailure(f"expected HTTP {expected_status}, got {status} ({error_code})")
            note = validate(body) if validate else "HTTP contract matched"
            passed = True
            return body
        except (OSError, urllib.error.URLError) as error:
            note = f"request failed: {type(error).__name__}"
            raise DemoFailure(note) from error
        except DemoFailure as error:
            note = str(error)
            raise
        finally:
            self.steps.append(
                StepResult(
                    name=name,
                    method=method,
                    path=path,
                    expected_status=expected_status,
                    actual_status=status,
                    passed=passed,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    note=note,
                )
            )

    def command(self, name: str, command: list[str], display_path: str) -> None:
        started = time.perf_counter()
        actual_status = -1
        note = ""
        passed = False
        try:
            process = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            actual_status = process.returncode
            if process.returncode != 0:
                raise DemoFailure(f"worker exited with code {process.returncode}")
            note = "worker exited successfully; output intentionally omitted"
            passed = True
        except subprocess.TimeoutExpired as error:
            note = "worker timed out"
            raise DemoFailure(note) from error
        except DemoFailure as error:
            note = str(error)
            raise
        finally:
            self.steps.append(
                StepResult(
                    name=name,
                    method="WORKER",
                    path=display_path,
                    expected_status=0,
                    actual_status=actual_status,
                    passed=passed,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    note=note,
                )
            )


def _write_reports(
    output_dir: Path,
    run: DemoRun,
    started_at: datetime,
    storage_label: str,
    summary: dict[str, Any],
    failure: str,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    finished_at = datetime.now(UTC)
    passed = not failure and all(step.passed for step in run.steps)
    payload = {
        "result": "PASS" if passed else "FAIL",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": round((finished_at - started_at).total_seconds() * 1000, 2),
        "base_url": run.base_url,
        "storage": storage_label,
        "summary": summary,
        "failure": failure or None,
        "steps": [asdict(step) for step in run.steps],
        "limitations": [
            "This functional demo does not prove PostgreSQL row-lock concurrency behavior.",
            "This is not a load test or benchmark result.",
            "No access token, password, or database URL is stored in this report.",
        ],
    }
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"demo-report-{timestamp}.json"
    markdown_path = output_dir / f"demo-report-{timestamp}.md"
    latest_json = output_dir / "latest-demo-report.json"
    latest_markdown = output_dir / "latest-demo-report.md"

    json_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")

    rows = "\n".join(
        "| {index} | `{method}` | `{path}` | {expected} | {actual} | {result} | {duration:.2f} | {note} |".format(
            index=index,
            method=step.method,
            path=step.path.replace("|", "\\|"),
            expected=step.expected_status,
            actual=step.actual_status,
            result="PASS" if step.passed else "FAIL",
            duration=step.duration_ms,
            note=step.note.replace("|", "\\|"),
        )
        for index, step in enumerate(run.steps, start=1)
    )
    summary_lines = "\n".join(f"- **{key}:** `{value}`" for key, value in summary.items())
    markdown = f"""# EventHub functional demo report

- **Result:** {payload["result"]}
- **Started:** {payload["started_at"]}
- **Finished:** {payload["finished_at"]}
- **API:** `{run.base_url}`
- **Storage:** {storage_label}
- **Steps:** {sum(step.passed for step in run.steps)}/{len(run.steps)} passed

## Business result

{summary_lines or "- No business result was produced."}

## HTTP evidence

| # | Method | Path | Expected | Actual | Result | ms | Evidence |
|---:|---|---|---:|---:|---|---:|---|
{rows}

## Limitations

- This functional demo does not prove PostgreSQL row-lock concurrency behavior.
- This is not a load test or benchmark result.
- No access token, password, or database URL is stored in this report.

## Failure

{failure or "None."}
"""
    markdown_path.write_text(markdown, encoding="utf-8")
    latest_markdown.write_text(markdown, encoding="utf-8")
    return markdown_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/demo"))
    parser.add_argument("--storage-label", default="configured application database")
    parser.add_argument(
        "--run-completion-worker",
        action="store_true",
        help="also demonstrate automatic event completion using the configured database",
    )
    args = parser.parse_args()

    started_at = datetime.now(UTC)
    run = DemoRun(args.base_url)
    summary: dict[str, Any] = {}
    failure = ""
    suffix = uuid.uuid4().hex[:10]
    password = "demo-password-123"

    try:
        _wait_for_health(run.base_url)
        run.call(
            "Health check",
            "GET",
            "/health",
            200,
            validate=lambda body: _require(body["status"] == "UP", "service status is UP"),
        )
        run.call("Swagger UI", "GET", "/docs", 200)
        openapi = run.call(
            "OpenAPI document",
            "GET",
            "/openapi.json",
            200,
            validate=lambda body: _require(
                body["openapi"].startswith("3."), "OpenAPI 3 document is available"
            ),
        )
        operation_count = sum(len(operations) for operations in openapi["paths"].values())
        summary["openapi_operations"] = operation_count

        run.call("Protected route without token", "GET", "/api/bookings/me", 401)

        organizer_email = f"demo-organizer-{suffix}@example.com"
        organizer = run.call(
            "Register organizer",
            "POST",
            "/api/auth/register",
            201,
            payload={
                "email": organizer_email,
                "password": password,
                "full_name": "Demo Organizer",
                "role": "ORGANIZER",
            },
            validate=lambda body: _require(body["role"] == "ORGANIZER", "role is ORGANIZER"),
        )
        organizer_login = run.call(
            "Organizer login",
            "POST",
            "/api/auth/login",
            200,
            payload={"email": organizer_email, "password": password},
            validate=lambda body: _require(
                body["token_type"] == "bearer", "bearer token issued (not stored)"
            ),
        )
        organizer_token = organizer_login["access_token"]
        run.call(
            "Organizer current account",
            "GET",
            "/api/auth/me",
            200,
            token=organizer_token,
            validate=lambda body: _require(
                body["id"] == organizer["id"], "authenticated organizer identity matched"
            ),
        )

        buyer_email = f"demo-buyer-{suffix}@example.com"
        buyer = run.call(
            "Register buyer",
            "POST",
            "/api/auth/register",
            201,
            payload={
                "email": buyer_email,
                "password": password,
                "full_name": "Demo Buyer",
                "role": "USER",
            },
            validate=lambda body: _require(body["role"] == "USER", "role is USER"),
        )
        run.call(
            "Reject invalid credentials",
            "POST",
            "/api/auth/login",
            401,
            payload={"email": buyer_email, "password": "wrong-password"},
        )
        buyer_login = run.call(
            "Buyer login",
            "POST",
            "/api/auth/login",
            200,
            payload={"email": buyer_email, "password": password},
            validate=lambda body: _require(
                body["user"]["id"] == buyer["id"], "buyer identity matched"
            ),
        )
        buyer_token = buyer_login["access_token"]

        if args.run_completion_worker:
            completion_start = datetime.now(UTC) + timedelta(seconds=8)
            completion_end = completion_start + timedelta(seconds=1)
            completion_event = run.call(
                "Create short completion event",
                "POST",
                "/api/events",
                201,
                payload={
                    "title": f"Completion Demo {suffix}",
                    "description": "Short event completed by the standalone worker",
                    "category": "demo",
                    "city": "Hanoi",
                    "location": "Completion Hall",
                    "start_time": completion_start.isoformat(),
                    "end_time": completion_end.isoformat(),
                    "total_tickets": 5,
                    "price": "10000.00",
                },
                token=organizer_token,
            )
            completion_event_id = completion_event["id"]
            run.call(
                "Publish short completion event",
                "PATCH",
                f"/api/events/{completion_event_id}/publish",
                200,
                token=organizer_token,
            )
            remaining = completion_end.timestamp() - datetime.now(UTC).timestamp() + 0.25
            if remaining > 0:
                time.sleep(remaining)
            run.command(
                "Run completion worker once",
                [sys.executable, "-m", "app.workers.event_completion", "--once"],
                "python -m app.workers.event_completion --once",
            )
            run.call(
                "Completed event is readable",
                "GET",
                f"/api/events/{completion_event_id}",
                200,
                validate=lambda body: _require(
                    body["status"] == "COMPLETED", "worker persisted COMPLETED status"
                ),
            )
            run.call(
                "Completed event leaves public catalogue",
                "GET",
                f"/api/events?q=Completion+Demo+{suffix}",
                200,
                validate=lambda body: _require(
                    body["total"] == 0, "completed event is absent from public discovery"
                ),
            )
            run.call(
                "Organizer dashboard includes completed event",
                "GET",
                "/api/events/mine?page=1&size=20&status=COMPLETED",
                200,
                token=organizer_token,
                validate=lambda body: _require(
                    any(item["id"] == completion_event_id for item in body["items"]),
                    "completed event remains in organizer history",
                ),
            )
            run.call(
                "Reject booking completed event",
                "POST",
                "/api/bookings",
                409,
                payload={"event_id": completion_event_id, "quantity": 1},
                token=buyer_token,
            )
            run.call(
                "Reject editing completed event",
                "PATCH",
                f"/api/events/{completion_event_id}",
                409,
                payload={"title": "Too late"},
                token=organizer_token,
            )
            summary["completion_event_id"] = completion_event_id
            summary["completion_event_status"] = "COMPLETED"

        start = datetime.now(UTC) + timedelta(days=30)
        event_payload = {
            "title": f"EventHub Demo {suffix}",
            "description": "Functional demonstration event",
            "category": "demo",
            "city": "Hanoi",
            "location": "Demo Hall",
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=2)).isoformat(),
            "total_tickets": 5,
            "price": "125000.00",
        }
        event = run.call(
            "Create draft event",
            "POST",
            "/api/events",
            201,
            payload=event_payload,
            token=organizer_token,
            validate=lambda body: _require(body["status"] == "DRAFT", "event status is DRAFT"),
        )
        event_id = event["id"]
        run.call(
            "Organizer dashboard lists the new draft",
            "GET",
            "/api/events/mine?page=1&size=20&status=DRAFT",
            200,
            token=organizer_token,
            validate=lambda body: _require(
                any(item["id"] == event_id for item in body["items"]),
                "owned draft appears without manually entering its ID",
            ),
        )
        edited_title = f"EventHub Demo {suffix} Edited"
        event = run.call(
            "Edit draft event",
            "PATCH",
            f"/api/events/{event_id}",
            200,
            payload={"title": edited_title, "location": "Updated Demo Hall"},
            token=organizer_token,
            validate=lambda body: _require(
                body["title"] == edited_title
                and body["location"] == "Updated Demo Hall"
                and body["status"] == "DRAFT",
                "editable fields changed while the event remained DRAFT",
            ),
        )
        run.call(
            "Read persisted draft edit",
            "GET",
            f"/api/events/{event_id}",
            200,
            token=organizer_token,
            validate=lambda body: _require(
                body["title"] == edited_title and body["organizer_id"] == organizer["id"],
                "draft edit persisted without changing ownership",
            ),
        )
        run.call("Draft is hidden from public", "GET", f"/api/events/{event_id}", 404)
        run.call(
            "Buyer cannot publish event",
            "PATCH",
            f"/api/events/{event_id}/publish",
            403,
            token=buyer_token,
        )
        event = run.call(
            "Publish event",
            "PATCH",
            f"/api/events/{event_id}/publish",
            200,
            token=organizer_token,
            validate=lambda body: _require(
                body["status"] == "PUBLISHED", "event status is PUBLISHED"
            ),
        )
        run.call(
            "Reject edit after publish",
            "PATCH",
            f"/api/events/{event_id}",
            409,
            payload={"title": "Published events are immutable"},
            token=organizer_token,
        )
        query = urllib.parse.urlencode(
            {"q": f"EventHub Demo {suffix}", "city": "Hanoi", "page": 1, "size": 5}
        )
        run.call(
            "Search published catalogue",
            "GET",
            f"/api/events?{query}",
            200,
            validate=lambda body: _require(body["total"] == 1, "catalogue returned one event"),
        )

        booking = run.call(
            "Book two tickets",
            "POST",
            "/api/bookings",
            201,
            payload={"event_id": event_id, "quantity": 2},
            token=buyer_token,
            validate=lambda body: _require(
                body["status"] == "CONFIRMED" and body["quantity"] == 2,
                "booking is CONFIRMED for 2 tickets",
            ),
        )
        booking_id = booking["id"]
        event_after_booking = run.call(
            "Inventory decreases after booking",
            "GET",
            f"/api/events/{event_id}",
            200,
            validate=lambda body: _require(
                body["available_tickets"] == 3, "available inventory changed from 5 to 3"
            ),
        )
        run.call(
            "List buyer bookings",
            "GET",
            "/api/bookings/me?page=1&size=10",
            200,
            token=buyer_token,
            validate=lambda body: _require(body["total"] == 1, "buyer has one booking"),
        )
        run.call(
            "Organizer cannot read buyer booking",
            "GET",
            f"/api/bookings/{booking_id}",
            403,
            token=organizer_token,
        )
        run.call(
            "Cancel booking",
            "DELETE",
            f"/api/bookings/{booking_id}",
            200,
            token=buyer_token,
            validate=lambda body: _require(
                body["status"] == "CANCELLED", "booking status is CANCELLED"
            ),
        )
        restored = run.call(
            "Inventory is restored",
            "GET",
            f"/api/events/{event_id}",
            200,
            validate=lambda body: _require(
                body["available_tickets"] == 5, "available inventory returned to 5"
            ),
        )
        cancelled_event = run.call(
            "Cancel published event",
            "PATCH",
            f"/api/events/{event_id}/cancel",
            200,
            token=organizer_token,
            validate=lambda body: _require(
                body["status"] == "CANCELLED", "event status is CANCELLED"
            ),
        )

        draft = run.call(
            "Create disposable draft",
            "POST",
            "/api/events",
            201,
            payload={**event_payload, "title": f"Disposable Draft {suffix}"},
            token=organizer_token,
            validate=lambda body: _require(body["status"] == "DRAFT", "second event is DRAFT"),
        )
        run.call(
            "Delete draft event",
            "DELETE",
            f"/api/events/{draft['id']}",
            204,
            token=organizer_token,
        )
        run.call(
            "Deleted draft no longer exists",
            "GET",
            f"/api/events/{draft['id']}",
            404,
            token=organizer_token,
        )

        summary.update(
            {
                "organizer_id": organizer["id"],
                "buyer_id": buyer["id"],
                "event_id": event_id,
                "event_title": event["title"],
                "event_final_status": cancelled_event["status"],
                "booking_id": booking_id,
                "booking_final_status": "CANCELLED",
                "inventory_before": event["available_tickets"],
                "inventory_after_booking": event_after_booking["available_tickets"],
                "inventory_after_cancellation": restored["available_tickets"],
            }
        )
    except DemoFailure as error:
        failure = str(error)

    markdown_path, json_path = _write_reports(
        args.output_dir,
        run,
        started_at,
        args.storage_label,
        summary,
        failure,
    )
    print(f"Demo result: {'FAIL' if failure else 'PASS'}")
    print(f"Markdown report: {markdown_path.resolve()}")
    print(f"JSON report: {json_path.resolve()}")
    return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
