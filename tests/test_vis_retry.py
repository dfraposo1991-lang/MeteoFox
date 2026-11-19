"""Testes do tratamento de falhas transitórias ECMWF VIS, sem rede."""
import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from gerar_visivel_swe_48h import get_bytes, RequestFailure

URL = "https://charts.ecmwf.int/opencharts-api/v1/products/medium-simulated-vis/image.png"

class Response:
    headers = {"Content-Type": "image/png"}
    def __init__(self, body): self.body=body
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self, n=-1): return self.body[:n]


def http_error(code):
    return HTTPError(URL,code,str(code),{"Retry-After":"300"},io.BytesIO(b"temporary"))


class TestNetworkRetry(unittest.TestCase):
    def test_success_first_attempt(self):
        with patch("gerar_visivel_swe_48h.urlopen",return_value=Response(b"ok")) as fetch:
            self.assertEqual(get_bytes(URL,image=True), (b"ok","image/png"))
            self.assertEqual(fetch.call_count,1)

    def test_connection_reset_recovers_once(self):
        with patch("gerar_visivel_swe_48h.urlopen",
                   side_effect=[URLError(ConnectionResetError("reset")),Response(b"ok")]) as fetch,\
             patch("gerar_visivel_swe_48h.time.sleep") as sleep:
            self.assertEqual(get_bytes(URL,image=True)[0], b"ok")
            self.assertEqual(fetch.call_count,2)
            sleep.assert_called_once_with(10)

    def test_three_transient_attempts(self):
        with patch("gerar_visivel_swe_48h.urlopen",
                   side_effect=[URLError("x"),URLError("x"),Response(b"ok")]) as fetch,\
             patch("gerar_visivel_swe_48h.time.sleep") as sleep:
            self.assertEqual(get_bytes(URL,image=True)[0],b"ok")
            self.assertEqual(fetch.call_count,3)
            self.assertEqual([x.args[0] for x in sleep.call_args_list],[10,25])

    def test_network_exhausted_fails_and_does_not_publish(self):
        with patch("gerar_visivel_swe_48h.urlopen",side_effect=URLError("reset")) as fetch,\
             patch("gerar_visivel_swe_48h.time.sleep"):
            with self.assertRaises(URLError):
                get_bytes(URL,image=True)
            self.assertEqual(fetch.call_count,3)

    def test_http_429_never_retries(self):
        with patch("gerar_visivel_swe_48h.urlopen",side_effect=http_error(429)) as fetch,\
             patch("gerar_visivel_swe_48h.time.sleep") as sleep:
            with self.assertRaises(RequestFailure) as ctx:
                get_bytes(URL,image=True)
            self.assertEqual(ctx.exception.status,429)
            self.assertEqual(fetch.call_count,1)
            sleep.assert_not_called()

    def test_http_400_never_retries(self):
        with patch("gerar_visivel_swe_48h.urlopen",side_effect=http_error(400)) as fetch,\
             patch("gerar_visivel_swe_48h.time.sleep") as sleep:
            with self.assertRaises(RequestFailure):
                get_bytes(URL)
            self.assertEqual(fetch.call_count,1)
            sleep.assert_not_called()

    def test_http_503_retry(self):
        with patch("gerar_visivel_swe_48h.urlopen",
                   side_effect=[http_error(503),Response(b"ok")]) as fetch,\
             patch("gerar_visivel_swe_48h.time.sleep") as sleep:
            self.assertEqual(get_bytes(URL,image=True)[0],b"ok")
            self.assertEqual(fetch.call_count,2)
            sleep.assert_called_once_with(10)

    def test_reject_external_image_url(self):
        with patch("gerar_visivel_swe_48h.urlopen") as fetch:
            with self.assertRaises(ValueError):
                get_bytes("https://example.com/evil.png",image=True)
            fetch.assert_not_called()

if __name__=="__main__": unittest.main()
