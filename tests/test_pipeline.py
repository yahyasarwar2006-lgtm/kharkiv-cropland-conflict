from datetime import datetime

import pystac

import agridisrupt.pipeline as pipeline


def test_freshly_signed_replaces_an_old_token(monkeypatch):
    item = pystac.Item("x", geometry=None, bbox=None, datetime=datetime(2021, 7, 1), properties={})
    item.add_asset("B04", pystac.Asset(href="https://a.blob.core.windows.net/c/B04.tif?st=old&se=old&sp=rl&sig=old"))

    def fake_sign(it):  # stands in for planetary_computer.sign: adds a new token
        for a in it.assets.values():
            assert "?" not in a.href  # the old token must be gone before signing
            a.href += "?st=new&se=new&sp=rl&sig=new"
        return it

    monkeypatch.setattr(pipeline.planetary_computer, "sign", fake_sign)
    fresh = pipeline.freshly_signed(item)

    assert fresh.assets["B04"].href.endswith("?st=new&se=new&sp=rl&sig=new")
    assert "old" in item.assets["B04"].href  # the original item is not modified


def test_wait_for_internet_returns_when_online(monkeypatch):
    calls = iter([False, False, True])
    monkeypatch.setattr(pipeline, "internet_ok", lambda: next(calls))
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)  # don't actually wait
    pipeline.wait_for_internet()  # returns once the (fake) connection is back
