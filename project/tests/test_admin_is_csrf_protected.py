from flask import Response, Flask

from project.server.models import Device
from project.tests.utils import login


def _try_auth(client, user) -> Response:
    response: Response = client.post("/admin/login/", data=dict(email=user.email, password="admin"))
    return response


class TestAdminCsrf:

    def test_test_client_has_csrf_deactivated(self, app: Flask, db, user):
        response = _try_auth(app.test_client(), user)
        assert response.status_code == 302  # 302 means the login succeeded and the user is redirected to admin welcome page
        assert b"The CSRF token is missing." not in response.data

    def test_login_is_csrf_protected(self, app_prod: Flask, db, user):
        # use traditional app instead of webtest, because webtest would get the form + csrf for us
        response = _try_auth(app_prod.test_client(), user)
        assert response.status_code == 200  # 200 means that the same page was returned -> auth failed
        assert b"The CSRF token is missing." in response.data

    def test_delete_device_form_is_csrf_protected(self, prodapp, db, user, sample_device):
        login(prodapp, user.email, "admin")
        assert Device.query.count() == 1
        response = prodapp.post("/admin/device/delete/", params=dict(id=sample_device.id, url="/admin/device/")).follow()
        assert b"Failed to delete record. CSRF Token: CSRF token missing" in response
        assert Device.query.count() == 1
