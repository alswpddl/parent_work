"""관리자 주소와 손님 주문서 주소를 나눴을 때 링크가 손님 주소로 가는지"""
from app.config import AppConfig


def test_shop_link_default_uses_admin_host():
    c = AppConfig(app_env="test", public_web_url="https://gayeom-admin.vercel.app")
    assert c.shop_link() == "https://gayeom-admin.vercel.app/shop"
    assert c.shop_link("/my") == "https://gayeom-admin.vercel.app/shop/my"
    assert c.customer_link("/order/abc") == "https://gayeom-admin.vercel.app/order/abc"


def test_shop_link_with_own_host_has_no_shop_prefix():
    c = AppConfig(app_env="test", public_web_url="https://gayeom-admin.vercel.app", public_shop_url="https://gayeom.vercel.app")
    assert c.shop_link() == "https://gayeom.vercel.app"
    assert c.shop_link("/my") == "https://gayeom.vercel.app/my"
    assert c.shop_link("/item/%EB%A9%B8%EC%B9%98%EC%95%A1%EC%A0%93") == "https://gayeom.vercel.app/item/%EB%A9%B8%EC%B9%98%EC%95%A1%EC%A0%93"
    assert c.customer_link("/order/abc") == "https://gayeom.vercel.app/order/abc"


def test_kakao_bot_buttons_use_shop_host(full_ctx):
    full_ctx.config.public_shop_url = "https://gayeom.vercel.app"
    bot = full_ctx.services["kakao_bot"]
    assert bot._shop_url() == "https://gayeom.vercel.app"
    assert bot._shop_url("/cart") == "https://gayeom.vercel.app/cart"
