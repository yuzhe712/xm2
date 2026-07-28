from __future__ import annotations

import os
from collections import deque
from time import perf_counter
from uuid import uuid4

import gevent
from locust import HttpUser, between, task
from locust.exception import StopUser


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise StopUser(f"Missing required environment variable: {name}")
    return value


class TicketApiUser(HttpUser):
    wait_time = between(0.2, 0.5)

    def on_start(self) -> None:
        self.ticket_ids: deque[str] = deque(maxlen=100)
        self.employee_token = self._login(
            _required_env("LOADTEST_EMPLOYEE_USERNAME"),
            _required_env("LOADTEST_EMPLOYEE_PASSWORD"),
        )
        self.operator_tokens = [
            self._login(
                _required_env("LOADTEST_OPERATOR_A_USERNAME"),
                _required_env("LOADTEST_OPERATOR_A_PASSWORD"),
            ),
            self._login(
                _required_env("LOADTEST_OPERATOR_B_USERNAME"),
                _required_env("LOADTEST_OPERATOR_B_PASSWORD"),
            ),
        ]

    def _login(self, username: str, password: str) -> str:
        with self.client.post(
            "/api/v1/auth/login",
            name="POST /api/v1/auth/login",
            json={"user_id": username, "password": password},
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login failed with {response.status_code}")
                raise StopUser(f"Unable to authenticate load-test user: {username}")
            token = response.json().get("token")
            if not token:
                response.failure("login response did not contain a token")
                raise StopUser(f"Missing token for load-test user: {username}")
            response.success()
            return str(token)

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _create_ticket(self) -> str | None:
        with self.client.post(
            "/api/v1/tickets/submit",
            name="POST /api/v1/tickets/submit",
            headers=self._headers(self.employee_token),
            json={
                "title": f"Load test {uuid4().hex[:8]}",
                "text": "Payment API latency exceeded the internal alert threshold.",
                "desk_id": "ops",
                "priority": "P3",
            },
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"ticket creation failed with {response.status_code}")
                return None
            ticket_id = response.json().get("ticket_id")
            if not ticket_id:
                response.failure("ticket creation response did not contain ticket_id")
                return None
            response.success()
            self.ticket_ids.append(str(ticket_id))
            return str(ticket_id)

    @task(4)
    def create_ticket(self) -> None:
        self._create_ticket()

    @task(3)
    def query_queue(self) -> None:
        self.client.get(
            "/api/v1/tickets/queue?limit=20&offset=0",
            name="GET /api/v1/tickets/queue",
            headers=self._headers(self.operator_tokens[0]),
        )

    @task(3)
    def query_detail(self) -> None:
        if not self.ticket_ids:
            self._create_ticket()
            return
        self.client.get(
            f"/api/v1/tickets/{self.ticket_ids[-1]}/workflow",
            name="GET /api/v1/tickets/[id]/workflow",
            headers=self._headers(self.employee_token),
        )

    def _claim(self, ticket_id: str, token: str) -> int:
        with self.client.post(
            f"/api/v1/tickets/{ticket_id}/claim",
            name="POST /api/v1/tickets/[id]/claim",
            headers=self._headers(token),
            json={"version": 1},
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif (
                response.status_code == 409
                and response.json().get("error", {}).get("code")
                == "TICKET_VERSION_CONFLICT"
            ):
                response.success()
            else:
                response.failure(f"unexpected claim response {response.status_code}")
            return response.status_code

    @task(1)
    def concurrent_claim(self) -> None:
        ticket_id = self._create_ticket()
        if ticket_id is None:
            return
        started = perf_counter()
        jobs = [
            gevent.spawn(self._claim, ticket_id, token) for token in self.operator_tokens
        ]
        gevent.joinall(jobs)
        statuses = sorted(job.value for job in jobs)
        exception = None
        if statuses != [200, 409]:
            exception = RuntimeError(f"claim invariant failed: {statuses}")
        self.environment.events.request.fire(
            request_type="P5",
            name="concurrent claim invariant",
            response_time=(perf_counter() - started) * 1000,
            response_length=0,
            exception=exception,
            context={},
        )
